from __future__ import annotations

from pathlib import Path


def find_project_root(start: Path) -> Path:
    """Find the repository root from a package file path."""
    current = start.resolve()
    if current.is_file():
        current = current.parent

    for candidate in [current] + list(current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "configs").exists():
            return candidate

    raise RuntimeError(f"could not find Agent Template Builder project root from {start}")


def default_game_dir() -> Path:
    return find_project_root(Path(__file__)) / "configs" / "games" / "dhxy2_classic_pc"

