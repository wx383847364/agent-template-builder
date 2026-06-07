from pathlib import Path

from PIL import Image

from agent_template_builder.matcher.roi import detect_game_view


def test_detects_window_capture_game_view(tmp_path: Path) -> None:
    screenshot = tmp_path / "window_capture.png"
    image = Image.new("RGB", (1554, 1174), color=(240, 240, 230))
    for y in range(40):
        for x in range(1554):
            image.putpixel((x, y), (90, 125, 165))
    image.save(screenshot)

    view = detect_game_view(screenshot)

    assert view.bbox == (7, 78, 1546, 1168)
    assert view.source == "window_capture"
    assert view.width == 1539
    assert view.height == 1090


def test_native_screenshot_uses_full_image(tmp_path: Path) -> None:
    screenshot = tmp_path / "native.png"
    Image.new("RGB", (800, 574), color=(10, 20, 30)).save(screenshot)

    view = detect_game_view(screenshot)

    assert view.bbox == (0, 0, 800, 574)
    assert view.source == "full_image"
