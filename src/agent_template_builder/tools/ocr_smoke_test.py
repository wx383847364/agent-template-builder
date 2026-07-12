from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean, quantiles
import argparse
import time

from agent_template_builder.ocr.base import OCREngine, OCRResult
from agent_template_builder.ocr.runtime import add_ocr_device_argument, create_ocr_engine_or_error
from agent_template_builder.paths import default_game_dir, find_project_root
from agent_template_builder.pipeline.analyze import analyze_screenshot


@dataclass(frozen=True)
class OCRSmokeTarget:
    label: str
    screenshot_name: str
    element_id: str
    expected_template_id: str
    required_text: str
    min_confidence: float


@dataclass(frozen=True)
class OCRSmokeResult:
    label: str
    screenshot_path: Path
    element_id: str
    template_id: str
    bbox: tuple[int, int, int, int]
    result: OCRResult
    elapsed_seconds: float


DEFAULT_TARGETS = (
    OCRSmokeTarget(
        "main_world.task_tracker",
        "main_world__manual_1000x718_1.png",
        "task_tracker",
        "dhxy2_classic_main_world_v1",
        "任务追踪",
        0.70,
    ),
    OCRSmokeTarget(
        "blocking_modal.modal_body",
        "blocking_modal__manual_team_invite1.png",
        "modal_body",
        "dhxy2_classic_blocking_modal_v1",
        "邀请您加入队伍",
        0.70,
    ),
    OCRSmokeTarget(
        "npc_dialog.dialog_body",
        "npc_dialog__manual_dialog1.png",
        "dialog_body",
        "dhxy2_classic_npc_dialog_v1",
        "蓝衣少年",
        0.70,
    ),
)


def default_screenshots_dir() -> Path:
    return find_project_root(Path(__file__)) / "samples" / "dhxy2_classic_pc" / "screenshots"


def run_smoke_test(
    ocr_engine: OCREngine,
    game_dir: Path,
    screenshots_dir: Path,
    targets: tuple[OCRSmokeTarget, ...] = DEFAULT_TARGETS,
) -> list[OCRSmokeResult]:
    results: list[OCRSmokeResult] = []
    for target in targets:
        screenshot_path = screenshots_dir / target.screenshot_name
        if not screenshot_path.is_file():
            raise FileNotFoundError(f"smoke-test screenshot does not exist: {screenshot_path}")

        data = analyze_screenshot(screenshot_path, game_dir)
        if data.screen.template_id != target.expected_template_id:
            raise ValueError(
                f"smoke-test target {target.label} matched {data.screen.template_id}, "
                f"expected {target.expected_template_id}"
            )
        element = next((item for item in data.elements if item.id == target.element_id), None)
        if element is None:
            raise ValueError(f"smoke-test target {target.label} has no element {target.element_id}")

        started = time.perf_counter()
        result = ocr_engine.read_region(screenshot_path, element.bbox)
        results.append(
            OCRSmokeResult(
                label=target.label,
                screenshot_path=screenshot_path,
                element_id=target.element_id,
                template_id=data.screen.template_id,
                bbox=element.bbox,
                result=result,
                elapsed_seconds=time.perf_counter() - started,
            )
        )
    return results


def benchmark(
    ocr_engine: OCREngine,
    smoke_results: list[OCRSmokeResult],
    iterations: int,
) -> tuple[float, float, float]:
    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    if not smoke_results:
        raise ValueError("at least one smoke result is required")

    timings: list[float] = []
    for index in range(iterations):
        item = smoke_results[index % len(smoke_results)]
        started = time.perf_counter()
        ocr_engine.read_region(item.screenshot_path, item.bbox)
        timings.append(time.perf_counter() - started)

    total = sum(timings)
    p95 = quantiles(timings, n=20)[18] if len(timings) >= 20 else max(timings)
    if total <= 0:
        raise RuntimeError("benchmark clock produced a non-positive elapsed time")
    return mean(timings), p95, iterations / total


def smoke_failures(
    results: list[OCRSmokeResult],
    targets: tuple[OCRSmokeTarget, ...] = DEFAULT_TARGETS,
) -> list[str]:
    targets_by_label = {target.label: target for target in targets}
    failures: list[str] = []
    for item in results:
        target = targets_by_label[item.label]
        text = item.result.text.strip()
        if item.template_id != target.expected_template_id:
            failures.append(f"{item.label}: template={item.template_id}")
        elif item.result.confidence < target.min_confidence:
            failures.append(f"{item.label}: confidence={item.result.confidence:.3f}")
        elif target.required_text not in text:
            failures.append(f"{item.label}: missing text {target.required_text!r}")
        elif not any("\u4e00" <= char <= "\u9fff" for char in text):
            failures.append(f"{item.label}: no Chinese text")
    return failures


def _print_result(item: OCRSmokeResult) -> None:
    text = item.result.text.replace("\n", " | ")
    print(
        f"[{item.label}] bbox={item.bbox} confidence={item.result.confidence:.3f} "
        f"elapsed={item.elapsed_seconds:.4f}s"
    )
    print(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PaddleOCR smoke and performance tests on repository ROI samples.")
    parser.add_argument("--game-dir", type=Path, default=default_game_dir())
    parser.add_argument("--screenshots-dir", type=Path, default=default_screenshots_dir())
    parser.add_argument("--benchmark", action="store_true", help="Run a warm ROI benchmark after smoke verification.")
    parser.add_argument("--iterations", type=int, default=60, help="Total ROI reads for --benchmark.")
    add_ocr_device_argument(parser)
    args = parser.parse_args()
    if args.benchmark and args.iterations < 1:
        parser.error("--iterations must be at least 1 when --benchmark is used.")

    engine = create_ocr_engine_or_error(parser, "paddle", args.ocr_device)
    assert engine is not None
    results = run_smoke_test(engine, args.game_dir, args.screenshots_dir)
    for item in results:
        _print_result(item)

    failures = smoke_failures(results)
    if failures:
        raise SystemExit(f"OCR smoke test failed: {'; '.join(failures)}")

    if args.benchmark:
        avg, p95, roi_per_second = benchmark(engine, results, args.iterations)
        print(
            f"benchmark count={args.iterations} avg={avg:.4f}s p95={p95:.4f}s "
            f"roi_per_s={roi_per_second:.2f}"
        )


if __name__ == "__main__":
    main()
