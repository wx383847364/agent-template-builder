from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class AgentField:
    index: int
    key: str
    type: str
    description: str


@dataclass(frozen=True)
class AgentRow:
    index: int
    key: str
    type: str
    value: str
    semantic_role: str | None = None


@dataclass(frozen=True)
class AgentRowsConfig:
    schema: str
    fields: list[AgentField]
    mappings: dict[int, str]
    reserved_ranges: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRowsOutput:
    schema: str
    game: dict[str, str]
    screen_type: str
    template_id: str
    confidence: float
    rows: list[AgentRow]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_agent_rows_config(path: Path) -> AgentRowsConfig:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    fields = [
        AgentField(
            index=int(item["index"]),
            key=str(item["key"]),
            type=str(item["type"]),
            description=str(item.get("description", "")),
        )
        for item in data.get("fields", [])
    ]
    mappings = {int(index): str(role) for index, role in data.get("mappings", {}).items()}

    return AgentRowsConfig(
        schema=str(data["schema"]),
        fields=fields,
        mappings=mappings,
        reserved_ranges=list(data.get("reserved_ranges", [])),
    )
