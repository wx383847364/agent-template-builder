from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import argparse
import json

from agent_template_builder.paths import default_game_dir
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
        raise FileNotFoundError(f"截图目录不存在: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"不是截图目录: {directory}")

    screenshots = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(screenshots, key=lambda path: (path.stat().st_mtime, path.name))


def latest_screenshot(directory: Path) -> Path:
    screenshots = list_screenshots(directory)
    if not screenshots:
        raise FileNotFoundError(f"截图目录没有可分析图片: {directory.resolve()}")
    return screenshots[-1]


def summarize_screenshot(screenshot_path: Path, game_dir: Path = default_game_dir()) -> ScreenshotSummary:
    data = analyze_screenshot(screenshot_path, game_dir).to_dict()
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


def summarize_directory(directory: Path, game_dir: Path = default_game_dir()) -> list[ScreenshotSummary]:
    return [summarize_screenshot(path, game_dir) for path in list_screenshots(directory)]


def main() -> None:
    parser = argparse.ArgumentParser(description="分析实时截图目录并输出 AgentData 或摘要。")
    parser.add_argument("directory", type=Path, help="截图目录，文件名仅用于追踪，不参与模板识别。")
    parser.add_argument("--game-dir", type=Path, default=default_game_dir())
    parser.add_argument("--latest", action="store_true", help="只分析目录中修改时间最新的截图。")
    parser.add_argument("--agent-data", action="store_true", help="与 --latest 一起使用，输出完整 AgentData JSON。")
    parser.add_argument("--jsonl", action="store_true", help="批量分析时按 JSON Lines 输出。")
    args = parser.parse_args()

    if args.latest:
        screenshot = latest_screenshot(args.directory)
        if args.agent_data:
            result = analyze_screenshot(screenshot, args.game_dir)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return
        summary = summarize_screenshot(screenshot, args.game_dir)
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
        return

    summaries = summarize_directory(args.directory, args.game_dir)
    if args.jsonl:
        for summary in summaries:
            print(json.dumps(asdict(summary), ensure_ascii=False))
    else:
        print(json.dumps([asdict(summary) for summary in summaries], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
