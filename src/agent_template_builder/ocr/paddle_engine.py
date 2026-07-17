from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from typing import Any

from PIL import Image

from agent_template_builder.ocr.base import OCRResult


class PaddleOCREngine:
    def __init__(
        self,
        *,
        device: str = "gpu",
        text_detection_model_name: str = "PP-OCRv5_mobile_det",
        text_recognition_model_name: str = "PP-OCRv5_mobile_rec",
        ocr: Any | None = None,
    ) -> None:
        self._cache_identity = ":".join(
            (
                "paddleocr",
                device,
                text_detection_model_name,
                text_recognition_model_name,
            )
        )
        self._inference_lock = RLock()
        self._ocr = ocr or self._create_ocr(
            device=device,
            text_detection_model_name=text_detection_model_name,
            text_recognition_model_name=text_recognition_model_name,
        )

    @property
    def cache_identity(self) -> str:
        return self._cache_identity

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        with Image.open(image_path) as image:
            crop = _crop_region(image, bbox)
            if crop is None:
                return OCRResult(text="", confidence=0.0)

            return self.read_image(crop)

    def read_image(self, image: Image.Image) -> OCRResult:
        with TemporaryDirectory(prefix="agent_template_builder_ocr_") as tmp_dir:
            crop_path = Path(tmp_dir) / "roi.png"
            image.save(crop_path)
            with self._inference_lock:
                raw_result = self._predict(crop_path)

        return _parse_result(raw_result)

    def _predict(self, image_path: Path) -> Any:
        if hasattr(self._ocr, "predict"):
            return self._ocr.predict(str(image_path))
        if hasattr(self._ocr, "ocr"):
            return self._ocr.ocr(str(image_path))
        raise TypeError("PaddleOCR object does not expose predict() or ocr().")

    @staticmethod
    def _create_ocr(
        *,
        device: str,
        text_detection_model_name: str,
        text_recognition_model_name: str,
    ) -> Any:
        from paddleocr import PaddleOCR

        return PaddleOCR(
            device=device,
            text_detection_model_name=text_detection_model_name,
            text_recognition_model_name=text_recognition_model_name,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )


def _crop_region(image: Image.Image, bbox: tuple[int, int, int, int]) -> Image.Image | None:
    left, top, right, bottom = bbox
    width, height = image.size
    left = max(0, min(left, width))
    top = max(0, min(top, height))
    right = max(0, min(right, width))
    bottom = max(0, min(bottom, height))
    if right <= left or bottom <= top:
        return None
    return image.crop((left, top, right, bottom))


def _parse_result(raw_result: Any) -> OCRResult:
    texts: list[str] = []
    scores: list[float] = []
    _collect_text_scores(raw_result, texts, scores)
    text = "\n".join(item for item in texts if item)
    confidence = sum(scores) / len(scores) if scores else 0.0
    return OCRResult(text=text, confidence=confidence)


def _collect_text_scores(raw: Any, texts: list[str], scores: list[float]) -> None:
    if raw is None:
        return

    if isinstance(raw, dict):
        rec_texts = raw.get("rec_texts")
        if isinstance(rec_texts, list):
            texts.extend(str(item) for item in rec_texts if item is not None)

        rec_scores = raw.get("rec_scores")
        if isinstance(rec_scores, list):
            scores.extend(float(item) for item in rec_scores if item is not None)

        if "text" in raw and raw["text"] is not None:
            texts.append(str(raw["text"]))
        if "confidence" in raw and raw["confidence"] is not None:
            scores.append(float(raw["confidence"]))
        if "score" in raw and raw["score"] is not None:
            scores.append(float(raw["score"]))

        for value in raw.values():
            if isinstance(value, (dict, list, tuple)):
                _collect_text_scores(value, texts, scores)
        return

    if isinstance(raw, (list, tuple)):
        if len(raw) >= 2 and isinstance(raw[0], str) and isinstance(raw[1], (float, int)):
            texts.append(raw[0])
            scores.append(float(raw[1]))
            return

        for item in raw:
            _collect_text_scores(item, texts, scores)
