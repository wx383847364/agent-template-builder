from pathlib import Path
from base64 import b64decode

import pytest
from PIL import Image

from agent_template_builder.matcher.template_matcher import TemplateMatcher, UnsupportedResolutionError
from agent_template_builder.schema.templates import AnchorSpec, TemplateSpec, load_game_config, load_templates


RESOLUTION = (1920, 1080)
WINDOW_BBOX = (143, 95, 1177, 878)


def _template(
    screen_type: str,
    priority: int,
    anchor: AnchorSpec,
    *,
    confirmed: bool = True,
    calibration_mode: str = "template_anchor",
) -> TemplateSpec:
    return TemplateSpec(
        template_id=f"test_{screen_type}_v1",
        screen_type=screen_type,
        priority=priority,
        anchors=[anchor],
        elements=[],
        calibration_status="confirmed_1920" if confirmed else "pending_1920_calibration",
        calibration_mode=calibration_mode,
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


@pytest.mark.parametrize("offset", [(40, 0), (-20, 12)])
def test_matcher_exhaustive_fallback_recovers_non_grid_offset(tmp_path: Path, monkeypatch, offset: tuple[int, int]) -> None:
    resolution = (100, 80)
    screenshot = _screenshot(tmp_path, resolution)
    anchor = AnchorSpec("anchor", "layout_region", (0.4, 0.1, 0.5, 0.2), expected_hash="0" * 16)
    base_bbox = (40, 8, 50, 16)
    expected_bbox = tuple(value + delta for value, delta in zip(base_bbox, (*offset, *offset)))
    matcher = TemplateMatcher(
        [_template("server_select", 40, anchor)],
        resolution=resolution,
        reference_window_bbox=(0, 0, 50, 50) if offset[0] >= 0 else (20, 0, 80, 50),
    )
    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, bbox: "0" * 16 if bbox == expected_bbox else "f" * 16,
    )

    result = matcher.match(screenshot)

    assert result.calibration.offset == offset


def test_window_probe_beats_a_decoy_coarse_template_for_non_grid_offset(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
    offset = (40, 0)
    probe_bbox = (143, 95, 1177, 126)
    true_anchor = AnchorSpec("true", "layout_region", (0.2, 0.2, 0.3, 0.3), expected_hash="1" * 16)
    decoy_anchor = AnchorSpec("decoy", "layout_region", (0.4, 0.2, 0.5, 0.3), expected_hash="2" * 16)
    true_bbox = (384 + offset[0], 216, 576 + offset[0], 324)

    def fake_hash(_image, bbox):
        if bbox == tuple(value + delta for value, delta in zip(probe_bbox, (*offset, *offset))):
            return "0" * 16
        if bbox == true_bbox:
            return "1" * 16
        if bbox == (768, 216, 960, 324):
            return "2" * 16
        return "f" * 16

    monkeypatch.setattr("agent_template_builder.matcher.template_matcher.region_hash_image", fake_hash)
    matcher = TemplateMatcher(
        [
            _template("server_select", 10, true_anchor, calibration_mode="window_center"),
            _template("decoy", 99, decoy_anchor),
        ],
        resolution=RESOLUTION,
        reference_window_bbox=WINDOW_BBOX,
        window_probe_bbox=probe_bbox,
        window_probe_hashes=("0" * 16,),
    )

    result = matcher.match(screenshot)

    assert result.template.screen_type == "server_select"
    assert result.calibration.offset == offset


@pytest.mark.parametrize("offset", [(40, 0), (-20, 12)])
def test_real_window_probe_recovers_non_grid_shift(offset: tuple[int, int]) -> None:
    root = Path(__file__).resolve().parents[1]
    game_dir = root / "configs/games/dhxy2_classic_pc"
    calibration = load_game_config(game_dir)["window_calibration"]
    matcher = TemplateMatcher(
        load_templates(game_dir),
        resolution=RESOLUTION,
        reference_window_bbox=tuple(calibration["reference_window_bbox"]),
        window_probe_bbox=tuple(calibration["probe_bbox"]),
        window_probe_pixels=tuple(b64decode(value) for value in calibration["probe_pixels_base64"]),
    )
    with Image.open(root / "samples/dhxy2_classic_pc/screenshots/登陆界面服务器选择界面1920x1080.png") as source:
        shifted = Image.new("RGB", RESOLUTION)
        shifted.paste(source, offset)

    result = matcher.match_image(shifted)

    assert result.template.screen_type == "server_select"
    assert result.calibration.status == "calibrated"
    assert result.calibration.offset == offset
