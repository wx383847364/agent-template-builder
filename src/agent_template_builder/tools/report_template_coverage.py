from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import argparse
import json

from agent_template_builder.paths import default_game_dir, find_project_root
from agent_template_builder.schema.templates import TemplateSpec, load_templates


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass(frozen=True)
class TemplateCoverage:
    template_id: str
    screen_type: str
    has_template_json: bool
    has_screenshot_sample: bool
    has_expected_json: bool
    has_measurable_anchor: bool
    has_ocr_region: bool
    sample_count: int
    expected_count: int
    anchor_count: int
    measurable_anchor_count: int
    ocr_region_count: int
    missing: list[str]


@dataclass(frozen=True)
class CoverageReport:
    game_dir: str
    samples_dir: str
    template_count: int
    complete_count: int
    templates: list[TemplateCoverage]

    @property
    def complete_ratio(self) -> float:
        if not self.template_count:
            return 0.0
        return round(self.complete_count / self.template_count, 4)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["complete_ratio"] = self.complete_ratio
        return data


def build_coverage_report(game_dir: Path, samples_dir: Path | None = None) -> CoverageReport:
    game_dir = game_dir.resolve()
    if samples_dir is None:
        project_root = find_project_root(game_dir)
        samples_dir = project_root / "samples" / game_dir.name
    samples_dir = samples_dir.resolve()

    screenshots_dir = samples_dir / "screenshots"
    expected_dir = samples_dir / "expected"
    templates = load_templates(game_dir)
    coverage = [
        _template_coverage(template, screenshots_dir, expected_dir)
        for template in templates
    ]
    complete_count = sum(1 for item in coverage if not item.missing)

    return CoverageReport(
        game_dir=str(game_dir),
        samples_dir=str(samples_dir),
        template_count=len(coverage),
        complete_count=complete_count,
        templates=coverage,
    )


def _template_coverage(
    template: TemplateSpec,
    screenshots_dir: Path,
    expected_dir: Path,
) -> TemplateCoverage:
    sample_count = _matching_file_count(screenshots_dir, template, IMAGE_SUFFIXES)
    expected_count = _matching_file_count(expected_dir, template, {".json"})
    ocr_region_count = sum(1 for element in template.elements if element.ocr_required)

    checks = {
        "screenshot_sample": sample_count > 0,
        "expected_json": expected_count > 0,
        "measurable_anchor": template.measurable_anchor_count > 0,
        "ocr_region": ocr_region_count > 0,
    }

    return TemplateCoverage(
        template_id=template.template_id,
        screen_type=template.screen_type,
        has_template_json=True,
        has_screenshot_sample=checks["screenshot_sample"],
        has_expected_json=checks["expected_json"],
        has_measurable_anchor=checks["measurable_anchor"],
        has_ocr_region=checks["ocr_region"],
        sample_count=sample_count,
        expected_count=expected_count,
        anchor_count=len(template.anchors),
        measurable_anchor_count=template.measurable_anchor_count,
        ocr_region_count=ocr_region_count,
        missing=[name for name, ok in checks.items() if not ok],
    )


def _matching_file_count(directory: Path, template: TemplateSpec, suffixes: set[str]) -> int:
    if not directory.exists():
        return 0

    stems = {template.template_id, template.screen_type}
    count = 0
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if path.stem in stems or any(path.stem.startswith(f"{stem}__") for stem in stems):
            count += 1
            continue
        if path.suffix.lower() == ".json":
            count += _matching_expected_case_count(path, template)
    return count


def _matching_expected_case_count(path: Path, template: TemplateSpec) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return 0

    cases = data.get("cases")
    if not isinstance(cases, list):
        return 0

    count = 0
    for item in cases:
        if not isinstance(item, dict):
            continue
        if item.get("template_id") == template.template_id or item.get("screen_type") == template.screen_type:
            count += 1
    return count


def format_text_report(report: CoverageReport) -> str:
    lines = [
        "Template coverage report",
        f"game_dir: {report.game_dir}",
        f"samples_dir: {report.samples_dir}",
        f"complete: {report.complete_count}/{report.template_count} ({report.complete_ratio:.2%})",
        "",
    ]

    for item in report.templates:
        status = "ok" if not item.missing else "missing " + ", ".join(item.missing)
        lines.append(f"- {item.template_id} ({item.screen_type}): {status}")
        lines.append(
            "  "
            f"samples={item.sample_count}, expected={item.expected_count}, "
            f"anchors={item.measurable_anchor_count}/{item.anchor_count}, "
            f"ocr_regions={item.ocr_region_count}"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report template asset coverage.")
    parser.add_argument("--game-dir", type=Path, default=default_game_dir())
    parser.add_argument("--samples-dir", type=Path)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    report = build_coverage_report(args.game_dir, args.samples_dir)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report))


if __name__ == "__main__":
    main()
