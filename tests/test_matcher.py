from pathlib import Path

import pytest
from PIL import Image

from agent_template_builder.matcher.template_matcher import TemplateMatcher, UnsupportedResolutionError
from agent_template_builder.schema.templates import AnchorSpec, TemplateSpec


RESOLUTION = (1920, 1080)
WINDOW_BBOX = (143, 95, 1177, 878)


def _template(screen_type: str, priority: int, anchor: AnchorSpec, *, confirmed: bool = True) -> TemplateSpec:
    return TemplateSpec(
        template_id=f"test_{screen_type}_v1",
        screen_type=screen_type,
        priority=priority,
        anchors=[anchor],
        elements=[],
        calibration_status="confirmed_1920" if confirmed else "pending_1920_calibration",
    )


def _matcher(*templates: TemplateSpec) -> TemplateMatcher:
    return TemplateMatcher(
        list(templates),
        resolution=RESOLUTION,
        reference_window_bbox=WINDOW_BBOX,
    )


def _screenshot(tmp_path: Path, size: tuple[int, int] = RESOLUTION) -> Path:
    screenshot = tmp_path / "capture.png"
    Image.new("RGB", size, color=(10, 20, 30)).save(screenshot)
    return screenshot


def test_matcher_calibrates_common_anchor_translation(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
    anchor = AnchorSpec(
        id="anchor",
        type="layout_region",
        bbox=(0.1, 0.1, 0.2, 0.2),
        expected_hash="0000000000000000",
    )
    expected_bbox = (224, 140, 416, 248)  # Baseline bbox translated by (+32, +32).

    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, bbox: "0000000000000000" if bbox == expected_bbox else "ffffffffffffffff",
    )

    result = _matcher(_template("server_select", 40, anchor)).match(screenshot)

    assert result.template.screen_type == "server_select"
    assert result.calibration.status == "calibrated"
    assert result.calibration.offset == (32, 32)
    assert result.calibration.actual_center == (692.0, 518.5)
    assert result.anchor_matches[0].hamming_distance == 0


def test_matcher_marks_pending_template_as_not_exportable(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
    anchor = AnchorSpec("anchor", "layout_region", (0.1, 0.1, 0.2, 0.2), expected_hash="0" * 16)
    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, _bbox: "0" * 16,
    )

    result = _matcher(_template("battle", 40, anchor, confirmed=False)).match(screenshot)

    assert result.calibration.status == "pending"
    assert result.calibration.reason == "template_not_1920_calibrated"


def test_matcher_marks_missing_anchor_match_as_failure(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
    anchor = AnchorSpec("anchor", "layout_region", (0.1, 0.1, 0.2, 0.2), expected_hash="0" * 16)
    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, _bbox: "f" * 16,
    )

    result = _matcher(_template("battle", 40, anchor)).match(screenshot)

    assert result.calibration.status == "failed"
    assert result.calibration.reason == "no_anchor_hash_match"


def test_matcher_rejects_non_1920x1080_input(tmp_path: Path) -> None:
    screenshot = _screenshot(tmp_path, (1280, 720))
    anchor = AnchorSpec("anchor", "layout_region", (0.1, 0.1, 0.2, 0.2), expected_hash="0" * 16)

    with pytest.raises(UnsupportedResolutionError, match="unsupported_resolution"):
        _matcher(_template("battle", 40, anchor)).match(screenshot)
