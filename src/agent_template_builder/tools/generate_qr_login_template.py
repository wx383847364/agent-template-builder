"""Generate the padded QR-code target bbox for the QR-login template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


DEFAULT_QR_BBOX = (503, 448, 675, 619)
DEFAULT_SCREENSHOT_SIZE = (1920, 1080)
DEFAULT_PADDING_PIXELS = 50
DEFAULT_TEMPLATE_PATH = Path("configs/games/dhxy2_classic_pc/templates/qr_login.json")


def expand_bbox(
    bbox: tuple[int, int, int, int],
    padding_pixels: int,
    bounds: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Expand a full-screenshot bbox, clamped to screenshot bounds."""
    left, top, right, bottom = bbox
    min_left, min_top, max_right, max_bottom = bounds
    return (
        max(min_left, left - padding_pixels),
        max(min_top, top - padding_pixels),
        min(max_right, right + padding_pixels),
        min(max_bottom, bottom + padding_pixels),
    )


def normalize_screen_bbox(
    bbox: tuple[int, int, int, int],
    screenshot_size: tuple[int, int],
) -> list[float]:
    """Convert a full-screenshot bbox to full-screenshot ratio space."""
    left, top, right, bottom = bbox
    width, height = screenshot_size
    return [
        round(left / width, 9),
        round(top / height, 9),
        round(right / width, 9),
        round(bottom / height, 9),
    ]


def update_qr_target(template_path: Path, normalized_bbox: list[float]) -> None:
    """Replace the QR target full-screenshot bbox."""
    data = json.loads(template_path.read_text(encoding="utf-8"))
    for item in data.get("static_outputs", []):
        if item.get("id") == "qr_code_target":
            item["bbox"] = normalized_bbox
            template_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return
    raise ValueError(f"qr_code_target static output not found: {template_path}")


def _parse_bbox(values: Sequence[str]) -> tuple[int, int, int, int]:
    if len(values) != 4:
        raise argparse.ArgumentTypeError("bbox must contain left top right bottom")
    left, top, right, bottom = (int(value) for value in values)
    if left >= right or top >= bottom:
        raise argparse.ArgumentTypeError("bbox must satisfy left < right and top < bottom")
    return left, top, right, bottom


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a padded QR-login template bbox.")
    parser.add_argument("--qr-bbox", nargs=4, default=DEFAULT_QR_BBOX, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--screenshot-size", nargs=2, default=DEFAULT_SCREENSHOT_SIZE, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--padding", type=int, default=DEFAULT_PADDING_PIXELS, help="Pixels to expand on every side (default: 50).")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--write", action="store_true", help="Write the normalized bbox to qr_code_target.")
    args = parser.parse_args()

    qr_bbox = _parse_bbox(args.qr_bbox)
    screenshot_width, screenshot_height = (int(value) for value in args.screenshot_size)
    if screenshot_width <= 0 or screenshot_height <= 0:
        parser.error("--screenshot-size values must be positive")
    if args.padding < 0:
        parser.error("--padding must be non-negative")

    expanded_bbox = expand_bbox(qr_bbox, args.padding, (0, 0, screenshot_width, screenshot_height))
    normalized_bbox = normalize_screen_bbox(expanded_bbox, (screenshot_width, screenshot_height))
    if args.write:
        update_qr_target(args.template, normalized_bbox)

    print(
        json.dumps(
            {
                "qr_bbox": list(qr_bbox),
                "padding_pixels": args.padding,
                "expanded_bbox": list(expanded_bbox),
                "normalized_screen_bbox": normalized_bbox,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
