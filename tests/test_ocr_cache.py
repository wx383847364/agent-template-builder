from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
import gc
import time

import pytest
from PIL import Image

from agent_template_builder.ocr.base import OCRResult
from agent_template_builder.ocr.cache import (
    EngineStateRegistry,
    OCRRegionCache,
    RegionCacheKey,
    hash_roi_pixels,
    make_region_cache_key,
)


def _key(name: str) -> RegionCacheKey:
    return RegionCacheKey("template", name, f"hash-{name}", "paddle-v5")


def test_roi_hash_is_stable_for_equivalent_pixels() -> None:
    rgb = Image.new("RGB", (3, 2), color=(10, 20, 30))
    rgba = rgb.convert("RGBA")

    assert hash_roi_pixels(rgb) == hash_roi_pixels(rgba)
    assert hash_roi_pixels(rgb) != hash_roi_pixels(Image.new("RGB", (2, 3), color=(10, 20, 30)))


def test_cache_key_contains_region_and_ocr_identity() -> None:
    roi = Image.new("RGB", (4, 4), color="white")

    key = make_region_cache_key("login", "selected_server", roi, "paddle-v5-gpu")

    assert key.template_id == "login"
    assert key.element_id == "selected_server"
    assert key.roi_hash == hash_roi_pixels(roi)
    assert key.ocr_config_id == "paddle-v5-gpu"


def test_get_or_compute_reuses_a_successful_non_empty_result() -> None:
    cache = OCRRegionCache(max_entries=2)
    calls = 0

    def compute() -> OCRResult:
        nonlocal calls
        calls += 1
        return OCRResult(text="雾隐云居", confidence=0.96)

    first = cache.get_or_compute(_key("server"), compute)
    second = cache.get_or_compute(_key("server"), compute)

    assert first == second
    assert calls == 1
    assert cache.stats().hits == 1
    assert cache.stats().misses == 1


def test_cache_rejects_empty_and_unsuccessful_results() -> None:
    cache = OCRRegionCache()

    assert cache.put(_key("empty"), OCRResult(text="  \n", confidence=0.99)) is False
    assert cache.put(_key("failed"), OCRResult(text="untrusted", confidence=0.0)) is False
    assert len(cache) == 0
    assert cache.stats().rejected_writes == 2


def test_cache_evicts_the_least_recently_used_entry() -> None:
    cache = OCRRegionCache(max_entries=2)
    result = OCRResult(text="text", confidence=0.9)
    first = _key("first")
    second = _key("second")
    third = _key("third")
    cache.put(first, result)
    cache.put(second, result)
    assert cache.get(first) == result

    cache.put(third, result)

    assert cache.get(second) is None
    assert cache.get(first) == result
    assert cache.get(third) == result
    assert cache.stats().evictions == 1


def test_disabled_cache_always_computes_and_keeps_no_entries() -> None:
    cache = OCRRegionCache(max_entries=4, enabled=False)
    calls = 0

    def compute() -> OCRResult:
        nonlocal calls
        calls += 1
        return OCRResult(text="任务", confidence=0.95)

    cache.get_or_compute(_key("task"), compute)
    cache.get_or_compute(_key("task"), compute)

    assert cache.enabled is False
    assert calls == 2
    assert len(cache) == 0
    assert cache.stats().rejected_writes == 2


def test_concurrent_misses_share_one_inflight_computation() -> None:
    cache = OCRRegionCache()
    barrier = Barrier(8)
    calls = 0
    calls_lock = Lock()

    def compute() -> OCRResult:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return OCRResult(text="任务", confidence=0.95)

    def read() -> OCRResult:
        barrier.wait()
        return cache.get_or_compute(_key("concurrent"), compute)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: read(), range(8)))

    assert calls == 1
    assert all(result.text == "任务" for result in results)
    assert cache.stats().writes == 1


def test_concurrent_failure_is_broadcast_and_allows_retry() -> None:
    cache = OCRRegionCache()
    barrier = Barrier(8)
    started = Event()
    release = Event()
    calls = 0
    calls_lock = Lock()

    def failing_compute() -> OCRResult:
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(timeout=2)
        raise RuntimeError("prediction failed")

    def read() -> OCRResult:
        barrier.wait()
        return cache.get_or_compute(_key("failure"), failing_compute)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(read) for _index in range(8)]
        assert started.wait(timeout=2)
        time.sleep(0.05)
        release.set()
        for future in futures:
            with pytest.raises(RuntimeError, match="prediction failed"):
                future.result(timeout=2)

    retry = cache.get_or_compute(
        _key("failure"),
        lambda: OCRResult(text="retry succeeded", confidence=0.95),
    )

    assert calls == 1
    assert retry.text == "retry succeeded"
    assert cache.stats().writes == 1


def test_clear_detaches_old_inflight_generation() -> None:
    cache = OCRRegionCache()
    started = Event()
    release = Event()
    key = _key("generation")

    def old_compute() -> OCRResult:
        started.set()
        assert release.wait(timeout=2)
        return OCRResult(text="old", confidence=0.95)

    with ThreadPoolExecutor(max_workers=2) as executor:
        leader = executor.submit(cache.get_or_compute, key, old_compute)
        assert started.wait(timeout=2)
        waiter = executor.submit(cache.get_or_compute, key, old_compute)
        deadline = time.monotonic() + 2
        while cache.stats().misses < 2 and time.monotonic() < deadline:
            time.sleep(0.01)

        cache.clear(reset_stats=True)
        new_result = cache.get_or_compute(
            key,
            lambda: OCRResult(text="new", confidence=0.95),
        )
        release.set()

        assert leader.result(timeout=2).text == "old"
        assert waiter.result(timeout=2).text == "old"

    assert new_result.text == "new"
    assert cache.get(key).text == "new"
    assert cache.stats().writes == 1


def test_engine_state_registry_uses_identity_for_equal_and_unhashable_engines() -> None:
    class EqualEngine:
        __hash__ = lambda self: 1

        def __eq__(self, other: object) -> bool:
            return isinstance(other, EqualEngine)

    class UnhashableEngine:
        __hash__ = None

    registry = EngineStateRegistry()
    first = EqualEngine()
    second = EqualEngine()
    unhashable = UnhashableEngine()

    assert registry.get_or_create(first) is not registry.get_or_create(second)
    assert registry.get_or_create(unhashable) is registry.get_or_create(unhashable)
    assert len(registry) == 3


def test_engine_state_registry_releases_collected_engines() -> None:
    class Engine:
        pass

    registry = EngineStateRegistry()
    engine = Engine()
    registry.get_or_create(engine)
    assert len(registry) == 1

    del engine
    gc.collect()

    assert len(registry) == 0


def test_engine_state_registry_rejects_non_weak_referenceable_engines() -> None:
    class SlottedEngine:
        __slots__ = ()

    assert EngineStateRegistry().get_or_create(SlottedEngine()) is None
