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
        issues.append("game.json: v1 要求 ocr_policy.only_when_required 为 true")

    template_ids = set()
    for template in templates:
        issues.extend(_audit_template(template))
        if template.template_id in template_ids:
            issues.append(f"{template.template_id}: template_id 重复")
        template_ids.add(template.template_id)

    if not any(template.screen_type == "main_world" for template in templates):
        issues.append("templates: 需要一个 main_world 兜底模板")

    return issues


def _audit_template(template: TemplateSpec) -> list[str]:
    issues: list[str] = []
    if not template.anchors:
        issues.append(f"{template.template_id}: 至少需要一个锚点")
    if not template.elements:
        issues.append(f"{template.template_id}: 至少需要一个元素")

    for anchor in template.anchors:
        issues.extend(_audit_bbox(template.template_id, "anchor", anchor.id, anchor.bbox))
        if anchor.weight <= 0:
            issues.append(f"{template.template_id}: 锚点 {anchor.id} 的 weight 必须为正数")

    for element in template.elements:
        issues.extend(_audit_bbox(template.template_id, "element", element.id, element.bbox))
        if element.type == "text_region" and not element.ocr_required:
            issues.append(f"{template.template_id}: text_region {element.id} 应设置 ocr_required=true")

    if template.screen_type in {"npc_dialog", "blocking_modal"} and not template.blocking_modal:
        if template.screen_type == "blocking_modal":
            issues.append(f"{template.template_id}: blocking_modal 屏幕应设置 blocking_modal=true")

    return issues


def _audit_bbox(template_id: str, kind: str, item_id: str, bbox: tuple[float, float, float, float]) -> list[str]:
    left, top, right, bottom = bbox
    issues: list[str] = []
    if not all(0.0 <= value <= 1.0 for value in bbox):
        issues.append(f"{template_id}: {kind} {item_id} 的 bbox 值必须归一化到 0..1")
    if left >= right or top >= bottom:
        issues.append(f"{template_id}: {kind} {item_id} 的 bbox 必须按 left,top,right,bottom 排列")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="校验 Agent Template Builder 模板包配置。")
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    parser.add_argument("--json", action="store_true", help="打印机器可读的审计结果")
    args = parser.parse_args()

    issues = audit_game_dir(args.game_dir)
    if args.json:
        print(json.dumps({"ok": not issues, "issues": issues}, ensure_ascii=False, indent=2))
    elif issues:
        print("模板审计未通过:")
        for issue in issues:
            print(f"- {issue}")
    else:
        print("模板审计通过。")

    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
