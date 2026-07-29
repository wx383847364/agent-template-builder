from __future__ import annotations

from pathlib import Path
from typing import Protocol
import json

from agent_template_builder.discovery.schema import ModelDiscoveryOutput, PreparationRequest


class DiscoveryProvider(Protocol):
    def discover(self, screenshot: Path, request: PreparationRequest) -> ModelDiscoveryOutput:
        ...


class FileDiscoveryProvider:
    """读取 Codex 客户端按固定 schema 生成的模型输出。"""

    def __init__(self, model_output_path: Path) -> None:
        self._model_output_path = model_output_path

    def discover(self, screenshot: Path, request: PreparationRequest) -> ModelDiscoveryOutput:
        del screenshot, request
        with self._model_output_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return ModelDiscoveryOutput.model_validate(payload)
