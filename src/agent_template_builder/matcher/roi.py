from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class GameView:
    bbox: BBox
    source: str

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


def detect_game_view(path: Path) -> GameView:
    """Return the gameplay viewport inside a screenshot.

    Native game screenshots use the full image. Windows window captures include
    browser-like chrome around the game surface, so the known client frame is
    removed before template bbox and anchor calculations.
    """
    with Image.open(path) as image:
        width, height = image.size
        if _looks_like_window_capture(image):
            return GameView((7, 78, width - 8, height - 6), "window_capture")
        return GameView((0, 0, width, height), "full_image")


def denormalize_bbox_in_view(
    bbox: tuple[float, float, float, float],
    view: GameView,
) -> BBox:
    left, top, right, bottom = bbox
    x0, y0, _, _ = view.bbox
    return (
        round(x0 + left * view.width),
        round(y0 + top * view.height),
        round(x0 + right * view.width),
        round(y0 + bottom * view.height),
    )


def _looks_like_window_capture(image: Image.Image) -> bool:
    width, height = image.size
    if width < 1200 or height < 900:
        return False

    top = image.crop((0, 0, width, min(40, height))).convert("RGB")
    pixels = list(top.getdata())
    avg_r = sum(pixel[0] for pixel in pixels) / len(pixels)
    avg_g = sum(pixel[1] for pixel in pixels) / len(pixels)
    avg_b = sum(pixel[2] for pixel in pixels) / len(pixels)
    return avg_b > avg_r + 20 and avg_b > avg_g + 5
