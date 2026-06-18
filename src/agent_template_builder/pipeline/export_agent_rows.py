from __future__ import annotations

from pathlib import Path
import argparse
import json

from agent_template_builder.exporters.agent_rows import AgentRowsExporter
from agent_template_builder.paths import default_game_dir
from agent_template_builder.pipeline.analyze import analyze_screenshot
from agent_template_builder.schema.agent_rows import AgentRowsOutput


DEFAULT_FIELDS_CONFIG = default_game_dir() / "agent_fields.json"


def export_agent_rows(
    screenshot_path: Path,
    game_dir: Path = default_game_dir(),
    fields_config: Path = DEFAULT_FIELDS_CONFIG,
) -> AgentRowsOutput:
    data = analyze_screenshot(screenshot_path, game_dir)
    exporter = AgentRowsExporter.from_config_path(fields_config)
    return exporter.export(data)


def to_index_value_data(output: AgentRowsOutput) -> dict[str, str]:
    return {str(row.index): row.value for row in output.rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export AgentData as stable index/value JSON rows.")
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--game-dir", type=Path, default=default_game_dir())
    parser.add_argument("--fields-config", type=Path, default=DEFAULT_FIELDS_CONFIG)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    result = export_agent_rows(args.screenshot, args.game_dir, args.fields_config)
    indent = 2 if args.pretty else None
    print(json.dumps(to_index_value_data(result), ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
