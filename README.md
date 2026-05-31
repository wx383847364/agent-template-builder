# Agent Template Builder

Agent Template Builder creates reusable screen templates and exports structured data for a local Agent or LLM.

The first template pack targets `dhxy2_classic_pc`, the PC classic client of
`大话西游2`. Version 1 focuses on task-readable screens:

- identify the current screen template without OCR when possible;
- detect fixed UI elements such as task panels, dialogs, maps, and modals;
- OCR only dynamic regions such as task text, dialog body, and popup content;
- emit JSON with confidence and evidence for every important field.

## Layout

```text
configs/games/dhxy2_classic_pc/   Game-specific templates and vocabulary
samples/dhxy2_classic_pc/         Screenshot samples and expected JSON outputs
src/agent_template_builder/       Template builder and export pipeline
docs/                             Architecture notes
tests/                            Unit tests for schema and config loading
```

## Quick Start

```bash
cd /Users/bruce/work/agent-template-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m agent_template_builder.pipeline.analyze samples/dhxy2_classic_pc/screenshots/example.png
```

The sample command expects a real screenshot. Until screenshots are added, use
the tests to verify the project skeleton:

```bash
python -m pytest
```

## First Milestone

1. Capture 3-10 screenshots for each first template: main world, NPC dialog,
   blocking modal, map/navigation, and reward/prompt popup.
2. Fill each template anchor with real region hashes or image anchors.
3. Add expected JSON files under `samples/dhxy2_classic_pc/expected`.
4. Keep OCR limited to regions marked with `ocr_required: true`.

Template bboxes are screen ratios, not fixed pixels, so one template can work
across multiple resolutions that share a supported aspect ratio.
