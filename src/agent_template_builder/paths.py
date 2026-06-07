from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_GAME_ID = "dhxy2_classic_pc"
LOCAL_CONFIG_NAME = "local.json"
SCREENSHOT_DIR_ENV = "AGENT_TEMPLATE_BUILDER_SCREENSHOT_DIR"
KNOWN_SCREENSHOT_DIRS = (
    Path("G:/大话/大话西游2_经典版/screen"),
)


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


def local_config_path(project_root: Path | None = None) -> Path:
    root = project_root or find_project_root(Path(__file__))
    return root / "configs" / LOCAL_CONFIG_NAME


def load_local_config(project_root: Path | None = None) -> dict[str, object]:
    path = local_config_path(project_root)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"local config must be a JSON object: {path}")
    return data


def configured_game_paths(
    game_id: str = DEFAULT_GAME_ID,
    project_root: Path | None = None,
) -> dict[str, Path]:
    config = load_local_config(project_root)
    games = config.get("games", {})
    if not isinstance(games, dict):
        return {}

    game_config = games.get(game_id, {})
    if not isinstance(game_config, dict):
        return {}

    paths: dict[str, Path] = {}
    for key in ("install_dir", "screenshot_dir"):
        value = game_config.get(key)
        if isinstance(value, str) and value:
            paths[key] = Path(value).expanduser()
    return paths


def candidate_screenshot_dirs(
    game_id: str = DEFAULT_GAME_ID,
    project_root: Path | None = None,
) -> list[Path]:
    root = project_root or find_project_root(Path(__file__))
    candidates: list[Path] = []

    env_path = os.environ.get(SCREENSHOT_DIR_ENV)
    if env_path:
        candidates.append(Path(env_path).expanduser())

    configured = configured_game_paths(game_id, root).get("screenshot_dir")
    if configured is not None:
        candidates.append(configured)

    candidates.extend(KNOWN_SCREENSHOT_DIRS)
    candidates.append(root / "samples" / game_id / "screenshots")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def default_screenshot_dir(
    game_id: str = DEFAULT_GAME_ID,
    project_root: Path | None = None,
) -> Path:
    candidates = candidate_screenshot_dirs(game_id, project_root)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]

