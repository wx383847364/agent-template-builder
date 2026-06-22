from pathlib import Path
import json

from PIL import Image

from agent_template_builder.tools.report_recognition_quality import (
    RecognitionQualityItem,
    RecognitionQualityReport,
    build_quality_report,
    format_text_report,
)


GAME_DIR = Path(__file__).resolve().parents[1] / "configs" / "games" / "dhxy2_classic_pc"
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "dhxy2_classic_pc"


def test_reports_repository_sample_quality() -> None:
    report = build_quality_report(GAME_DIR)

    login_waterfall = next(item for item in report.items if item.case_id == "login_waterfall__manual_login1")
    main_world = next(item for item in report.items if item.case_id == "main_world__baseline")
    reward = next(item for item in report.items if item.case_id == "reward_popup__manual_summon_reward1")
    blocking = next(item for item in report.items if item.case_id == "blocking_modal__baseline")

    assert main_world.actual_screen_type == "main_world"
    assert main_world.passed_expected is True
    assert main_world.confidence is not None
    assert main_world.confidence >= 0.6
    assert reward.expected_screen_type == "reward_popup"
    assert reward.actual_screen_type == "reward_popup"
    assert reward.passed_expected is True
    assert reward.anchor_matches
    assert login_waterfall.confidence is not None
    assert login_waterfall.confidence >= 0.6
    assert blocking.confidence == 0.79


def test_reports_directory_items_without_expected(tmp_path: Path) -> None:
    screenshot = tmp_path / "runtime.png"
    Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(screenshot)

    report = build_quality_report(GAME_DIR, samples_dir=SAMPLES_DIR, screenshot_dir=tmp_path)

    assert report.total_count == 1
    assert report.items[0].screenshot == str(screenshot.resolve())
    assert report.items[0].expected_screen_type is None
    assert report.items[0].passed_expected is None


def test_matches_directory_items_to_expected_manifest(tmp_path: Path) -> None:
    screenshot = tmp_path / "runtime.png"
    Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(screenshot)
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "runtime",
                        "screenshot": str(screenshot),
                        "screen_type": "main_world",
                        "template_id": "dhxy2_classic_main_world_v1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_quality_report(
        GAME_DIR,
        samples_dir=SAMPLES_DIR,
        screenshot_dir=tmp_path,
        expected_path=expected_path,
    )

    assert report.items[0].case_id == "runtime"
    assert report.items[0].passed_expected is True


def test_text_report_sorting_uses_configured_low_confidence_threshold() -> None:
    report = RecognitionQualityReport(
        game_dir="game",
        source="source",
        total_count=2,
        analyzed_count=2,
        passed_count=0,
        failed_count=0,
        missing_count=0,
        low_confidence_count=1,
        low_confidence_threshold=0.8,
        items=[
            RecognitionQualityItem(
                screenshot="high.png",
                case_id=None,
                sample_status=None,
                expected_screen_type=None,
                expected_template_id=None,
                actual_screen_type="main_world",
                actual_template_id="main",
                confidence=0.9,
                fallback_reason=None,
                anchor_matches=[],
                passed_expected=None,
            ),
            RecognitionQualityItem(
                screenshot="low.png",
                case_id=None,
                sample_status=None,
                expected_screen_type=None,
                expected_template_id=None,
                actual_screen_type="main_world",
                actual_template_id="main",
                confidence=0.7,
                fallback_reason=None,
                anchor_matches=[],
                passed_expected=None,
            ),
        ],
    )

    text = format_text_report(report)

    assert text.index("- low.png") < text.index("- high.png")
