from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from typing import Callable
from weakref import ReferenceType, ref

from PIL import Image

from agent_template_builder.ocr.base import OCRResult


@dataclass(frozen=True)
class RegionCacheKey:
    template_id: str
    element_id: str
    roi_hash: str
    ocr_config_id: str


@dataclass(frozen=True)
class RegionCacheStats:
    hits: int
    misses: int
    writes: int
    evictions: int
    rejected_writes: int


@dataclass
class EngineRuntimeState:
    cache: "OCRRegionCache"
    inference_lock: RLock


@dataclass
class _EngineStateEntry:
    engine_ref: ReferenceType[object]
    state: EngineRuntimeState


def hash_roi_pixels(roi: Image.Image) -> str:
    """Return a stable hash of the ROI's visible pixels and dimensions."""
    pixels = roi.convert("RGBA")
    digest = sha256()
    digest.update(pixels.width.to_bytes(8, "big"))
    digest.update(pixels.height.to_bytes(8, "big"))
    digest.update(pixels.tobytes())
    return digest.hexdigest()


def make_region_cache_key(
    template_id: str,
    element_id: str,
    roi: Image.Image,
    ocr_config_id: str,
) -> RegionCacheKey:
    return RegionCacheKey(
        template_id=template_id,
        element_id=element_id,
        roi_hash=hash_roi_pixels(roi),
        ocr_config_id=ocr_config_id,
    )


class OCRRegionCache:
    """A bounded, process-local LRU cache for successful OCR results."""

    def __init__(self, max_entries: int = 256, *, enabled: bool = True) -> None:
        if max_entries < 0:
            raise ValueError("max_entries must be non-negative")

        self._max_entries = max_entries
        self._enabled = enabled and max_entries > 0
        self._entries: OrderedDict[RegionCacheKey, OCRResult] = OrderedDict()
        self._inflight: dict[RegionCacheKey, Future[OCRResult]] = {}
        self._lock = RLock()
        self._generation = 0
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._evictions = 0
        self._rejected_writes = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get(self, key: RegionCacheKey) -> OCRResult | None:
        with self._lock:
            if not self._enabled:
                self._misses += 1
                return None

            result = self._entries.get(key)
            if result is None:
                self._misses += 1
                return None

            self._entries.move_to_end(key)
            self._hits += 1
            return result

    def put(self, key: RegionCacheKey, result: OCRResult) -> bool:
        with self._lock:
            return self._put_locked(key, result)

    def get_or_compute(
        self,
        key: RegionCacheKey,
        compute: Callable[[], OCRResult],
        *,
        should_cache: Callable[[OCRResult], bool] | None = None,
    ) -> OCRResult:
        with self._lock:
            if not self._enabled:
                self._misses += 1
                leader = True
                future = None
            else:
                cached = self._entries.get(key)
                if cached is not None:
                    self._entries.move_to_end(key)
                    self._hits += 1
                    return cached

                self._misses += 1
                future = self._inflight.get(key)
                leader = future is None
                if leader:
                    future = Future()
                    self._inflight[key] = future
                    generation = self._generation

        if not self._enabled:
            result = compute()
            self.put(key, result)
            return result

        assert future is not None
        if not leader:
            return future.result()

        try:
            result = compute()
            should_write = should_cache is None or should_cache(result)
        except BaseException as exc:
            with self._lock:
                future.set_exception(exc)
                if self._inflight.get(key) is future:
                    self._inflight.pop(key, None)
            raise

        with self._lock:
            if generation == self._generation and should_write:
                self._put_locked(key, result)
            future.set_result(result)
            if self._inflight.get(key) is future:
                self._inflight.pop(key, None)
        return result

    def clear(self, *, reset_stats: bool = False) -> None:
        with self._lock:
            self._generation += 1
            self._entries.clear()
            self._inflight.clear()
            if reset_stats:
                self._hits = 0
                self._misses = 0
                self._writes = 0
                self._evictions = 0
                self._rejected_writes = 0

    def stats(self) -> RegionCacheStats:
        with self._lock:
            return RegionCacheStats(
                hits=self._hits,
                misses=self._misses,
                writes=self._writes,
                evictions=self._evictions,
                rejected_writes=self._rejected_writes,
            )

    def _put_locked(self, key: RegionCacheKey, result: OCRResult) -> bool:
        if not self._enabled or not _is_cacheable(result):
            self._rejected_writes += 1
            return False

        self._entries[key] = result
        self._entries.move_to_end(key)
        self._writes += 1
        if len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
            self._evictions += 1
        return True


class EngineStateRegistry:
    """Keep per-engine state by object identity, independent of equality semantics."""

    def __init__(self, cache_max_entries: int = 256) -> None:
        self._cache_max_entries = cache_max_entries
        self._entries: dict[int, _EngineStateEntry] = {}
        self._lock = RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get_or_create(self, engine: object) -> EngineRuntimeState | None:
        object_id = id(engine)
        with self._lock:
            existing = self._entries.get(object_id)
            if existing is not None and existing.engine_ref() is engine:
                return existing.state

            try:
                engine_ref = ref(engine, lambda dead_ref: self._remove(object_id, dead_ref))
            except TypeError:
                return None

            state = EngineRuntimeState(
                cache=OCRRegionCache(max_entries=self._cache_max_entries),
                inference_lock=RLock(),
            )
            self._entries[object_id] = _EngineStateEntry(engine_ref=engine_ref, state=state)
            return state

    def get(self, engine: object) -> EngineRuntimeState | None:
        with self._lock:
            entry = self._entries.get(id(engine))
            if entry is None or entry.engine_ref() is not engine:
                return None
            return entry.state

    def clear_cache(self, engine: object, *, reset_stats: bool = False) -> bool:
        state = self.get_or_create(engine)
        if state is None:
            return False
        state.cache.clear(reset_stats=reset_stats)
        return True

    def cache_stats(self, engine: object) -> RegionCacheStats | None:
        state = self.get(engine)
        return state.cache.stats() if state is not None else None

    def _remove(self, object_id: int, dead_ref: ReferenceType[object]) -> None:
        with self._lock:
            current = self._entries.get(object_id)
            if current is not None and current.engine_ref is dead_ref:
                self._entries.pop(object_id, None)


def _is_cacheable(result: OCRResult) -> bool:
    return bool(result.text.strip()) and result.confidence > 0.0
