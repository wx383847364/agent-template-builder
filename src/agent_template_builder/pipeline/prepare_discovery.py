from __future__ import annotations

from pathlib import Path
import argparse

from agent_template_builder.discovery.workflow import prepare_discovery


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a 1920x1080 screenshot for Codex-client UI discovery."
    )
    parser.add_argument("screenshot", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    parser.add_argument("--game-dir", type=Path, default=None)
    args = parser.parse_args()

    run_dir = prepare_discovery(
        args.screenshot,
        output_dir=args.output_dir,
        game_dir=args.game_dir,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
