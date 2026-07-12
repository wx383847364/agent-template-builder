"""OCR interfaces and implementations."""

from agent_template_builder.ocr.base import NullOCREngine, OCREngine, OCRResult
from agent_template_builder.ocr.paddle_engine import PaddleOCREngine

__all__ = ["NullOCREngine", "OCREngine", "OCRResult", "PaddleOCREngine"]
