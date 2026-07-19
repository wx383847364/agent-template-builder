from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from agent_template_builder.ocr.paddle_engine import PaddleOCREngine


class FakePaddleOCR:
    def __init__(self) -> None:
        self.seen_size: tuple[int, int] | None = None

    def predict(self, image_path: str) -> list[dict[str, list[object]]]:
        with Image.open(image_path) as image:
            self.seen_size = image.size
        return [{"rec_texts": ["任务", "追踪"], "rec_scores": [0.9, 0.8]}]


def test_paddle_ocr_engine_crops_roi_and_parses_result(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (100, 80), color=(255, 255, 255)).save(image_path)
    fake_ocr = FakePaddleOCR()
    engine = PaddleOCREngine(ocr=fake_ocr)

    result = engine.read_region(image_path, (10, 15, 50, 45))

    assert fake_ocr.seen_size == (40, 30)
    assert result.text == "任务\n追踪"
    assert result.confidence == pytest.approx(0.85)


def test_paddle_ocr_engine_handles_empty_roi(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (100, 80), color=(255, 255, 255)).save(image_path)
    engine = PaddleOCREngine(ocr=FakePaddleOCR())

    result = engine.read_region(image_path, (50, 50, 10, 10))

    assert result.text == ""
    assert result.confidence == 0.0
