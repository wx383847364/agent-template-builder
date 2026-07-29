from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Iterable, Optional

from agent_template_builder.discovery.schema import (
    CoordinateSpace,
    DiscoveryData,
    ElementCandidate,
    EvidenceRecord,
    ModelDiscoveryOutput,
    PanelCandidate,
    PreparationRequest,
    RunInfo,
    TextContent,
)
from agent_template_builder.ocr.base import OCREngine


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
PROMPT_VERSION = "ui_discovery_v1"


class DiscoveryProcessingError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_discovery_data(
    *,
    screenshot_path: Path,
    request: PreparationRequest,
    model_output: ModelDiscoveryOutput,
    model_output_sha256: str,
    ocr_engine: Optional[OCREngine] = None,
    extra_warnings: Iterable[str] = (),
    status: str = "complete",
) -> DiscoveryData:
    _require_unique_ids(model_output.panels, "panel")
    _require_unique_ids(model_output.elements, "element")
    _require_unique_ids(model_output.evidence, "evidence")

    warnings = [*model_output.warnings, *extra_warnings]
    panels = _deduplicate_panels(
        _sanitize_panels(model_output.panels, warnings),
        warnings,
    )
    elements = _sanitize_elements(model_output.elements, warnings)
    elements = _deduplicate_elements(elements, warnings)
    evidence = list(model_output.evidence)

    if ocr_engine is not None:
        elements, ocr_evidence, ocr_warnings = _refine_with_ocr(
            screenshot_path,
            elements,
            ocr_engine,
            occupied_evidence_ids={item.id for item in evidence},
        )
        evidence.extend(ocr_evidence)
        warnings.extend(ocr_warnings)

    return DiscoveryData(
        status=status,
        source=request.source,
        coordinate_space=CoordinateSpace(),
        run=RunInfo(
            run_id=request.run_id,
            prompt_version=request.prompt_version,
            model_output_sha256=model_output_sha256,
        ),
        known_template_context=request.known_template_context,
        scene=model_output.scene,
        panels=panels,
        elements=elements,
        evidence=_deduplicate_evidence(evidence),
        warnings=list(dict.fromkeys(warnings)),
        errors=[],
    )


def sanitize_review_candidates(
    panels: list[PanelCandidate],
    elements: list[ElementCandidate],
) -> tuple[list[PanelCandidate], list[ElementCandidate], list[str]]:
    _require_unique_ids(panels, "panel")
    _require_unique_ids(elements, "element")
    warnings: list[str] = []
    sanitized_panels = _deduplicate_panels(
        _sanitize_panels(panels, warnings),
        warnings,
    )
    sanitized_elements = _deduplicate_elements(
        _sanitize_elements(elements, warnings),
        warnings,
    )
    return sanitized_panels, sanitized_elements, warnings


def _require_unique_ids(items: Iterable[object], kind: str) -> None:
    seen: set[str] = set()
    for item in items:
        item_id = str(getattr(item, "id"))
        if item_id in seen:
            raise DiscoveryProcessingError(f"duplicate {kind} id: {item_id}")
        seen.add(item_id)


def _sanitize_panels(
    panels: list[PanelCandidate],
    warnings: list[str],
) -> list[PanelCandidate]:
    result: list[PanelCandidate] = []
    for panel in panels:
        bbox = _sanitize_bbox(panel.bbox, panel.id, "bbox", warnings)
        if bbox is None:
            continue
        result.append(panel.model_copy(update={"bbox": bbox}))
    return result


def _sanitize_elements(
    elements: list[ElementCandidate],
    warnings: list[str],
) -> list[ElementCandidate]:
    result: list[ElementCandidate] = []
    for element in elements:
        bbox = _sanitize_bbox(element.bbox, element.id, "bbox", warnings)
        if bbox is None:
            continue
        interaction_bbox = element.interaction_bbox_guess
        if interaction_bbox is not None:
            interaction_bbox = _sanitize_bbox(
                interaction_bbox,
                element.id,
                "interaction_bbox_guess",
                warnings,
            )
        result.append(
            element.model_copy(
                update={
                    "bbox": bbox,
                    "interaction_bbox_guess": interaction_bbox,
                }
            )
        )
    return result


def _sanitize_bbox(
    bbox: tuple[int, int, int, int],
    item_id: str,
    field_name: str,
    warnings: list[str],
) -> tuple[int, int, int, int] | None:
    original = tuple(int(value) for value in bbox)
    left, top, right, bottom = original
    clipped = (
        max(0, min(left, SCREEN_WIDTH)),
        max(0, min(top, SCREEN_HEIGHT)),
        max(0, min(right, SCREEN_WIDTH)),
        max(0, min(bottom, SCREEN_HEIGHT)),
    )
    if clipped != original:
        warnings.append(
            f"{item_id}.{field_name}: clipped {list(original)} to {list(clipped)}"
        )
    if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        warnings.append(
            f"{item_id}.{field_name}: rejected empty bbox {list(clipped)}"
        )
        return None
    return clipped


def _deduplicate_elements(
    elements: list[ElementCandidate],
    warnings: list[str],
) -> list[ElementCandidate]:
    kept: list[ElementCandidate] = []
    for element in elements:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(kept)
                if existing.type == element.type and _bbox_iou(existing.bbox, element.bbox) >= 0.85
            ),
            None,
        )
        if duplicate_index is None:
            kept.append(element)
            continue

        existing = kept[duplicate_index]
        winner, loser = (
            (element, existing)
            if _text_length(element) > _text_length(existing)
            else (existing, element)
        )
        kept[duplicate_index] = winner.model_copy(
            update={
                "evidence_ids": list(
                    dict.fromkeys([*winner.evidence_ids, *loser.evidence_ids])
                ),
                "data_field": winner.data_field or loser.data_field,
                "suggested_actions": winner.suggested_actions or loser.suggested_actions,
            }
        )
        warnings.append(
            f"deduplicated element {loser.id} into {winner.id} at IoU >= 0.85"
        )
    return kept


def _deduplicate_panels(
    panels: list[PanelCandidate],
    warnings: list[str],
) -> list[PanelCandidate]:
    kept: list[PanelCandidate] = []
    for panel in panels:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(kept)
                if existing.type_guess == panel.type_guess
                and _bbox_iou(existing.bbox, panel.bbox) >= 0.85
            ),
            None,
        )
        if duplicate_index is None:
            kept.append(panel)
            continue

        existing = kept[duplicate_index]
        winner, loser = (
            (panel, existing)
            if (len(panel.title), panel.confidence)
            > (len(existing.title), existing.confidence)
            else (existing, panel)
        )
        kept[duplicate_index] = winner
        warnings.append(
            f"deduplicated panel {loser.id} into {winner.id} at IoU >= 0.85"
        )
    return kept


def _bbox_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    if not intersection:
        return 0.0
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / (first_area + second_area - intersection)


def _text_length(element: ElementCandidate) -> int:
    return max(len(element.text.raw), len(element.text.normalized))


def _refine_with_ocr(
    screenshot_path: Path,
    elements: list[ElementCandidate],
    ocr_engine: OCREngine,
    *,
    occupied_evidence_ids: set[str],
) -> tuple[list[ElementCandidate], list[EvidenceRecord], list[str]]:
    refined: list[ElementCandidate] = []
    evidence: list[EvidenceRecord] = []
    warnings: list[str] = []
    readable_types = {
        "button",
        "tab",
        "list_item",
        "input",
        "checkbox",
        "text",
        "data_field",
    }
    for element in elements:
        if element.type not in readable_types:
            refined.append(element)
            continue

        try:
            result = ocr_engine.read_region(screenshot_path, element.bbox)
        except Exception as exc:
            warnings.append(
                f"{element.id}: OCR verification failed; kept Codex text: {exc}"
            )
            refined.append(element)
            continue
        ocr_text = result.text.strip()
        if not ocr_text:
            refined.append(element)
            continue

        evidence_id = _unique_evidence_id(
            f"ocr_{element.id}",
            occupied_evidence_ids,
        )
        occupied_evidence_ids.add(evidence_id)
        evidence.append(
            EvidenceRecord(
                id=evidence_id,
                source="ocr",
                description=ocr_text,
                confidence=result.confidence,
            )
        )
        updated_text = element.text
        if not updated_text.raw:
            updated_text = TextContent(raw=ocr_text, normalized=ocr_text)
        elif updated_text.raw.strip() != ocr_text:
            warnings.append(
                f"{element.id}: Codex text {updated_text.raw!r} differs from OCR {ocr_text!r}"
            )
        refined.append(
            element.model_copy(
                update={
                    "text": updated_text,
                    "evidence_ids": list(
                        dict.fromkeys([*element.evidence_ids, evidence_id])
                    ),
                }
            )
        )
    return refined, evidence, warnings


def _unique_evidence_id(base: str, occupied: set[str]) -> str:
    if base not in occupied:
        return base
    suffix = 2
    while f"{base}_{suffix}" in occupied:
        suffix += 1
    return f"{base}_{suffix}"


def _deduplicate_evidence(evidence: list[EvidenceRecord]) -> list[EvidenceRecord]:
    result: list[EvidenceRecord] = []
    seen: set[str] = set()
    for item in evidence:
        if item.id not in seen:
            result.append(item)
            seen.add(item.id)
    return result
