from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float


class OCREngine(Protocol):
    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        ...


class NullOCREngine:
    """Placeholder OCR engine used until PaddleOCR/Tesseract is wired in."""

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        return OCRResult(text="", confidence=0.0)

