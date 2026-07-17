from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float


class OCREngine(Protocol):
    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        ...


class ImageOCREngine(OCREngine, Protocol):
    cache_identity: str

    def read_image(self, image: Image.Image) -> OCRResult:
        ...


class NullOCREngine:
    """在接入 PaddleOCR/Tesseract 之前使用的占位 OCR 引擎。"""

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        return OCRResult(text="", confidence=0.0)

    def read_image(self, image: Image.Image) -> OCRResult:
        return OCRResult(text="", confidence=0.0)
