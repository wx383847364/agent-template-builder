from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from agent_template_builder.pipeline.analyze import DEFAULT_GAME_DIR
from agent_template_builder.schema.templates import AnchorSpec, ElementSpec, TemplateSpec, load_game_config, load_templates


def audit_game_dir(game_dir: Path) -> list[str]:
    issues: list[str] = []
    config = load_game_config(game_dir)
    templates = load_templates(game_dir)

    if config.get("ocr_policy", {}).get("only_when_required") is not True:
        issues.append("game.json: ocr_policy.only_when_required should be true for v1")

    template_ids = set()
    for template in templates:
        issues.extend(_audit_template(template))
        if template.template_id in template_ids:
            issues.append(f"{template.template_id}: duplicate template_id")
        template_ids.add(template.template_id)

    if not any(template.screen_type == "main_world" for template in templates):
        issues.append("templates: one main_world fallback template is required")

    return issues


def _audit_template(template: TemplateSpec) -> list[str]:
    issues: list[str] = []
    if not template.anchors:
        issues.append(f"{template.template_id}: at least one anchor is required")
    if not template.elements:
        issues.append(f"{template.template_id}: at least one element is required")

    for anchor in template.anchors:
        issues.extend(_audit_bbox(template.template_id, "anchor", anchor.id, anchor.bbox))
        if anchor.weight <= 0:
            issues.append(f"{template.template_id}: anchor {anchor.id} weight must be positive")

    for element in template.elements:
        issues.extend(_audit_bbox(template.template_id, "element", element.id, element.bbox))
        if element.type == "text_region" and not element.ocr_required:
            issues.append(f"{template.template_id}: text_region {element.id} should set ocr_required=true")

    if template.screen_type in {"npc_dialog", "blocking_modal"} and not template.blocking_modal:
        if template.screen_type == "blocking_modal":
            issues.append(f"{template.template_id}: blocking_modal screen should set blocking_modal=true")

    return issues


def _audit_bbox(template_id: str, kind: str, item_id: str, bbox: tuple[float, float, float, float]) -> list[str]:
    left, top, right, bottom = bbox
    issues: list[str] = []
    if not all(0.0 <= value <= 1.0 for value in bbox):
        issues.append(f"{template_id}: {kind} {item_id} bbox values must be normalized 0..1")
    if left >= right or top >= bottom:
        issues.append(f"{template_id}: {kind} {item_id} bbox must be left,top,right,bottom")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Agent Template Builder template pack configuration.")
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    parser.add_argument("--json", action="store_true", help="print machine-readable audit result")
    args = parser.parse_args()

    issues = audit_game_dir(args.game_dir)
    if args.json:
        print(json.dumps({"ok": not issues, "issues": issues}, ensure_ascii=False, indent=2))
    elif issues:
        print("Template audit failed:")
        for issue in issues:
            print(f"- {issue}")
    else:
        print("Template audit passed.")

    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
