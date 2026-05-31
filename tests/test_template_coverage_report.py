from pathlib import Path

from agent_template_builder.tools.report_template_coverage import build_coverage_report


GAME_DIR = Path(__file__).resolve().parents[1] / "configs" / "games" / "dhxy2_classic_pc"


def test_reports_current_template_gaps() -> None:
    report = build_coverage_report(GAME_DIR)
    data = report.to_dict()

    assert data["template_count"] >= 1
    assert data["complete_count"] == 0
    assert any(
        "screenshot_sample" in item["missing"] and "expected_json" in item["missing"]
        for item in data["templates"]
    )


def test_matches_samples_and_expected_by_template_or_screen_type(tmp_path: Path) -> None:
    samples_dir = tmp_path / "samples"
    screenshots_dir = samples_dir / "screenshots"
    expected_dir = samples_dir / "expected"
    screenshots_dir.mkdir(parents=True)
    expected_dir.mkdir(parents=True)

    (screenshots_dir / "dhxy2_classic_battle_v1__local.png").write_bytes(b"not an image")
    (expected_dir / "battle__local.json").write_text("{}", encoding="utf-8")

    report = build_coverage_report(GAME_DIR, samples_dir)
    battle = next(item for item in report.templates if item.screen_type == "battle")

    assert battle.sample_count == 1
    assert battle.expected_count == 1
    assert "screenshot_sample" not in battle.missing
    assert "expected_json" not in battle.missing
