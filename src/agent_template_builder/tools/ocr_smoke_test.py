from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean, quantiles
import argparse
import time

from agent_template_builder.ocr.base import OCREngine, OCRResult
from agent_template_builder.ocr.runtime import add_ocr_device_argument, create_ocr_engine_or_error
from agent_template_builder.paths import default_game_dir, find_project_root
from agent_template_builder.pipeline.analyze import (
    analyze_screenshot,
    clear_engine_region_cache,
    get_engine_region_cache_stats,
)


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


@dataclass(frozen=True)
class CachedAnalysisBenchmark:
    warmup_seconds: float
    hit_avg_seconds: float
    hit_p95_seconds: float
    analyses_per_second: float
    warmup_misses: int
    warmup_writes: int
    timed_hits: int
    timed_misses: int


# Existing OCR smoke images are legacy resolutions. Add targets only after a
# confirmed 1920×1080 template and its OCR text baseline are captured.
DEFAULT_TARGETS: tuple[OCRSmokeTarget, ...] = ()

DEFAULT_BENCHMARK_LABELS: tuple[str, ...] = ()


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


def benchmark_cached_analysis(
    ocr_engine: OCREngine,
    game_dir: Path,
    smoke_results: list[OCRSmokeResult],
    iterations: int,
) -> CachedAnalysisBenchmark:
    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    if not smoke_results:
        raise ValueError("at least one smoke result is required")
    if not clear_engine_region_cache(ocr_engine, reset_stats=True):
        raise RuntimeError("analysis cache benchmark requires a weak-referenceable OCR engine")

    warmup_started = time.perf_counter()
    for item in smoke_results:
        analyze_screenshot(item.screenshot_path, game_dir, ocr_engine)
    warmup_seconds = time.perf_counter() - warmup_started
    warmup_stats = get_engine_region_cache_stats(ocr_engine)
    if warmup_stats is None or warmup_stats.misses <= 0 or warmup_stats.writes <= 0:
        raise RuntimeError("analysis cache warmup did not produce real cache misses and writes")

    timings: list[float] = []
    for index in range(iterations):
        item = smoke_results[index % len(smoke_results)]
        started = time.perf_counter()
        analyze_screenshot(item.screenshot_path, game_dir, ocr_engine)
        timings.append(time.perf_counter() - started)

    total = sum(timings)
    p95 = quantiles(timings, n=20)[18] if len(timings) >= 20 else max(timings)
    if total <= 0:
        raise RuntimeError("benchmark clock produced a non-positive elapsed time")
    final_stats = get_engine_region_cache_stats(ocr_engine)
    if final_stats is None:
        raise RuntimeError("analysis cache statistics disappeared during benchmark")
    timed_hits = final_stats.hits - warmup_stats.hits
    timed_misses = final_stats.misses - warmup_stats.misses
    if timed_misses != 0 or timed_hits <= 0:
        raise RuntimeError(
            "analysis cache timed phase was not cache-only: "
            f"hits={timed_hits} misses={timed_misses}"
        )
    return CachedAnalysisBenchmark(
        warmup_seconds=warmup_seconds,
        hit_avg_seconds=mean(timings),
        hit_p95_seconds=p95,
        analyses_per_second=iterations / total,
        warmup_misses=warmup_stats.misses,
        warmup_writes=warmup_stats.writes,
        timed_hits=timed_hits,
        timed_misses=timed_misses,
    )


def select_benchmark_results(
    smoke_results: list[OCRSmokeResult],
    labels: tuple[str, ...] = DEFAULT_BENCHMARK_LABELS,
) -> list[OCRSmokeResult]:
    results_by_label = {item.label: item for item in smoke_results}
    missing = [label for label in labels if label not in results_by_label]
    if missing:
        raise ValueError(f"missing benchmark smoke results: {', '.join(missing)}")
    return [results_by_label[label] for label in labels]


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
        benchmark_results = select_benchmark_results(results)
        avg, p95, roi_per_second = benchmark(engine, benchmark_results, args.iterations)
        print(
            f"roi_benchmark count={args.iterations} avg={avg:.4f}s p95={p95:.4f}s "
            f"roi_per_s={roi_per_second:.2f}"
        )
        cached = benchmark_cached_analysis(
            engine,
            args.game_dir,
            benchmark_results,
            args.iterations,
        )
        print(
            f"analysis_cache_benchmark warmup_count={len(benchmark_results)} "
            f"warmup_total={cached.warmup_seconds:.4f}s "
            f"warmup_misses={cached.warmup_misses} warmup_writes={cached.warmup_writes} "
            f"hit_count={args.iterations} hit_avg={cached.hit_avg_seconds:.4f}s "
            f"hit_p95={cached.hit_p95_seconds:.4f}s "
            f"timed_hits={cached.timed_hits} timed_misses={cached.timed_misses} "
            f"analyses_per_s={cached.analyses_per_second:.2f}"
        )


if __name__ == "__main__":
    main()
