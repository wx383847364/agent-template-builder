from pathlib import Path

from PIL import Image

from agent_template_builder.matcher.template_matcher import AspectRatioProfile, TemplateMatcher
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
        supported_sizes={(1280, 720): "fixed_window_1280x720"},
        aspect_profiles=[],
    )
    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, _bbox: actual_hash,
    )

    result = matcher.match(screenshot)

    assert result.template.screen_type == "reward_popup"
    assert result.anchor_matches[0].expected_hash == "0000000000000000"
    assert result.anchor_matches[0].hamming_distance == 4
    assert result.aspect_ratio_label == "fixed_window"
    assert result.viewport_profile_label == "fixed_window_1280x720"


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
        supported_sizes={(1280, 720): "fixed_window_1280x720"},
        aspect_profiles=[],
    )
    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, _bbox: actual_hash,
    )

    result = matcher.match(screenshot)

    assert result.template.screen_type == "main_world"
    assert result.confidence == 0.35
    assert result.fallback_reason == "low_anchor_score_match"
    assert result.anchor_matches[0].score > 0


def test_matcher_uses_profile_bbox_for_anchor_hash(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
    captured_bboxes = []
    matcher = TemplateMatcher(
        templates=[
            _template("reward_popup", 40, [
                AnchorSpec(
                    id="reward",
                    type="layout_region",
                    bbox=(0.0, 0.0, 1.0, 1.0),
                    bbox_by_profile={"fixed_window_1280x720": (0.0, 0.0, 0.5, 0.5)},
                    expected_hash="0000000000000000",
                    max_hamming_distance=8,
                )
            ]),
            _template("main_world", 10, []),
        ],
        supported_sizes={(1280, 720): "fixed_window_1280x720"},
        aspect_profiles=[],
    )

    def fake_region_hash(_image: Image.Image, bbox: tuple[int, int, int, int]) -> str:
        captured_bboxes.append(bbox)
        return "0000000000000000"

    monkeypatch.setattr("agent_template_builder.matcher.template_matcher.region_hash_image", fake_region_hash)

    result = matcher.match(screenshot)

    assert result.template.screen_type == "reward_popup"
    assert captured_bboxes == [(0, 0, 640, 360)]


def test_matcher_accepts_legacy_supported_size_set(tmp_path: Path, monkeypatch) -> None:
    screenshot = _screenshot(tmp_path)
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
    monkeypatch.setattr(
        "agent_template_builder.matcher.template_matcher.region_hash_image",
        lambda _image, _bbox: "0000000000000000",
    )

    result = matcher.match(screenshot)

    assert result.template.screen_type == "reward_popup"
    assert result.aspect_ratio_label == "fixed_window"
    assert result.viewport_profile_label == "fixed_window"


def test_viewport_profile_selects_bbox_without_supported_size_score(
    tmp_path: Path,
    monkeypatch,
) -> None:
    screenshot = tmp_path / "legacy.png"
    Image.new("RGB", (1203, 872), color=(10, 20, 30)).save(screenshot)
    captured_bboxes = []
    matcher = TemplateMatcher(
        templates=[
            _template("reward_popup", 40, [
                AnchorSpec(
                    id="reward",
                    type="layout_region",
                    bbox=(0.0, 0.0, 1.0, 1.0),
                    bbox_by_profile={
                        "legacy_window_capture_1203x872": (0.0, 0.0, 0.5, 0.5)
                    },
                    expected_hash="0000000000000000",
                    max_hamming_distance=8,
                )
            ]),
            _template("main_world", 10, []),
        ],
        supported_sizes={(1280, 720): "fixed_window_1280x720"},
        aspect_profiles=[
            AspectRatioProfile(
                label="classic_windowed_client",
                ratio=800 / 574,
                tolerance=0.04,
            )
        ],
        viewport_profiles={(1203, 872): "legacy_window_capture_1203x872"},
    )

    def fake_region_hash(_image: Image.Image, bbox: tuple[int, int, int, int]) -> str:
        captured_bboxes.append(bbox)
        return "0000000000000000"

    monkeypatch.setattr("agent_template_builder.matcher.template_matcher.region_hash_image", fake_region_hash)

    result = matcher.match(screenshot)

    assert result.template.screen_type == "reward_popup"
    assert result.aspect_ratio_label == "classic_windowed_client"
    assert result.viewport_profile_label == "legacy_window_capture_1203x872"
    assert result.confidence < 0.9
    assert captured_bboxes == [(0, 0, 602, 436)]


def test_path_and_image_matcher_entrypoints_are_equivalent(tmp_path: Path) -> None:
    screenshot = _screenshot(tmp_path)
    matcher = TemplateMatcher(
        templates=[_template("main_world", 10, [])],
        supported_sizes={(1280, 720): "fixed_window_1280x720"},
        aspect_profiles=[],
    )

    path_result = matcher.match(screenshot)
    with Image.open(screenshot) as image:
        image_result = matcher.match_image(image)

    assert image_result == path_result
