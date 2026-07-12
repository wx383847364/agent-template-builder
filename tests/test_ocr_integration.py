from pathlib import Path
import sys

import pytest

import agent_template_builder.pipeline.analyze_screenshots as analyze_screenshots_pipeline
from agent_template_builder.ocr.base import OCRResult
from agent_template_builder.ocr.runtime import OCRConfigurationError, create_ocr_engine
from agent_template_builder.pipeline.analyze import analyze_screenshot
from agent_template_builder.pipeline.analyze_screenshots import summarize_directory, summarize_screenshot
from agent_template_builder.pipeline.export_agent_rows import export_agent_rows, to_index_value_data


ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "configs" / "games" / "dhxy2_classic_pc"
FIELDS_CONFIG = ROOT / "agent_fields.json"
SAMPLES_DIR = ROOT / "samples" / "dhxy2_classic_pc" / "screenshots"


class FakeOCREngine:
    def __init__(self, text: str = "任务追踪") -> None:
        self.text = text
        self.calls: list[tuple[Path, tuple[int, int, int, int]]] = []

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        self.calls.append((image_path, bbox))
        return OCRResult(text=self.text, confidence=0.9)


def test_none_backend_does_not_create_an_ocr_engine() -> None:
    assert create_ocr_engine("none") is None


def test_gpu_backend_requires_cuda(monkeypatch) -> None:
    monkeypatch.setattr("agent_template_builder.ocr.runtime._cuda_available", lambda: False)

    with pytest.raises(OCRConfigurationError, match="CUDA-enabled"):
        create_ocr_engine("paddle", "gpu")


def test_batch_summary_cli_rejects_ocr_without_full_agent_data(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_screenshots.py", str(SAMPLES_DIR), "--ocr", "paddle"],
    )

    with pytest.raises(SystemExit) as exc_info:
        analyze_screenshots_pipeline.main()

    assert exc_info.value.code == 2


def test_analyze_injects_ocr_text_into_task_and_evidence() -> None:
    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = FakeOCREngine("名望伊始")

    result = analyze_screenshot(image_path, GAME_DIR, engine)
    task_tracker = next(item for item in result.elements if item.id == "task_tracker")

    assert task_tracker.text == "名望伊始"
    assert task_tracker.evidence is not None
    assert task_tracker.evidence.ocr_text == "名望伊始"
    assert result.task is not None
    assert result.task.text == "名望伊始"
    assert len(engine.calls) == 1


def test_batch_summary_helpers_support_an_explicit_ocr_engine() -> None:
    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = FakeOCREngine()

    summary = summarize_screenshot(image_path, GAME_DIR, engine)
    summaries = summarize_directory(image_path.parent, GAME_DIR, engine)

    assert summary.screen_type == "main_world"
    assert summaries
    assert len(engine.calls) >= 2


def test_export_agent_rows_accepts_trailing_ocr_engine_argument() -> None:
    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = FakeOCREngine("穷奇境界业已破碎")

    output = export_agent_rows(image_path, GAME_DIR, FIELDS_CONFIG, engine)
    rows = to_index_value_data(output)

    assert rows["4"] == "穷奇境界业已破碎"
    assert rows["4000"] == "0"
