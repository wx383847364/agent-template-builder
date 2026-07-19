from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from typing import Iterator, Optional
import argparse
import json

from PIL import Image

from agent_template_builder.matcher.template_matcher import AspectRatioProfile, TemplateMatcher
from agent_template_builder.matcher.roi import denormalize_bbox_in_view
from agent_template_builder.ocr.base import NullOCREngine, OCREngine, OCRResult
from agent_template_builder.ocr.cache import (
    EngineRuntimeState,
    EngineStateRegistry,
    RegionCacheStats,
    make_region_cache_key,
)
from agent_template_builder.ocr.postprocess import (
    DEFAULT_CONFUSION_SUBSTITUTIONS,
    OCRPostprocessor,
    load_confusions,
    load_vocab,
)
from agent_template_builder.ocr.runtime import add_ocr_argument, create_ocr_engine_or_error
from agent_template_builder.paths import default_game_dir
from agent_template_builder.schema.agent_data import AgentData, Element, Evidence, Resolution, RuntimeState, Screen, TaskState
from agent_template_builder.schema.templates import denormalize_bbox, load_game_config, load_templates


DEFAULT_GAME_DIR = default_game_dir()
OCR_CACHE_MAX_ENTRIES = 256


@dataclass
class _ScreenshotSnapshot:
    image: Image.Image
    owns_image: bool = True
    _temporary_dir: TemporaryDirectory[str] | None = None
    _legacy_path: Path | None = None

    def legacy_path(self) -> Path:
        if self._legacy_path is None:
            self._temporary_dir = TemporaryDirectory(prefix="agent_template_builder_snapshot_")
            self._legacy_path = Path(self._temporary_dir.name) / "snapshot.png"
            self.image.save(self._legacy_path, format="PNG")
        return self._legacy_path

    def close(self) -> None:
        if self._temporary_dir is not None:
            self._temporary_dir.cleanup()
            self._temporary_dir = None
            self._legacy_path = None
        if self.owns_image:
            self.image.close()


_OCR_STATES = EngineStateRegistry(cache_max_entries=OCR_CACHE_MAX_ENTRIES)
_FALLBACK_INFERENCE_LOCK = RLock()


def analyze_screenshot(
    screenshot_path: Path,
    game_dir: Path = DEFAULT_GAME_DIR,
    ocr_engine: Optional[OCREngine] = None,
) -> AgentData:
    game_config = load_game_config(game_dir)
    templates = load_templates(game_dir)
    supported_sizes = {
        (int(item["width"]), int(item["height"])): item["label"]
        for item in game_config.get("supported_windows", [])
    }
    viewport_profiles = {
        (int(item["width"]), int(item["height"])): item["label"]
        for item in game_config.get("viewport_profiles", [])
    }
    game_view_profiles = list(game_config.get("game_view_profiles", []))
    aspect_profiles = [
        AspectRatioProfile(
            label=item["label"],
            ratio=float(item["width"]) / float(item["height"]),
            tolerance=float(item.get("tolerance", 0.04)),
        )
        for item in game_config.get("supported_aspect_ratios", [])
    ]

    matcher = TemplateMatcher(
        templates=templates,
        supported_sizes=supported_sizes,
        aspect_profiles=aspect_profiles,
        viewport_profiles=viewport_profiles,
        game_view_profiles=game_view_profiles,
    )
    ocr = ocr_engine or NullOCREngine()
    ocr_policy = game_config.get("ocr_policy", {})
    cache_enabled = bool(ocr_policy.get("cache_by_region_hash", False)) and ocr_engine is not None
    postprocessor = _load_postprocessor(game_dir.resolve())

    elements: list[Element] = []
    task_state: Optional[TaskState] = None

    with _open_screenshot_snapshot(screenshot_path) as screenshot_snapshot:
        match = matcher.match_image(screenshot_snapshot.image)
        for spec in match.template.elements:
            screen_bbox = spec.screen_bbox_for_profile(match.viewport_profile_label)
            bbox = (
                denormalize_bbox(screen_bbox, match.width, match.height)
                if screen_bbox
                else denormalize_bbox_in_view(spec.bbox_for_profile(match.viewport_profile_label), match.game_view)
            )
            text = None
            confidence = match.confidence
            evidence = Evidence(
                region_id=spec.id,
                source="template",
                template_id=match.template.template_id,
            )

            if spec.ocr_required:
                result = _read_ocr_region(
                    ocr,
                    screenshot_path,
                    bbox,
                    template_id=match.template.template_id,
                    element_id=spec.id,
                    cache_enabled=cache_enabled,
                    screenshot_snapshot=screenshot_snapshot,
                )
                processed = postprocessor.process(result, spec.semantic_role)
                text = processed.corrected_text
                confidence = min(match.confidence, result.confidence) if result.confidence else match.confidence
                evidence = Evidence(
                    region_id=spec.id,
                    source="ocr",
                    ocr_text=result.text,
                    template_id=match.template.template_id,
                )

            element = Element(
                id=spec.id,
                type=spec.type,
                bbox=bbox,
                confidence=confidence,
                semantic_role=spec.semantic_role,
                text=text,
                evidence=evidence,
            )
            elements.append(element)

            if spec.semantic_role == "current_task":
                task_state = TaskState(
                    visible=True,
                    text=text,
                    confidence=confidence,
                    evidence=evidence,
                )

    for spec in match.template.static_outputs:
        screen_bbox = spec.screen_bbox_for_profile(match.viewport_profile_label)
        if screen_bbox:
            bbox = denormalize_bbox(screen_bbox, match.width, match.height)
        else:
            spec_bbox = spec.bbox_for_profile(match.viewport_profile_label)
            bbox = denormalize_bbox_in_view(spec_bbox, match.game_view) if spec_bbox else (0, 0, 0, 0)
        elements.append(
            Element(
                id=spec.id,
                type=spec.type,
                bbox=bbox,
                confidence=match.confidence,
                semantic_role=spec.semantic_role,
                text=spec.text if spec.text is not None else spec.value,
                evidence=Evidence(
                    region_id=spec.id,
                    source="template_static",
                    template_id=match.template.template_id,
                ),
            )
        )

    return AgentData(
        game={
            "id": game_config["game_id"],
            "client": game_config["client"],
        },
        screen=Screen(
            type=match.template.screen_type,
            template_id=match.template.template_id,
            confidence=match.confidence,
            resolution=Resolution(width=match.width, height=match.height),
        ),
        task=task_state,
        elements=elements,
        state=RuntimeState(
            blocking_modal=match.template.blocking_modal,
            available_intents=match.template.available_intents,
        ),
        raw={
            "coordinate_space": game_config.get("coordinate_space", {}),
            "ocr_policy": ocr_policy,
            "game_view": {
                "bbox": match.game_view.bbox,
                "width": match.game_view.width,
                "height": match.game_view.height,
                "source": match.game_view.source,
            },
            "match": {
                "aspect_ratio_label": match.aspect_ratio_label,
                "viewport_profile_label": match.viewport_profile_label,
                "fallback_reason": match.fallback_reason,
                "measurable_template_count": match.measurable_template_count,
                "anchor_matches": [
                    {
                        "id": item.id,
                        "score": item.score,
                        "actual_hash": item.actual_hash,
                        "expected_hash": item.expected_hash,
                        "hamming_distance": item.hamming_distance,
                    }
                    for item in match.anchor_matches
                ],
            },
        },
    )


def _read_ocr_region(
    ocr: OCREngine,
    screenshot_path: Path,
    bbox: tuple[int, int, int, int],
    *,
    template_id: str,
    element_id: str,
    cache_enabled: bool,
    screenshot_image: Image.Image | None = None,
    screenshot_snapshot: _ScreenshotSnapshot | None = None,
) -> OCRResult:
    if screenshot_snapshot is not None:
        return _read_ocr_from_snapshot(
            ocr,
            screenshot_snapshot,
            bbox,
            template_id=template_id,
            element_id=element_id,
            cache_enabled=cache_enabled,
        )

    if screenshot_image is not None:
        borrowed_snapshot = _ScreenshotSnapshot(screenshot_image, owns_image=False)
        try:
            return _read_ocr_from_snapshot(
                ocr,
                borrowed_snapshot,
                bbox,
                template_id=template_id,
                element_id=element_id,
                cache_enabled=cache_enabled,
            )
        finally:
            borrowed_snapshot.close()

    with _open_screenshot_snapshot(screenshot_path) as opened_snapshot:
        return _read_ocr_from_snapshot(
            ocr,
            opened_snapshot,
            bbox,
            template_id=template_id,
            element_id=element_id,
            cache_enabled=cache_enabled,
        )


def _read_ocr_from_snapshot(
    ocr: OCREngine,
    screenshot_snapshot: _ScreenshotSnapshot,
    bbox: tuple[int, int, int, int],
    *,
    template_id: str,
    element_id: str,
    cache_enabled: bool,
) -> OCRResult:
    normalized_bbox = _normalize_bbox(screenshot_snapshot.image, bbox)
    if normalized_bbox is None:
        return OCRResult(text="", confidence=0.0)

    state = _state_for_engine(ocr)
    inference_lock = state.inference_lock if state is not None else _FALLBACK_INFERENCE_LOCK
    read_image = getattr(ocr, "read_image", None)
    if not callable(read_image):
        with inference_lock:
            return ocr.read_region(screenshot_snapshot.legacy_path(), normalized_bbox)

    roi = screenshot_snapshot.image.crop(normalized_bbox).copy()
    try:
        ocr_config_id = _ocr_config_id(ocr)
        can_cache = cache_enabled and ocr_config_id is not None and state is not None

        def compute() -> OCRResult:
            with inference_lock:
                return read_image(roi)

        if not can_cache:
            return compute()

        key = make_region_cache_key(
            template_id,
            element_id,
            roi,
            ocr_config_id,
        )
        return state.cache.get_or_compute(key, compute)
    finally:
        roi.close()


def _normalize_bbox(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = bbox
    left = max(0, min(left, image.width))
    top = max(0, min(top, image.height))
    right = max(0, min(right, image.width))
    bottom = max(0, min(bottom, image.height))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


@contextmanager
def _open_screenshot_snapshot(screenshot_path: Path) -> Iterator[_ScreenshotSnapshot]:
    with Image.open(screenshot_path) as image:
        snapshot = _ScreenshotSnapshot(image.copy())
    try:
        yield snapshot
    finally:
        snapshot.close()


def _ocr_config_id(ocr: OCREngine) -> str | None:
    identity = getattr(ocr, "cache_identity", None)
    if isinstance(identity, str) and identity:
        return identity
    return None


def _state_for_engine(ocr: OCREngine) -> EngineRuntimeState | None:
    return _OCR_STATES.get_or_create(ocr)


def clear_engine_region_cache(ocr: OCREngine, *, reset_stats: bool = False) -> bool:
    return _OCR_STATES.clear_cache(ocr, reset_stats=reset_stats)


def get_engine_region_cache_stats(ocr: OCREngine) -> RegionCacheStats | None:
    return _OCR_STATES.cache_stats(ocr)


def _load_postprocessor(game_dir: Path) -> OCRPostprocessor:
    vocab_dir = game_dir / "vocab"
    server_names_path = vocab_dir / "server_names.txt"
    common_terms_path = vocab_dir / "common_terms.txt"
    confusions_path = vocab_dir / "ocr_confusions.json"
    server_names = load_vocab(server_names_path) if server_names_path.is_file() else ()
    common_terms = load_vocab(common_terms_path) if common_terms_path.is_file() else ()
    confusions = (
        load_confusions(confusions_path)
        if confusions_path.is_file()
        else DEFAULT_CONFUSION_SUBSTITUTIONS
    )
    return _postprocessor_from_vocab(server_names, common_terms, confusions)


@lru_cache(maxsize=16)
def _postprocessor_from_vocab(
    server_names: tuple[str, ...],
    common_terms: tuple[str, ...],
    confusion_substitutions: tuple[tuple[str, str], ...],
) -> OCRPostprocessor:
    return OCRPostprocessor(
        server_names=server_names,
        common_terms=common_terms,
        confusion_substitutions=confusion_substitutions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="将游戏截图分析为 AgentData JSON。")
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    add_ocr_argument(parser)
    args = parser.parse_args()

    ocr_engine = create_ocr_engine_or_error(parser, args.ocr, args.ocr_device)
    result = analyze_screenshot(args.screenshot, args.game_dir, ocr_engine)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
