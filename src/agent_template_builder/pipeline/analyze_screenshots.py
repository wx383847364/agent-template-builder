from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import argparse
import json

from agent_template_builder.paths import DEFAULT_GAME_ID, default_game_dir, default_screenshot_dir
from agent_template_builder.ocr.base import OCREngine
from agent_template_builder.ocr.runtime import add_ocr_argument, create_ocr_engine_or_error
from agent_template_builder.pipeline.analyze import analyze_screenshot


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass(frozen=True)
class ScreenshotSummary:
    screenshot: str
    screen_type: str
    template_id: str
    confidence: float
    resolution: dict[str, int]
    match: dict[str, object]


def list_screenshots(directory: Path) -> list[Path]:
    directory = directory.resolve()
    if not directory.exists():
        raise FileNotFoundError(f"screenshot directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"not a screenshot directory: {directory}")

    screenshots = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(screenshots, key=lambda path: (path.stat().st_mtime, path.name))


def latest_screenshot(directory: Path) -> Path:
    screenshots = list_screenshots(directory)
    if not screenshots:
        raise FileNotFoundError(f"no analyzable images in screenshot directory: {directory.resolve()}")
    return screenshots[-1]


def summarize_screenshot(
    screenshot_path: Path,
    game_dir: Path = default_game_dir(),
    ocr_engine: OCREngine | None = None,
) -> ScreenshotSummary:
    data = analyze_screenshot(screenshot_path, game_dir, ocr_engine).to_dict()
    screen = data["screen"]
    resolution = screen["resolution"]
    return ScreenshotSummary(
        screenshot=str(screenshot_path.resolve()),
        screen_type=str(screen["type"]),
        template_id=str(screen["template_id"]),
        confidence=float(screen["confidence"]),
        resolution={
            "width": int(resolution["width"]),
            "height": int(resolution["height"]),
        },
        match=dict(data["raw"]["match"]),
    )


def summarize_directory(
    directory: Path,
    game_dir: Path = default_game_dir(),
    ocr_engine: OCREngine | None = None,
) -> list[ScreenshotSummary]:
    return [summarize_screenshot(path, game_dir, ocr_engine) for path in list_screenshots(directory)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a live screenshot directory.")
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        help="Screenshot directory. Defaults to local config, known game paths, then samples.",
    )
    parser.add_argument("--game-dir", type=Path, default=default_game_dir())
    parser.add_argument("--latest", action="store_true", help="Only analyze the newest screenshot.")
    parser.add_argument("--agent-data", action="store_true", help="With --latest, print full AgentData JSON.")
    parser.add_argument("--jsonl", action="store_true", help="Print batch summaries as JSON Lines.")
    add_ocr_argument(parser)
    args = parser.parse_args()

    if args.ocr != "none" and not (args.latest and args.agent_data):
        parser.error("OCR is only available with --latest --agent-data because summary output does not include OCR text.")

    directory = args.directory or default_screenshot_dir(DEFAULT_GAME_ID)
    ocr_engine = create_ocr_engine_or_error(parser, args.ocr, args.ocr_device)

    if args.latest:
        screenshot = latest_screenshot(directory)
        if args.agent_data:
            result = analyze_screenshot(screenshot, args.game_dir, ocr_engine)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return
        summary = summarize_screenshot(screenshot, args.game_dir, ocr_engine)
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
        return

    summaries = summarize_directory(directory, args.game_dir, ocr_engine)
    if args.jsonl:
        for summary in summaries:
            print(json.dumps(asdict(summary), ensure_ascii=False))
    else:
        print(json.dumps([asdict(summary) for summary in summaries], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
