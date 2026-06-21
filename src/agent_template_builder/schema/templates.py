from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
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
class TemplateSpec:
    template_id: str
    screen_type: str
    priority: int
    anchors: list[AnchorSpec]
    elements: list[ElementSpec]
    available_intents: list[str] = field(default_factory=list)
    blocking_modal: bool = False
    description: str = ""

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
            bbox=tuple(item["bbox"]),
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
            bbox=tuple(item["bbox"]),
            ocr_required=bool(item.get("ocr_required", False)),
            semantic_role=item.get("semantic_role"),
        )
        for item in data.get("elements", [])
    ]
    return TemplateSpec(
        template_id=data["template_id"],
        screen_type=data["screen_type"],
        priority=int(data.get("priority", 0)),
        anchors=anchors,
        elements=elements,
        available_intents=list(data.get("available_intents", [])),
        blocking_modal=bool(data.get("blocking_modal", False)),
        description=data.get("description", ""),
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
