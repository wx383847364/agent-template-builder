from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from numbers import Real
from typing import Any, Optional
import json


NormalizedBBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class AnchorSpec:
    id: str
    type: str
    bbox: NormalizedBBox
    weight: float = 1.0
    expected_hash: Optional[str] = None
    expected_hashes: tuple[str, ...] = ()
    max_hamming_distance: int = 8

    @property
    def measurable_hashes(self) -> tuple[str, ...]:
        hashes = []
        if self.expected_hash:
            hashes.append(self.expected_hash)
        hashes.extend(item for item in self.expected_hashes if item)
        return tuple(dict.fromkeys(hashes))



@dataclass(frozen=True)
class ElementSpec:
    id: str
    type: str
    bbox: NormalizedBBox
    ocr_required: bool
    semantic_role: Optional[str] = None


@dataclass(frozen=True)
class StaticOutputSpec:
    id: str
    type: str
    semantic_role: str
    text: Optional[str] = None
    value: Optional[str] = None
    bbox: Optional[NormalizedBBox] = None


@dataclass(frozen=True)
class TemplateSpec:
    template_id: str
    screen_type: str
    priority: int
    anchors: list[AnchorSpec]
    elements: list[ElementSpec]
    static_outputs: list[StaticOutputSpec] = field(default_factory=list)
    available_intents: list[str] = field(default_factory=list)
    blocking_modal: bool = False
    description: str = ""
    calibration_status: str = "pending_1920_calibration"

    @property
    def measurable_anchor_count(self) -> int:
        return sum(1 for anchor in self.anchors if anchor.measurable_hashes)


def load_game_config(game_dir: Path) -> dict[str, Any]:
    with (game_dir / "game.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_templates(game_dir: Path) -> list[TemplateSpec]:
    templates_dir = game_dir / "templates"
    specs = [_load_template(path) for path in sorted(templates_dir.glob("*.json"))]
    return sorted(specs, key=lambda spec: spec.priority, reverse=True)


def denormalize_bbox(bbox: NormalizedBBox, width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    return (
        round(left * width),
        round(top * height),
        round(right * width),
        round(bottom * height),
    )


def _load_template(path: Path) -> TemplateSpec:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    anchors = [
        AnchorSpec(
            id=item["id"],
            type=item["type"],
            bbox=_load_normalized_bbox(item, "bbox"),
            weight=float(item.get("weight", 1.0)),
            expected_hash=item.get("expected_hash"),
            expected_hashes=_load_expected_hashes(item),
            max_hamming_distance=int(item.get("max_hamming_distance", 8)),
        )
        for item in data.get("anchors", [])
    ]
    elements = [
        ElementSpec(
            id=item["id"],
            type=item["type"],
            bbox=_load_normalized_bbox(item, "bbox"),
            ocr_required=bool(item.get("ocr_required", False)),
            semantic_role=item.get("semantic_role"),
        )
        for item in data.get("elements", [])
    ]
    static_outputs = [_load_static_output(item) for item in data.get("static_outputs", [])]
    return TemplateSpec(
        template_id=data["template_id"],
        screen_type=data["screen_type"],
        priority=int(data.get("priority", 0)),
        anchors=anchors,
        elements=elements,
        static_outputs=static_outputs,
        available_intents=list(data.get("available_intents", [])),
        blocking_modal=bool(data.get("blocking_modal", False)),
        description=data.get("description", ""),
        calibration_status=str(data.get("calibration_status", "pending_1920_calibration")),
    )


def _load_expected_hashes(anchor: dict[str, Any]) -> tuple[str, ...]:
    expected_hashes = anchor.get("expected_hashes", [])
    if expected_hashes is None:
        return ()
    if not isinstance(expected_hashes, list):
        raise ValueError(f"anchor {anchor.get('id', '<unknown>')}: expected_hashes must be a list")
    if not all(isinstance(item, str) for item in expected_hashes):
        raise ValueError(f"anchor {anchor.get('id', '<unknown>')}: expected_hashes items must be strings")
    return tuple(expected_hashes)


def _load_static_output(item: dict[str, Any]) -> StaticOutputSpec:
    if "text" not in item and "value" not in item:
        raise ValueError(f"static_output {item.get('id', '<unknown>')}: text or value is required")

    bbox = item.get("bbox")
    if bbox is not None:
        bbox = _load_normalized_bbox(item, "bbox")

    return StaticOutputSpec(
        id=item["id"],
        type=item["type"],
        semantic_role=item["semantic_role"],
        text=item.get("text"),
        value=item.get("value"),
        bbox=bbox,
    )


def _load_normalized_bbox(item: dict[str, Any], field_name: str) -> NormalizedBBox:
    bbox = item.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(f"{item.get('id', '<unknown>')}: {field_name} must be a bbox array")
    if not all(isinstance(value, Real) and not isinstance(value, bool) for value in bbox):
        raise ValueError(f"{item.get('id', '<unknown>')}: {field_name} values must be numbers")

    left, top, right, bottom = (float(value) for value in bbox)
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError(f"{item.get('id', '<unknown>')}: {field_name} must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1")
    return (left, top, right, bottom)
