from pathlib import Path

import pytest

from agent_template_builder.ocr.base import OCRResult
from agent_template_builder.tools.ocr_smoke_test import (
    benchmark,
    benchmark_cached_analysis,
    run_smoke_test,
    select_benchmark_results,
    smoke_failures,
)


ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "configs" / "games" / "dhxy2_classic_pc"
SAMPLES_DIR = ROOT / "samples" / "dhxy2_classic_pc" / "screenshots"


class FakeOCREngine:
    def __init__(self, text: str | None = None, confidence: float = 0.95) -> None:
        self.text = text
        self.confidence = confidence
        self.calls = 0
        self.seen_screenshots: list[str] = []

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        self.calls += 1
        self.seen_screenshots.append(image_path.name)
        expected = {
            "main_world": "任务追踪",
            "blocking_modal": "邀请您加入队伍",
            "npc_dialog": "蓝衣少年",
        }
        text = self.text or expected[next(key for key in expected if key in image_path.name)]
        return OCRResult(text=text, confidence=self.confidence)


class CacheableBenchmarkEngine:
    cache_identity = "cacheable-benchmark-engine"

    def __init__(self) -> None:
        self.image_calls = 0

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        raise AssertionError("cached analysis must use read_image")

    def read_image(self, image) -> OCRResult:
        self.image_calls += 1
        return OCRResult(text="缓存文本", confidence=0.95)


def test_smoke_test_uses_default_targets_and_returns_results() -> None:
    engine = FakeOCREngine()

    results = run_smoke_test(engine, GAME_DIR, SAMPLES_DIR)

    assert [item.label for item in results] == [
        "main_world.task_tracker",
        "main_world.task_tracker.1024x720",
        "main_world.task_tracker.800x574",
        "main_world.task_tracker.1366x768",
        "main_world.task_tracker.legacy_1203x872",
        "blocking_modal.modal_body",
        "npc_dialog.dialog_body",
    ]
    assert smoke_failures(results) == []
    assert engine.calls == 7


def test_benchmark_reuses_the_existing_engine() -> None:
    engine = FakeOCREngine()
    results = run_smoke_test(engine, GAME_DIR, SAMPLES_DIR)
    benchmark_results = select_benchmark_results(results)
    engine.seen_screenshots.clear()

    avg, p95, roi_per_second = benchmark(engine, benchmark_results, 6)

    assert avg >= 0.0
    assert p95 >= 0.0
    assert roi_per_second > 0.0
    assert engine.calls == 13
    assert engine.seen_screenshots == [
        "main_world__manual_1000x718_1.png",
        "blocking_modal__manual_team_invite1.png",
        "npc_dialog__manual_dialog1.png",
    ] * 2


def test_benchmark_selection_rejects_missing_stable_targets() -> None:
    with pytest.raises(ValueError, match="missing benchmark"):
        select_benchmark_results([])


def test_cached_analysis_benchmark_measures_misses_then_hits() -> None:
    smoke_engine = FakeOCREngine()
    smoke_results = select_benchmark_results(
        run_smoke_test(smoke_engine, GAME_DIR, SAMPLES_DIR)
    )
    engine = CacheableBenchmarkEngine()

    result = benchmark_cached_analysis(
        engine,
        GAME_DIR,
        smoke_results,
        6,
    )

    assert result.warmup_seconds >= 0.0
    assert result.hit_avg_seconds >= 0.0
    assert result.hit_p95_seconds >= 0.0
    assert result.analyses_per_second > 0.0
    assert result.warmup_misses == 4
    assert result.warmup_writes == 4
    assert result.timed_hits == 8
    assert result.timed_misses == 0
    assert engine.image_calls == 4


def test_cached_analysis_benchmark_clears_preexisting_cache_each_run() -> None:
    smoke_results = select_benchmark_results(
        run_smoke_test(FakeOCREngine(), GAME_DIR, SAMPLES_DIR)
    )
    engine = CacheableBenchmarkEngine()

    benchmark_cached_analysis(engine, GAME_DIR, smoke_results, 3)
    first_run_calls = engine.image_calls
    second = benchmark_cached_analysis(engine, GAME_DIR, smoke_results, 3)

    assert first_run_calls == 4
    assert engine.image_calls == 8
    assert second.warmup_misses == second.warmup_writes == 4
    assert second.timed_misses == 0


def test_benchmark_rejects_non_positive_iterations() -> None:
    with pytest.raises(ValueError, match="iterations"):
        benchmark(FakeOCREngine(), [], 0)


def test_smoke_failures_reject_missing_expected_text() -> None:
    results = run_smoke_test(FakeOCREngine(text="无关文本"), GAME_DIR, SAMPLES_DIR)

    failures = smoke_failures(results)

    assert len(failures) == 7
    assert all("missing text" in failure for failure in failures)


def test_smoke_failures_reject_low_confidence() -> None:
    results = run_smoke_test(FakeOCREngine(confidence=0.1), GAME_DIR, SAMPLES_DIR)

    assert all("confidence" in failure for failure in smoke_failures(results))
