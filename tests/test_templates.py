from pathlib import Path
import pytest

from agent_template_builder.schema.templates import denormalize_bbox, load_game_config, load_templates
from agent_template_builder.schema.templates import _load_template


GAME_DIR = Path(__file__).resolve().parents[1] / "configs" / "games" / "dhxy2_classic_pc"


def test_load_game_config() -> None:
    config = load_game_config(GAME_DIR)

    assert config["game_id"] == "dhxy2"
    assert config["client"] == "classic_pc"
    assert config["coordinate_space"]["bbox_unit"] == "screen_ratio"
    assert config["runtime_screenshot"] == {"width": 1920, "height": 1080}
    assert config["window_calibration"]["reference_window_bbox"] == [143, 95, 1177, 878]
    assert config["ocr_policy"]["only_when_required"] is True


def test_load_templates_by_priority() -> None:
    templates = load_templates(GAME_DIR)

    assert [template.template_id for template in templates]
    assert templates[0].priority >= templates[-1].priority
    assert any(element.ocr_required for template in templates for element in template.elements)


def test_denormalize_bbox() -> None:
    assert denormalize_bbox((0.5, 0.0, 1.0, 1.0), 1280, 720) == (640, 0, 1280, 720)


def test_anchor_supports_multiple_expected_hashes() -> None:
    templates = load_templates(GAME_DIR)
    reward = next(template for template in templates if template.screen_type == "reward_popup")
    notice = next(anchor for anchor in reward.anchors if anchor.id == "reward_notice_area")

    assert notice.measurable_hashes == ("f7fefec1fdc0e000", "fffe008000000000")


def test_template_loads_static_outputs() -> None:
    templates = load_templates(GAME_DIR)
    server_select = next(template for template in templates if template.screen_type == "server_select")
    login_waterfall = next(template for template in templates if template.screen_type == "login_waterfall")

    ids = {item.id for item in server_select.static_outputs}

    assert {"account_server_slot_1", "selected_server_slot"}.issubset(ids)
    assert any(item.semantic_role == "confirm_server" and item.text == "进入游戏" for item in server_select.static_outputs)
    assert any(
        item.semantic_role == "start_game_button"
        and item.text == "开始游戏"
        and item.bbox == (0.703125, 0.592592593, 0.765625, 0.703703704)
        for item in login_waterfall.static_outputs
    )


def test_template_loads_full_screenshot_bboxes_and_calibration_status() -> None:
    templates = load_templates(GAME_DIR)
    confirmed = {template.screen_type for template in templates if template.calibration_status == "confirmed_1920"}

    assert confirmed == {"login_waterfall", "qr_login", "server_select", "character_select"}
    assert all(template.calibration_status in {"confirmed_1920", "pending_1920_calibration"} for template in templates)


def test_rejects_invalid_expected_hashes_shape(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "template_id": "test_template",
          "screen_type": "test",
          "anchors": [
            {
              "id": "bad_anchor",
              "type": "layout_region",
              "bbox": [0, 0, 1, 1],
              "expected_hashes": "not-a-list"
            }
          ],
          "elements": []
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected_hashes must be a list"):
        _load_template(template_path)


def test_rejects_static_output_without_text_or_value(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "template_id": "test_template",
          "screen_type": "test",
          "static_outputs": [
            {
              "id": "bad_static",
              "type": "button",
              "semantic_role": "confirm"
            }
          ],
          "elements": []
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="text or value is required"):
        _load_template(template_path)
