from agent_template_builder.paths import default_game_dir, find_project_root


def test_find_project_root() -> None:
    root = find_project_root(default_game_dir())

    assert (root / "pyproject.toml").exists()
    assert (root / "configs" / "games" / "dhxy2_classic_pc").exists()


def test_default_game_dir() -> None:
    assert (default_game_dir() / "game.json").exists()

