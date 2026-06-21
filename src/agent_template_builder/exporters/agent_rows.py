from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from agent_template_builder.schema.agent_data import AgentData, Element
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
        self._add_metadata_values(data, values_by_role)

        for element in data.elements:
            if not element.semantic_role or not element.text:
                continue
            values_by_role[element.semantic_role].append(element.text)

        self._bind_server_select_values(data.elements, values_by_role)

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

    def _add_metadata_values(
        self,
        data: AgentData,
        values_by_role: dict[str, list[str]],
    ) -> None:
        values_by_role["screen_type"].append(data.screen.type)
        values_by_role["template_id"].append(data.screen.template_id)
        values_by_role["screen_confidence"].append(f"{data.screen.confidence:.3f}")
        values_by_role["blocking_modal"].append("1" if data.state.blocking_modal else "0")

        available_intents = _format_available_intents(data.state.available_intents)
        if available_intents:
            values_by_role["available_intents"].append(available_intents)

    def _bind_server_select_values(
        self,
        elements: list[Element],
        values_by_role: dict[str, list[str]],
    ) -> None:
        selected_values = values_by_role.get("selected_server", [])
        if selected_values:
            selected_slots = _elements_by_role(elements, "selected_server_slot")
            selected_values[0] = _bind_single_server(selected_values[0], selected_slots, _elements_by_role(elements, "selected_server"))

        account_values = values_by_role.get("account_servers", [])
        if account_values:
            account_slots = _elements_by_role(elements, "account_server_slot")
            account_values[0] = _bind_server_list(account_values[0], account_slots, _elements_by_role(elements, "account_servers"))


def _elements_by_role(elements: list[Element], semantic_role: str) -> list[Element]:
    return [element for element in elements if element.semantic_role == semantic_role]


def _format_available_intents(intents: list[str]) -> str:
    for intent in intents:
        if not re.fullmatch(r"[a-z0-9_]+", intent):
            raise ValueError(f"available_intent must match [a-z0-9_]+: {intent}")
    return ";".join(intents)


def _bind_single_server(value: str, slots: list[Element], fallback_regions: list[Element]) -> str:
    if _has_bound_coordinate(value):
        return value
    candidates = _split_server_names(value)
    if not candidates:
        return value
    slot = slots[0] if slots else fallback_regions[0] if fallback_regions else None
    return _format_server_at(candidates[0], slot) if slot else candidates[0]


def _bind_server_list(value: str, slots: list[Element], fallback_regions: list[Element]) -> str:
    if _has_bound_coordinate(value):
        return value
    names = _split_server_names(value)
    if not names:
        return value
    if not slots and len(names) == 1 and fallback_regions:
        return _format_server_at(names[0], fallback_regions[0])
    bound = [
        _format_server_at(name, slot)
        for name, slot in zip(names, slots)
    ]
    return ";".join(bound) if bound else value


def _split_server_names(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;\n\r,，、\s]+", value) if item.strip()]


def _has_bound_coordinate(value: str) -> bool:
    return bool(re.search(r"@\d+,\d+", value))


def _format_server_at(name: str, element: Element) -> str:
    left, top, right, bottom = element.bbox
    center_x = round((left + right) / 2)
    center_y = round((top + bottom) / 2)
    return f"{name}@{center_x},{center_y}"
