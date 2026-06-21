from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import argparse
import json

from agent_template_builder.paths import default_game_dir, find_project_root
from agent_template_builder.pipeline.analyze import analyze_screenshot
from agent_template_builder.pipeline.analyze_screenshots import IMAGE_SUFFIXES, list_screenshots


@dataclass(frozen=True)
class ExpectedCase:
    case_id: Optional[str]
    screenshot: str
    expected_screen_type: Optional[str]
    expected_template_id: Optional[str]
    sample_status: Optional[str]


@dataclass(frozen=True)
class RecognitionQualityItem:
    screenshot: str
    case_id: Optional[str]
    sample_status: Optional[str]
    expected_screen_type: Optional[str]
    expected_template_id: Optional[str]
    actual_screen_type: Optional[str]
    actual_template_id: Optional[str]
    confidence: Optional[float]
    fallback_reason: Optional[str]
    anchor_matches: list[dict[str, object]]
    passed_expected: Optional[bool]
    issue: Optional[str] = None


@dataclass(frozen=True)
class RecognitionQualityReport:
    game_dir: str
    source: str
    total_count: int
    analyzed_count: int
    passed_count: int
    failed_count: int
    missing_count: int
    low_confidence_count: int
    low_confidence_threshold: float
    items: list[RecognitionQualityItem]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_quality_report(
    game_dir: Path,
    samples_dir: Path | None = None,
    screenshot_dir: Path | None = None,
    expected_path: Path | None = None,
    low_confidence_threshold: float = 0.6,
) -> RecognitionQualityReport:
    game_dir = game_dir.resolve()
    project_root = find_project_root(game_dir)
    if samples_dir is None:
        samples_dir = project_root / "samples" / game_dir.name
    samples_dir = samples_dir.resolve()
    if expected_path is None:
        expected_path = samples_dir / "expected" / "final_expected.json"
    expected_path = expected_path.resolve()

    expected_cases = _load_expected_cases(expected_path, project_root)
    expected_by_path = {
        str(_resolve_screenshot_path(case.screenshot, project_root).resolve()): case
        for case in expected_cases
    }

    if screenshot_dir is None:
        source = str(expected_path)
        items = [_analyze_expected_case(case, project_root, game_dir) for case in expected_cases]
    else:
        screenshot_dir = screenshot_dir.resolve()
        source = str(screenshot_dir)
        items = []
        for screenshot in list_screenshots(screenshot_dir):
            case = expected_by_path.get(str(screenshot.resolve()))
            items.append(_analyze_screenshot_path(screenshot, game_dir, case))

    analyzed = [item for item in items if item.issue is None]
    passed_count = sum(1 for item in analyzed if item.passed_expected is True)
    failed_count = sum(1 for item in analyzed if item.passed_expected is False)
    missing_count = sum(1 for item in items if item.issue == "missing_screenshot")
    low_confidence_count = sum(
        1
        for item in analyzed
        if item.confidence is not None and item.confidence < low_confidence_threshold
    )

    return RecognitionQualityReport(
        game_dir=str(game_dir),
        source=source,
        total_count=len(items),
        analyzed_count=len(analyzed),
        passed_count=passed_count,
        failed_count=failed_count,
        missing_count=missing_count,
        low_confidence_count=low_confidence_count,
        low_confidence_threshold=low_confidence_threshold,
        items=items,
    )


def _load_expected_cases(expected_path: Path, project_root: Path) -> list[ExpectedCase]:
    if not expected_path.exists():
        return []

    with expected_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    cases = data.get("cases", [])
    if not isinstance(cases, list):
        return []

    expected_cases: list[ExpectedCase] = []
    for item in cases:
        if not isinstance(item, dict):
            continue
        screenshot = item.get("screenshot")
        if not isinstance(screenshot, str) or not screenshot:
            continue
        expected_cases.append(
            ExpectedCase(
                case_id=item.get("case_id") if isinstance(item.get("case_id"), str) else None,
                screenshot=str(_resolve_screenshot_path(screenshot, project_root)),
                expected_screen_type=item.get("screen_type") if isinstance(item.get("screen_type"), str) else None,
                expected_template_id=item.get("template_id") if isinstance(item.get("template_id"), str) else None,
                sample_status=item.get("sample_status") if isinstance(item.get("sample_status"), str) else None,
            )
        )
    return expected_cases


def _resolve_screenshot_path(screenshot: str, project_root: Path) -> Path:
    path = Path(screenshot)
    if path.is_absolute():
        return path
    return project_root / path


def _analyze_expected_case(case: ExpectedCase, project_root: Path, game_dir: Path) -> RecognitionQualityItem:
    screenshot_path = _resolve_screenshot_path(case.screenshot, project_root)
    if not screenshot_path.is_file() or screenshot_path.suffix.lower() not in IMAGE_SUFFIXES:
        return RecognitionQualityItem(
            screenshot=str(screenshot_path),
            case_id=case.case_id,
            sample_status=case.sample_status,
            expected_screen_type=case.expected_screen_type,
            expected_template_id=case.expected_template_id,
            actual_screen_type=None,
            actual_template_id=None,
            confidence=None,
            fallback_reason=None,
            anchor_matches=[],
            passed_expected=False,
            issue="missing_screenshot",
        )
    return _analyze_screenshot_path(screenshot_path, game_dir, case)


def _analyze_screenshot_path(
    screenshot_path: Path,
    game_dir: Path,
    case: ExpectedCase | None,
) -> RecognitionQualityItem:
    data = analyze_screenshot(screenshot_path, game_dir).to_dict()
    screen = data["screen"]
    match = data["raw"]["match"]
    expected_screen_type = case.expected_screen_type if case else None
    expected_template_id = case.expected_template_id if case else None
    passed_expected = _passed_expected(
        expected_screen_type=expected_screen_type,
        expected_template_id=expected_template_id,
        actual_screen_type=str(screen["type"]),
        actual_template_id=str(screen["template_id"]),
    )

    return RecognitionQualityItem(
        screenshot=str(screenshot_path.resolve()),
        case_id=case.case_id if case else None,
        sample_status=case.sample_status if case else None,
        expected_screen_type=expected_screen_type,
        expected_template_id=expected_template_id,
        actual_screen_type=str(screen["type"]),
        actual_template_id=str(screen["template_id"]),
        confidence=float(screen["confidence"]),
        fallback_reason=match.get("fallback_reason"),
        anchor_matches=list(match.get("anchor_matches", [])),
        passed_expected=passed_expected,
    )


def _passed_expected(
    expected_screen_type: Optional[str],
    expected_template_id: Optional[str],
    actual_screen_type: str,
    actual_template_id: str,
) -> Optional[bool]:
    checks = []
    if expected_screen_type is not None:
        checks.append(expected_screen_type == actual_screen_type)
    if expected_template_id is not None:
        checks.append(expected_template_id == actual_template_id)
    if not checks:
        return None
    return all(checks)


def format_text_report(report: RecognitionQualityReport) -> str:
    lines = [
        "Recognition quality report",
        f"game_dir: {report.game_dir}",
        f"source: {report.source}",
        (
            f"analyzed: {report.analyzed_count}/{report.total_count}, "
            f"passed: {report.passed_count}, failed: {report.failed_count}, "
            f"missing: {report.missing_count}, "
            f"low_confidence(<{report.low_confidence_threshold:g}): {report.low_confidence_count}"
        ),
        "",
    ]

    for item in sorted(report.items, key=lambda item: _quality_sort_key(item, report.low_confidence_threshold)):
        status = _status_label(item)
        confidence = "-" if item.confidence is None else f"{item.confidence:.3f}"
        lines.append(f"- {Path(item.screenshot).name}: {status}")
        lines.append(
            "  "
            f"expected={item.expected_screen_type or '-'} / {item.expected_template_id or '-'}; "
            f"actual={item.actual_screen_type or '-'} / {item.actual_template_id or '-'}; "
            f"confidence={confidence}; fallback={item.fallback_reason or '-'}"
        )
        if item.anchor_matches:
            anchors = [
                (
                    f"{anchor.get('id')}: "
                    f"hamming={anchor.get('hamming_distance')}, score={anchor.get('score')}"
                )
                for anchor in item.anchor_matches
            ]
            lines.append("  anchors: " + "; ".join(anchors))
        if item.issue:
            lines.append(f"  issue: {item.issue}")

    return "\n".join(lines)


def _quality_sort_key(item: RecognitionQualityItem, low_confidence_threshold: float) -> tuple[int, float, str]:
    if item.issue:
        group = 0
    elif item.passed_expected is False:
        group = 1
    elif item.fallback_reason:
        group = 2
    elif item.confidence is not None and item.confidence < low_confidence_threshold:
        group = 3
    else:
        group = 4
    confidence = item.confidence if item.confidence is not None else -1.0
    return (group, confidence, item.screenshot)


def _status_label(item: RecognitionQualityItem) -> str:
    if item.issue:
        return "missing"
    if item.passed_expected is True:
        return "pass"
    if item.passed_expected is False:
        return "fail"
    return "no_expected"


def main() -> None:
    parser = argparse.ArgumentParser(description="Report screenshot recognition quality.")
    parser.add_argument("--game-dir", type=Path, default=default_game_dir())
    parser.add_argument("--samples-dir", type=Path)
    parser.add_argument("--expected-path", type=Path)
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        help="Analyze every image in a directory. Expected values are filled when the manifest references the same path.",
    )
    parser.add_argument("--low-confidence-threshold", type=float, default=0.6)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--jsonl", action="store_true", help="Print only item rows as JSON Lines.")
    args = parser.parse_args()

    report = build_quality_report(
        game_dir=args.game_dir,
        samples_dir=args.samples_dir,
        screenshot_dir=args.screenshot_dir,
        expected_path=args.expected_path,
        low_confidence_threshold=args.low_confidence_threshold,
    )

    if args.jsonl:
        for item in report.items:
            print(json.dumps(asdict(item), ensure_ascii=False))
    elif args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report))


if __name__ == "__main__":
    main()
