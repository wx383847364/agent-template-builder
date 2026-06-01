from __future__ import annotations

from pathlib import Path
from typing import Optional
import argparse
import json

from agent_template_builder.matcher.template_matcher import AspectRatioProfile, TemplateMatcher
from agent_template_builder.ocr.base import NullOCREngine, OCREngine
from agent_template_builder.paths import default_game_dir
from agent_template_builder.schema.agent_data import AgentData, Element, Evidence, Resolution, RuntimeState, Screen, TaskState
from agent_template_builder.schema.templates import denormalize_bbox, load_game_config, load_templates


DEFAULT_GAME_DIR = default_game_dir()


def analyze_screenshot(
    screenshot_path: Path,
    game_dir: Path = DEFAULT_GAME_DIR,
    ocr_engine: Optional[OCREngine] = None,
) -> AgentData:
    game_config = load_game_config(game_dir)
    templates = load_templates(game_dir)
    supported_sizes = {
        (int(item["width"]), int(item["height"]))
        for item in game_config.get("supported_windows", [])
    }
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
    )
    match = matcher.match(screenshot_path)
    ocr = ocr_engine or NullOCREngine()

    elements: list[Element] = []
    task_state: Optional[TaskState] = None

    for spec in match.template.elements:
        bbox = denormalize_bbox(spec.bbox, match.width, match.height)
        text = None
        confidence = match.confidence
        evidence = Evidence(
            region_id=spec.id,
            source="template",
            template_id=match.template.template_id,
        )

        if spec.ocr_required:
            result = ocr.read_region(screenshot_path, bbox)
            text = result.text
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
            "ocr_policy": game_config.get("ocr_policy", {}),
            "match": {
                "aspect_ratio_label": match.aspect_ratio_label,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="将游戏截图分析为 AgentData JSON。")
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    args = parser.parse_args()

    result = analyze_screenshot(args.screenshot, args.game_dir)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
