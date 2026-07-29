from __future__ import annotations

from pathlib import Path
import argparse
import importlib.util
import json

from agent_template_builder.discovery.workflow import finalize_discovery
from agent_template_builder.ocr.base import OCREngine
from agent_template_builder.ocr.runtime import (
    OCRConfigurationError,
    add_ocr_device_argument,
    create_ocr_engine,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Codex-client model output and render DiscoveryData."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--input", type=Path, required=True, dest="model_output")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--ocr", choices=("auto", "none", "paddle"), default="auto")
    add_ocr_device_argument(parser)
    args = parser.parse_args()

    try:
        ocr_engine, warnings, status = _resolve_ocr(args.ocr, args.ocr_device)
    except OCRConfigurationError as exc:
        parser.error(str(exc))

    data_path, annotated_path, review_path = finalize_discovery(
        args.run_dir,
        model_output_path=args.model_output,
        draft=args.draft,
        ocr_engine=ocr_engine,
        extra_warnings=tuple(warnings),
        status=status,
    )
    print(
        json.dumps(
            {
                "discovery": str(data_path),
                "annotated": str(annotated_path),
                "review": str(review_path) if review_path else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _resolve_ocr(
    backend: str,
    device: str,
) -> tuple[OCREngine | None, list[str], str]:
    if backend == "none":
        return None, [], "complete"
    if backend == "auto":
        if (
            importlib.util.find_spec("paddle") is None
            or importlib.util.find_spec("paddleocr") is None
        ):
            return None, ["PaddleOCR unavailable; kept Codex text without OCR verification"], "complete"
        try:
            return create_ocr_engine("paddle", device), [], "complete"
        except OCRConfigurationError as exc:
            return None, [f"PaddleOCR auto initialization failed: {exc}"], "complete"
    return create_ocr_engine("paddle", device), [], "complete"


if __name__ == "__main__":
    main()
