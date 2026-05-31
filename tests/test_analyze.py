from pathlib import Path

from PIL import Image

from agent_template_builder.pipeline.analyze import analyze_screenshot


GAME_DIR = Path(__file__).resolve().parents[1] / "configs" / "games" / "dhxy2_classic_pc"


def test_analyze_accepts_same_ratio_different_resolution(tmp_path: Path) -> None:
    screenshot = tmp_path / "wide_1080p.png"
    Image.new("RGB", (1920, 1080), color=(10, 20, 30)).save(screenshot)

    result = analyze_screenshot(screenshot, GAME_DIR)
    data = result.to_dict()

    assert data["screen"]["type"] == "main_world"
    assert data["screen"]["confidence"] == 0.7
    assert data["screen"]["resolution"] == {"width": 1920, "height": 1080}
    assert data["raw"]["match"]["aspect_ratio_label"] == "wide_16_9"
    assert data["elements"][0]["bbox"] == (1382, 130, 1901, 475)


def test_analyze_penalizes_unknown_aspect_ratio(tmp_path: Path) -> None:
    screenshot = tmp_path / "odd_ratio.png"
    Image.new("RGB", (1000, 1000), color=(10, 20, 30)).save(screenshot)

    result = analyze_screenshot(screenshot, GAME_DIR)

    assert result.screen.confidence == 0.315
    assert result.raw["match"]["aspect_ratio_label"] is None
