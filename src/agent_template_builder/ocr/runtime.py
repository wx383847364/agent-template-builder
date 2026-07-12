from __future__ import annotations

import argparse

from agent_template_builder.ocr.base import OCREngine


OCR_BACKENDS = ("none", "paddle")
OCR_DEVICES = ("auto", "gpu", "cpu")


class OCRConfigurationError(RuntimeError):
    pass


def add_ocr_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ocr",
        choices=OCR_BACKENDS,
        default="none",
        help="OCR backend. Defaults to none so PaddleOCR is only loaded explicitly.",
    )
    add_ocr_device_argument(parser)


def add_ocr_device_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ocr-device",
        choices=OCR_DEVICES,
        default="auto",
        help="PaddleOCR device. Auto prefers CUDA and otherwise uses CPU.",
    )


def _cuda_available() -> bool:
    try:
        import paddle
    except ModuleNotFoundError as exc:
        raise OCRConfigurationError(
            "PaddleOCR requires paddlepaddle and paddleocr. "
            "Install the local OCR environment before using --ocr paddle."
        ) from exc

    return bool(paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0)


def _resolve_device(device: str) -> str:
    if device == "cpu":
        return "cpu"

    cuda_available = _cuda_available()
    if device == "gpu":
        if not cuda_available:
            raise OCRConfigurationError(
                "--ocr-device gpu requires a CUDA-enabled PaddlePaddle installation and an available GPU. "
                "Use --ocr-device cpu or repair the local CUDA/Paddle environment."
            )
        return "gpu"
    if device == "auto":
        return "gpu" if cuda_available else "cpu"
    raise ValueError(f"unsupported OCR device: {device}")


def create_ocr_engine(backend: str, device: str = "auto") -> OCREngine | None:
    if backend == "none":
        return None
    if backend == "paddle":
        resolved_device = _resolve_device(device)
        try:
            from agent_template_builder.ocr.paddle_engine import PaddleOCREngine

            return PaddleOCREngine(device=resolved_device)
        except ModuleNotFoundError as exc:
            raise OCRConfigurationError(
                "PaddleOCR is not installed. Install paddleocr and a compatible PaddlePaddle build "
                "before using --ocr paddle."
            ) from exc
        except Exception as exc:
            raise OCRConfigurationError(
                f"failed to initialize PaddleOCR on {resolved_device}: {exc}"
            ) from exc
    raise ValueError(f"unsupported OCR backend: {backend}")


def create_ocr_engine_or_error(
    parser: argparse.ArgumentParser,
    backend: str,
    device: str,
) -> OCREngine | None:
    try:
        return create_ocr_engine(backend, device)
    except OCRConfigurationError as exc:
        parser.error(str(exc))
