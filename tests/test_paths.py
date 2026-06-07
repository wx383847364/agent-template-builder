import json

from agent_template_builder.paths import (
    candidate_screenshot_dirs,
    default_game_dir,
    default_screenshot_dir,
    find_project_root,
    load_local_config,
)


def test_find_project_root() -> None:
    root = find_project_root(default_game_dir())

    assert (root / "pyproject.toml").exists()
    assert (root / "configs" / "games" / "dhxy2_classic_pc").exists()


def test_default_game_dir() -> None:
    assert (default_game_dir() / "game.json").exists()


def test_load_local_config_from_project_root(tmp_path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "local.json").write_text(
        json.dumps({"games": {"dhxy2_classic_pc": {"screenshot_dir": "G:/game/screen"}}}),
        encoding="utf-8",
    )

    assert load_local_config(tmp_path)["games"]["dhxy2_classic_pc"]["screenshot_dir"] == "G:/game/screen"


def test_default_screenshot_dir_prefers_local_config(tmp_path) -> None:
    screenshot_dir = tmp_path / "game" / "screen"
    screenshot_dir.mkdir(parents=True)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "local.json").write_text(
        json.dumps(
            {
                "games": {
                    "dhxy2_classic_pc": {
                        "screenshot_dir": screenshot_dir.as_posix(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert default_screenshot_dir(project_root=tmp_path) == screenshot_dir


def test_candidate_screenshot_dirs_includes_samples_fallback(tmp_path) -> None:
    candidates = candidate_screenshot_dirs(project_root=tmp_path)

    assert candidates[-1] == tmp_path / "samples" / "dhxy2_classic_pc" / "screenshots"

