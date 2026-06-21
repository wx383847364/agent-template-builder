from pathlib import Path

from PIL import Image

from agent_template_builder.matcher.template_matcher import TemplateMatcher
from agent_template_builder.schema.templates import AnchorSpec, TemplateSpec


def _template(screen_type: str, priority: int, anchors: list[AnchorSpec]) -> TemplateSpec:
    return TemplateSpec(
        template_id=f"test_{screen_type}_v1",
        screen_type=screen_type,
        priority=priority,
        anchors=anchors,
        elements=[],
    )


def _screenshot(tmp_path: Path) -> Path:
    screenshot = tmp_path / "capture.png"
    Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(screenshot)
    return screenshot


def test_matcher_uses_nearest_expected_hash_variant(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
    actual_hash = "000000000000000f"
    matcher = TemplateMatcher(
        templates=[
            _template("reward_popup", 40, [
                AnchorSpec(
                    id="reward",
                    type="layout_region",
                    bbox=(0.0, 0.0, 1.0, 1.0),
                    expected_hash="ffffffffffffffff",
                    expected_hashes=("0000000000000000",),
                    max_hamming_distance=8,
                )
            ]),
            _template("main_world", 10, []),
        ],
        supported_sizes={(1280, 720)},
        aspect_profiles=[],
    )
    monkeypatch.setattr("agent_template_builder.matcher.template_matcher.region_hash", lambda _path, _bbox: actual_hash)

    result = matcher.match(screenshot)

    assert result.template.screen_type == "reward_popup"
    assert result.anchor_matches[0].expected_hash == "0000000000000000"
    assert result.anchor_matches[0].hamming_distance == 4


def test_matcher_falls_back_on_low_nonzero_anchor_score(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
    actual_hash = "000000000000007f"
    matcher = TemplateMatcher(
        templates=[
            _template("reward_popup", 40, [
                AnchorSpec(
                    id="reward",
                    type="layout_region",
                    bbox=(0.0, 0.0, 1.0, 1.0),
                    expected_hash="0000000000000000",
                    max_hamming_distance=8,
                )
            ]),
            _template("main_world", 10, []),
        ],
        supported_sizes={(1280, 720)},
        aspect_profiles=[],
    )
    monkeypatch.setattr("agent_template_builder.matcher.template_matcher.region_hash", lambda _path, _bbox: actual_hash)

    result = matcher.match(screenshot)

    assert result.template.screen_type == "main_world"
    assert result.confidence == 0.35
    assert result.fallback_reason == "low_anchor_score_match"
    assert result.anchor_matches[0].score > 0
