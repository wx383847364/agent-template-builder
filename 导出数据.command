#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

mkdir -p outputdata

if [ "$#" -ge 1 ]; then
  SCREENSHOT="$1"
else
  SCREENSHOT="samples/dhxy2_classic_pc/screenshots/reward_popup__manual_summon_reward1.png"
fi

if [ -x ".venv/bin/python" ]; then
  PYTHON_EXE=".venv/bin/python"
else
  PYTHON_EXE="python3"
fi

PYTHONPATH="$ROOT/src" "$PYTHON_EXE" -m agent_template_builder.pipeline.export_agent_rows "$SCREENSHOT" --fields-config agent_fields.json --pretty > outputdata/agent_rows.json

echo "导出完成：$ROOT/outputdata/agent_rows.json"
