from pathlib import Path
import json

import pytest
from PIL import Image

from agent_template_builder.matcher.template_matcher import UnsupportedResolutionError
from agent_template_builder.pipeline.analyze import analyze_screenshot
from agent_template_builder.pipeline.export_agent_rows import export_agent_rows, to_index_value_data


ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "configs" / "games" / "dhxy2_classic_pc"
SAMPLES_DIR = ROOT / "samples" / "dhxy2_classic_pc" / "screenshots"


def test_analyze_rejects_non_1920x1080_input(tmp_path: Path) -> None:
    screenshot = tmp_path / "legacy.png"
    Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(screenshot)

    with pytest.raises(UnsupportedResolutionError, match="unsupported_resolution"):
        analyze_screenshot(screenshot, GAME_DIR)


def test_qr_login_uses_calibrated_full_screenshot_bbox() -> None:
    result = analyze_screenshot(SAMPLES_DIR / "登陆二维码扫码界面.png", GAME_DIR)
    qr_target = next(element for element in result.elements if element.id == "qr_code_target")

    assert result.screen.type == "qr_login"
    assert qr_target.bbox == (453, 398, 725, 669)
    assert result.raw["calibration"]["status"] == "calibrated"
    assert result.raw["calibration"]["offset"] == [0, 0]
    assert "game_view" not in result.raw


def test_server_select_uses_calibrated_full_screenshot_bboxes() -> None:
    result = analyze_screenshot(SAMPLES_DIR / "登陆界面服务器选择界面1920x1080.png", GAME_DIR)
    elements = {element.id: element for element in result.elements}

    assert result.screen.type == "server_select"
    assert result.raw["calibration"]["status"] == "calibrated"
    assert elements["account_servers"].bbox == (182, 313, 925, 351)
    assert elements["selected_server_slot"].bbox == (465, 738, 575, 773)
    assert elements["account_server_slot_1"].bbox == (187, 316, 299, 348)
    assert elements["server_confirm_button"].bbox == (582, 741, 667, 771)


def test_analyze_translates_all_output_bboxes_and_export_marks_large_offset(tmp_path: Path, monkeypatch) -> None:
    game_dir = tmp_path / "game"
    templates_dir = game_dir / "templates"
    templates_dir.mkdir(parents=True)
    (game_dir / "game.json").write_text(
        json.dumps(
            {
                "game_id": "test_game",
                "client": "test_client",
                "runtime_screenshot": {"width": 1920, "height": 1080},
                "window_calibration": {"reference_window_bbox": [143, 95, 1177, 878]},
                "template_defaults": {"min_confidence": 0.65},
                "ocr_policy": {"only_when_required": True},
            }
        ),
        encoding="utf-8",
    )
    (templates_dir / "screen.json").write_text(
        json.dumps(
            {
                "template_id": "test_screen_v1",
                "screen_type": "test_screen",
                "priority": 50,
                "calibration_status": "confirmed_1920",
                "anchors": [{"id": "anchor", "type": "layout_region", "bbox": [0.1, 0.1, 0.2, 0.2], "expected_hash": "0" * 16}],
                "elements": [{"id": "region", "type": "text_region", "bbox": [0.2, 0.2, 0.3, 0.3], "ocr_required": False}],
                "static_outputs": [{"id": "start", "type": "button", "semantic_role": "start_game_button", "text": "开始", "bbox": [0.3, 0.3, 0.4, 0.4]}],
            }
        ),
        encoding="utf-8",
    )
    screenshot = tmp_path / "capture.png"
    Image.new("RGB", (1920, 1080), color=(10, 20, 30)).save(screenshot)
    expected_anchor = (224, 140, 416, 248)
    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, bbox: "0" * 16 if bbox == expected_anchor else "f" * 16,
    )

    result = analyze_screenshot(screenshot, game_dir)
    rows = to_index_value_data(export_agent_rows(screenshot, game_dir, ROOT / "agent_fields.json"))

    assert result.raw["calibration"]["offset"] == [32, 32]
    assert result.elements[0].bbox == (416, 248, 608, 356)
    assert result.elements[1].bbox == (608, 356, 800, 464)
    assert rows["303"] == "开始@[608, 356, 800, 464]"
    assert rows["9000"] == "window_center_offset@[32, 32]"


def test_character_select_uses_calibrated_full_screenshot_bboxes() -> None:
    result = analyze_screenshot(SAMPLES_DIR / "登陆界面选择角色界面-1920x1080.png", GAME_DIR)
    elements = {element.id: element for element in result.elements}

    assert result.screen.type == "character_select"
    assert result.raw["calibration"]["status"] == "calibrated"
    assert result.raw["calibration"]["offset"] == [0, 0]
    assert elements["character_grid"].bbox == (951, 324, 1174, 464)
    assert elements["character_slot_1"].bbox == (951, 324, 1174, 391)
    assert elements["character_slot_2"].bbox == (988, 399, 1174, 464)
    assert elements["enter_game_button"].bbox == (606, 723, 745, 758)
