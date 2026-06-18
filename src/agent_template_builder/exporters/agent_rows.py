from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from agent_template_builder.schema.agent_data import AgentData
from agent_template_builder.schema.agent_rows import (
    AgentRow,
    AgentRowsConfig,
    AgentRowsOutput,
    load_agent_rows_config,
)


class AgentRowsExporter:
    def __init__(self, config: AgentRowsConfig) -> None:
        self.config = config

    @classmethod
    def from_config_path(cls, path: Path) -> "AgentRowsExporter":
        return cls(load_agent_rows_config(path))

    def export(self, data: AgentData) -> AgentRowsOutput:
        values_by_role: dict[str, list[str]] = defaultdict(list)
        for element in data.elements:
            if not element.semantic_role or not element.text:
                continue
            values_by_role[element.semantic_role].append(element.text)

        rows = []
        for field in sorted(self.config.fields, key=lambda item: item.index):
            semantic_role = self.config.mappings.get(field.index)
            values = values_by_role.get(semantic_role or "", [])
            rows.append(
                AgentRow(
                    index=field.index,
                    key=field.key,
                    type=field.type,
                    value="\n".join(values) if values else "",
                    semantic_role=semantic_role,
                )
            )

        return AgentRowsOutput(
            schema=self.config.schema,
            game=data.game,
            screen_type=data.screen.type,
            template_id=data.screen.template_id,
            confidence=data.screen.confidence,
            rows=rows,
        )
