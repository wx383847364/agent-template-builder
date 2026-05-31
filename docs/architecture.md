# Agent Template Builder Architecture

Agent Template Builder is a template-first data export tool. It avoids full-screen OCR by using
local visual matching to determine the screen, then OCRs only dynamic text
regions before emitting Agent-ready JSON.

## Pipeline

```text
screenshot
  -> image metadata and aspect-ratio check
  -> game template pack loading
  -> template matching with anchors and fixed UI regions
  -> OCR only for dynamic regions
  -> AgentData JSON
```

## Matching Strategy

The matcher is intentionally layered from cheapest to most expensive:

1. Aspect-ratio and optional exact client-window checks.
2. Fixed layout anchors such as panel rectangles, button areas, and icons.
3. Region perceptual hash checks for stable UI blocks.
4. Small image-template matching, added later when real samples exist.
5. OCR fallback only after the screen candidate is known.

## OCR Policy

OCR is not used to decide the whole screen type in version 1. It is only used
for template elements with `ocr_required: true`, such as:

- current task text;
- NPC dialog body;
- blocking modal body;
- reward or prompt text.

Fixed labels and buttons should be recognized by template, region, or icon when
possible.

## Template Pack

`configs/games/dhxy2_classic_pc` is the first template pack. It contains:

- `game.json`: client identity, supported window sizes, and pipeline defaults;
- `templates/*.json`: screen templates and element regions;
- `vocab/*.txt`: correction dictionaries for OCR post-processing.

## Coordinate Policy

Template regions use normalized screen ratios, not fixed pixels:

```json
"bbox": [0.72, 0.12, 0.99, 0.44]
```

The runtime converts that region to pixels based on the incoming screenshot
size. The same bbox can work on `1280x720`, `1920x1080`, and other matching
aspect ratios.

The matcher prefers aspect-ratio profiles such as `16:9`, `4:3`, and `16:10`
instead of requiring one exact resolution. Exact window sizes are still allowed
as high-confidence profiles for local capture setups.
