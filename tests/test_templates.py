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
    assert {item["label"] for item in config["supported_aspect_ratios"]} >= {"wide_16_9"}
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
