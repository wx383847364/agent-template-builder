from pathlib import Path

import pytest

from agent_template_builder.ocr.base import OCRResult
from agent_template_builder.tools.ocr_smoke_test import benchmark, run_smoke_test, smoke_failures


ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "configs" / "games" / "dhxy2_classic_pc"
SAMPLES_DIR = ROOT / "samples" / "dhxy2_classic_pc" / "screenshots"


class FakeOCREngine:
    def __init__(self, text: str | None = None, confidence: float = 0.95) -> None:
        self.text = text
        self.confidence = confidence
        self.calls = 0

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        self.calls += 1
        expected = {
            "main_world": "任务追踪",
            "blocking_modal": "邀请您加入队伍",
            "npc_dialog": "蓝衣少年",
        }
        text = self.text or expected[next(key for key in expected if key in image_path.name)]
        return OCRResult(text=text, confidence=self.confidence)


def test_smoke_test_uses_default_targets_and_returns_results() -> None:
    engine = FakeOCREngine()

    results = run_smoke_test(engine, GAME_DIR, SAMPLES_DIR)

    assert [item.label for item in results] == [
        "main_world.task_tracker",
        "blocking_modal.modal_body",
        "npc_dialog.dialog_body",
    ]
    assert smoke_failures(results) == []
    assert engine.calls == 3


def test_benchmark_reuses_the_existing_engine() -> None:
    engine = FakeOCREngine()
    results = run_smoke_test(engine, GAME_DIR, SAMPLES_DIR)

    avg, p95, roi_per_second = benchmark(engine, results, 6)

    assert avg >= 0.0
    assert p95 >= 0.0
    assert roi_per_second > 0.0
    assert engine.calls == 9


def test_benchmark_rejects_non_positive_iterations() -> None:
    with pytest.raises(ValueError, match="iterations"):
        benchmark(FakeOCREngine(), [], 0)


def test_smoke_failures_reject_missing_expected_text() -> None:
    results = run_smoke_test(FakeOCREngine(text="无关文本"), GAME_DIR, SAMPLES_DIR)

    failures = smoke_failures(results)

    assert len(failures) == 3
    assert all("missing text" in failure for failure in failures)


def test_smoke_failures_reject_low_confidence() -> None:
    results = run_smoke_test(FakeOCREngine(confidence=0.1), GAME_DIR, SAMPLES_DIR)

    assert all("confidence" in failure for failure in smoke_failures(results))
