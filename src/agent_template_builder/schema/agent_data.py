from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class Resolution:
    width: int
    height: int


@dataclass(frozen=True)
class Evidence:
    region_id: str
    source: str
    ocr_text: Optional[str] = None
    template_id: Optional[str] = None


@dataclass(frozen=True)
class Screen:
    type: str
    template_id: str
    confidence: float
    resolution: Resolution


@dataclass(frozen=True)
class Element:
    id: str
    type: str
    bbox: BBox
    confidence: float
    semantic_role: Optional[str] = None
    text: Optional[str] = None
    visible: bool = True
    evidence: Optional[Evidence] = None


@dataclass(frozen=True)
class TaskState:
    visible: bool
    text: Optional[str] = None
    confidence: float = 0.0
    evidence: Optional[Evidence] = None


@dataclass(frozen=True)
class RuntimeState:
    blocking_modal: bool
    available_intents: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentData:
    game: dict[str, str]
    screen: Screen
    elements: list[Element]
    state: RuntimeState
    task: Optional[TaskState] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
