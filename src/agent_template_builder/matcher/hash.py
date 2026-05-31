from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image


def average_hash(image: Image.Image, hash_size: int = 8) -> str:
    """Return a compact average hash for quick local region comparisons."""
    gray = image.convert("L").resize((hash_size, hash_size))
    pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    bits = ["1" if pixel >= avg else "0" for pixel in pixels]
    return _bits_to_hex(bits)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def region_hash(path: Path, bbox: tuple[int, int, int, int]) -> str:
    with Image.open(path) as image:
        return average_hash(image.crop(bbox))


def hamming_distance(left: str, right: str) -> int:
    left_bits = _hex_to_bits(left)
    right_bits = _hex_to_bits(right)
    return sum(a != b for a, b in zip(left_bits, right_bits))


def _bits_to_hex(bits: Iterable[str]) -> str:
    bit_string = "".join(bits)
    return f"{int(bit_string, 2):0{len(bit_string) // 4}x}"


def _hex_to_bits(value: str) -> str:
    return f"{int(value, 16):0{len(value) * 4}b}"

