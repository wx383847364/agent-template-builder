import json
from pathlib import Path

from agent_template_builder.tools.report_template_coverage import build_coverage_report


GAME_DIR = Path(__file__).resolve().parents[1] / "configs" / "games" / "dhxy2_classic_pc"


def test_reports_current_template_gaps() -> None:
    report = build_coverage_report(GAME_DIR)
    data = report.to_dict()

    assert data["template_count"] >= 1
    assert data["complete_count"] == 10
    sampled_and_calibrated = {
        "dhxy2_classic_main_world_v1",
        "dhxy2_classic_battle_v1",
        "dhxy2_classic_blocking_modal_v1",
        "dhxy2_classic_login_waterfall_v1",
        "dhxy2_classic_character_select_v1",
        "dhxy2_classic_server_select_v1",
        "dhxy2_classic_npc_dialog_v1",
        "dhxy2_classic_login_guard_v1",
        "dhxy2_classic_reward_popup_v1",
        "dhxy2_classic_system_panel_v1",
    }
    anchor_calibrated = sampled_and_calibrated | {
        "dhxy2_classic_character_select_v1",
        "dhxy2_classic_server_select_v1",
    }
    for item in data["templates"]:
        if item["template_id"] in sampled_and_calibrated:
            assert "screenshot_sample" not in item["missing"]
        if item["template_id"] in anchor_calibrated:
            assert "measurable_anchor" not in item["missing"]
            assert "expected_json" not in item["missing"]
    assert all(not item["missing"] for item in data["templates"])


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


def test_matches_expected_cases_from_single_manifest(tmp_path: Path) -> None:
    samples_dir = tmp_path / "samples"
    expected_dir = samples_dir / "expected"
    expected_dir.mkdir(parents=True)

    (expected_dir / "final_expected.json").write_text(
        """
        {
          "cases": [
            {
              "case_id": "main_world__baseline",
              "template_id": "dhxy2_classic_main_world_v1",
              "screen_type": "main_world"
            },
            {
              "case_id": "npc_dialog__baseline",
              "template_id": "dhxy2_classic_npc_dialog_v1",
              "screen_type": "npc_dialog"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    report = build_coverage_report(GAME_DIR, samples_dir)
    main_world = next(item for item in report.templates if item.screen_type == "main_world")
    npc_dialog = next(item for item in report.templates if item.screen_type == "npc_dialog")
    battle = next(item for item in report.templates if item.screen_type == "battle")

    assert main_world.expected_count == 1
    assert npc_dialog.expected_count == 1
    assert battle.expected_count == 0
    assert "expected_json" not in main_world.missing
    assert "expected_json" not in npc_dialog.missing
    assert "expected_json" in battle.missing


def test_counts_existing_screenshot_paths_from_expected_manifest(tmp_path: Path) -> None:
    samples_dir = tmp_path / "samples"
    expected_dir = samples_dir / "expected"
    screenshots_dir = samples_dir / "screenshots"
    expected_dir.mkdir(parents=True)
    screenshots_dir.mkdir(parents=True)
    screenshot = screenshots_dir / "timestamp_only.png"
    screenshot.write_bytes(b"not an image")

    (expected_dir / "final_expected.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "main_world__runtime",
                        "template_id": "dhxy2_classic_main_world_v1",
                        "screen_type": "main_world",
                        "screenshot": str(screenshot),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_coverage_report(GAME_DIR, samples_dir)
    main_world = next(item for item in report.templates if item.screen_type == "main_world")

    assert main_world.sample_count == 1
    assert "screenshot_sample" not in main_world.missing


def test_does_not_double_count_named_screenshot_referenced_by_manifest(tmp_path: Path) -> None:
    samples_dir = tmp_path / "samples"
    expected_dir = samples_dir / "expected"
    screenshots_dir = samples_dir / "screenshots"
    expected_dir.mkdir(parents=True)
    screenshots_dir.mkdir(parents=True)
    screenshot = screenshots_dir / "main_world__baseline.png"
    screenshot.write_bytes(b"not an image")

    (expected_dir / "final_expected.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "main_world__baseline",
                        "template_id": "dhxy2_classic_main_world_v1",
                        "screen_type": "main_world",
                        "screenshot": str(screenshot),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_coverage_report(GAME_DIR, samples_dir)
    main_world = next(item for item in report.templates if item.screen_type == "main_world")

    assert main_world.sample_count == 1
