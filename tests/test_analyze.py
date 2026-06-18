from pathlib import Path
import json

from PIL import Image

from agent_template_builder.pipeline.analyze import analyze_screenshot
from agent_template_builder.pipeline.analyze_screenshots import (
    latest_screenshot,
    list_screenshots,
    summarize_directory,
    summarize_screenshot,
)


GAME_DIR = Path(__file__).resolve().parents[1] / "configs" / "games" / "dhxy2_classic_pc"
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "dhxy2_classic_pc"


def test_analyze_accepts_same_ratio_different_resolution(tmp_path: Path) -> None:
    screenshot = tmp_path / "wide_1080p.png"
    Image.new("RGB", (1920, 1080), color=(10, 20, 30)).save(screenshot)

    result = analyze_screenshot(screenshot, GAME_DIR)
    data = result.to_dict()

    assert data["screen"]["type"] == "main_world"
    assert data["screen"]["confidence"] == 0.35
    assert data["screen"]["resolution"] == {"width": 1920, "height": 1080}
    assert data["raw"]["match"]["aspect_ratio_label"] == "wide_16_9"
    assert data["raw"]["match"]["fallback_reason"] == "no_anchor_hash_match"
    assert data["raw"]["match"]["measurable_template_count"] == 7
    assert data["elements"][0]["bbox"] == (1382, 130, 1901, 475)


def test_analyze_penalizes_unknown_aspect_ratio(tmp_path: Path) -> None:
    screenshot = tmp_path / "odd_ratio.png"
    Image.new("RGB", (1000, 1000), color=(10, 20, 30)).save(screenshot)

    result = analyze_screenshot(screenshot, GAME_DIR)

    assert result.screen.confidence == 0.158
    assert result.raw["match"]["aspect_ratio_label"] is None
    assert result.raw["match"]["fallback_reason"] == "no_anchor_hash_match"
    assert result.raw["match"]["measurable_template_count"] == 7


def test_lists_screenshots_without_using_names_for_classification(tmp_path: Path) -> None:
    old = tmp_path / "20260601_170000.png"
    latest = tmp_path / "timestamp_only.png"
    ignored = tmp_path / "notes.txt"
    Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(old)
    Image.new("RGB", (1280, 720), color=(20, 30, 40)).save(latest)
    ignored.write_text("not a screenshot", encoding="utf-8")

    assert list_screenshots(tmp_path) == [old, latest]
    assert latest_screenshot(tmp_path) == latest

    summary = summarize_screenshot(latest, GAME_DIR)

    assert summary.screenshot == str(latest.resolve())
    assert summary.screen_type == "main_world"
    assert summary.template_id == "dhxy2_classic_main_world_v1"
    assert summary.match["fallback_reason"] == "no_anchor_hash_match"


def test_summarizes_directory_for_batch_agent_handoff(tmp_path: Path) -> None:
    first = tmp_path / "001.png"
    second = tmp_path / "002.png"
    Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(first)
    Image.new("RGB", (1000, 1000), color=(20, 30, 40)).save(second)

    summaries = summarize_directory(tmp_path, GAME_DIR)

    assert [item.screenshot for item in summaries] == [str(first.resolve()), str(second.resolve())]
    assert [item.screen_type for item in summaries] == ["main_world", "main_world"]
    assert summaries[0].match["aspect_ratio_label"] == "fixed_window"
    assert summaries[1].match["aspect_ratio_label"] is None


def test_existing_repository_samples_match_expected_templates(tmp_path: Path) -> None:
    expected_path = SAMPLES_DIR / "expected" / "final_expected.json"
    with expected_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    cases = [
        item
        for item in manifest["cases"]
        if str(item.get("sample_status", "")).endswith("anchor_calibrated")
        and (Path(__file__).resolve().parents[1] / item["screenshot"]).is_file()
    ]

    assert {item["screen_type"] for item in cases} == {
        "battle",
        "character_select",
        "login_waterfall",
        "main_world",
        "npc_dialog",
        "server_select",
        "system_panel",
    }

    for index, case in enumerate(cases):
        source = Path(__file__).resolve().parents[1] / case["screenshot"]
        timestamp_only = tmp_path / f"runtime_capture_{index:02}.png"
        timestamp_only.write_bytes(source.read_bytes())

        result = analyze_screenshot(timestamp_only, GAME_DIR)

        assert result.screen.type == case["screen_type"]
        assert result.screen.template_id == case["template_id"]
