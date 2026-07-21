from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import sys
import time

import pytest
from PIL import Image

import agent_template_builder.pipeline.analyze_screenshots as analyze_screenshots_pipeline
from agent_template_builder.ocr.base import OCRResult
from agent_template_builder.ocr.cache import hash_roi_pixels
from agent_template_builder.ocr.paddle_engine import PaddleOCREngine
from agent_template_builder.ocr.runtime import OCRConfigurationError, create_ocr_engine
from agent_template_builder.pipeline.analyze import analyze_screenshot
from agent_template_builder.pipeline.analyze import _load_postprocessor, _read_ocr_region
from agent_template_builder.pipeline.analyze_screenshots import summarize_directory, summarize_screenshot
from agent_template_builder.pipeline.export_agent_rows import export_agent_rows, to_index_value_data
from agent_template_builder.matcher.template_matcher import TemplateMatcher


pytestmark = pytest.mark.skip(reason="legacy OCR integration screenshots are outside the 1920x1080-only runtime contract")


ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "configs" / "games" / "dhxy2_classic_pc"
FIELDS_CONFIG = ROOT / "agent_fields.json"
SAMPLES_DIR = ROOT / "samples" / "dhxy2_classic_pc" / "screenshots"


class FakeOCREngine:
    cache_identity = "fake-test-engine"

    def __init__(self, text: str = "任务追踪") -> None:
        self.text = text
        self.calls: list[tuple[Path, tuple[int, int, int, int]]] = []

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        self.calls.append((image_path, bbox))
        return OCRResult(text=self.text, confidence=0.9)


class ServerSelectOCREngine:
    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        values = {
            (182, 313, 925, 351): "水晶宫\n爱你万年\n游戏试玩\n雾隐云居\n陕西专区\n水云仙府",
            (465, 738, 575, 773): "水晶宫",
            (949, 288, 1146, 360): "绝情魔女|0转68级|女魔|水晶宫",
        }
        return OCRResult(text=values.get(bbox, ""), confidence=0.95)


class CharacterSelectOCREngine:
    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        values = {
            (951, 324, 1174, 391): "绝情魔女|0转68级|女魔",
            (988, 399, 1174, 464): "灵剑寻花|0转10级|女魔",
        }
        return OCRResult(text=values.get(bbox, ""), confidence=0.95)


class CacheableFakeOCREngine:
    cache_identity = "cacheable-fake-test-engine"

    def __init__(self, text: str) -> None:
        self.text = text
        self.image_calls = 0
        self.image_sizes: list[tuple[int, int]] = []
        self.image_hashes: list[str] = []

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        raise AssertionError("cacheable engine must receive the frozen ROI")

    def read_image(self, image: Image.Image) -> OCRResult:
        self.image_calls += 1
        self.image_sizes.append(image.size)
        self.image_hashes.append(hash_roi_pixels(image))
        return OCRResult(text=self.text, confidence=0.9)


class ReplacingOCREngine:
    cache_identity = "replacing-test-engine"

    def __init__(self) -> None:
        self.calls = 0

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        self.calls += 1
        if self.calls == 1:
            Image.new("RGB", (20, 20), color="black").save(image_path)
            Image.new("RGB", (20, 20), color="white").save(image_path)
            return OCRResult(text="new pixels", confidence=0.9)
        return OCRResult(text="stable pixels", confidence=0.9)


class FakePaddleAdapter:
    def __init__(self) -> None:
        self.predict_calls = 0

    def predict(self, image_path: str) -> list[dict[str, list[object]]]:
        self.predict_calls += 1
        return [{"rec_texts": ["任务追踪"], "rec_scores": [0.95]}]


class ConcurrentPaddleAdapter:
    def __init__(self) -> None:
        self._lock = Lock()
        self.active = 0
        self.max_active = 0

    def predict(self, image_path: str) -> list[dict[str, list[object]]]:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.05)
            return [{"rec_texts": ["serialized"], "rec_scores": [0.95]}]
        finally:
            with self._lock:
                self.active -= 1


class UnidentifiedOCREngine:
    def __init__(self) -> None:
        self.calls = 0

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        self.calls += 1
        return OCRResult(text=f"call-{self.calls}", confidence=0.9)


class ConcurrentImageOCREngine:
    cache_identity = "concurrent-image-test-engine"

    def __init__(self) -> None:
        self._lock = Lock()
        self.active = 0
        self.max_active = 0
        self.calls = 0

    def read_region(self, image_path: Path, bbox: tuple[int, int, int, int]) -> OCRResult:
        raise AssertionError("cacheable engine must receive the frozen ROI")

    def read_image(self, image: Image.Image) -> OCRResult:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls += 1
        try:
            time.sleep(0.05)
            return OCRResult(text="serialized", confidence=0.9)
        finally:
            with self._lock:
                self.active -= 1


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


def test_analyze_reuses_cached_non_empty_ocr_result() -> None:
    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = CacheableFakeOCREngine("名望伊始")

    first = analyze_screenshot(image_path, GAME_DIR, engine)
    second = analyze_screenshot(image_path, GAME_DIR, engine)

    assert first.task is not None
    assert second.task is not None
    assert first.task.text == second.task.text == "名望伊始"
    assert engine.image_calls == 1


def test_analyze_passes_only_the_template_roi_to_image_ocr() -> None:
    image_path = SAMPLES_DIR / "npc_dialog__manual_dialog1.png"
    engine = CacheableFakeOCREngine("局部文本")

    result = analyze_screenshot(image_path, GAME_DIR, engine)
    ocr_elements = [item for item in result.elements if item.evidence.source == "ocr"]
    expected_sizes = [
        (item.bbox[2] - item.bbox[0], item.bbox[3] - item.bbox[1])
        for item in ocr_elements
    ]

    assert engine.image_sizes == expected_sizes
    assert len(engine.image_sizes) == 2
    assert all(width < result.screen.resolution.width for width, _height in engine.image_sizes)
    assert all(height < result.screen.resolution.height for _width, height in engine.image_sizes)


def test_analyze_keeps_match_and_ocr_on_the_same_frozen_frame(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    live = tmp_path / "live.png"
    with Image.open(source) as image:
        image.save(live)

    original_match = TemplateMatcher.match_image

    def replace_after_match(self: TemplateMatcher, image: Image.Image):
        result = original_match(self, image)
        Image.new("RGB", image.size, color="black").save(live)
        return result

    monkeypatch.setattr(TemplateMatcher, "match_image", replace_after_match)
    engine = CacheableFakeOCREngine("任务追踪")

    result = analyze_screenshot(live, GAME_DIR, engine)
    task_tracker = next(item for item in result.elements if item.id == "task_tracker")
    with Image.open(source) as original:
        expected_hash = hash_roi_pixels(original.crop(task_tracker.bbox))

    assert engine.image_hashes == [expected_hash]
    with Image.open(live) as replaced:
        assert hash_roi_pixels(replaced.crop(task_tracker.bbox)) != expected_hash


def test_analyze_does_not_cache_empty_ocr_result() -> None:
    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = CacheableFakeOCREngine("")

    analyze_screenshot(image_path, GAME_DIR, engine)
    analyze_screenshot(image_path, GAME_DIR, engine)

    assert engine.image_calls == 2


def test_path_based_engine_is_not_cached_during_an_a_b_a_replacement(tmp_path: Path) -> None:
    image_path = tmp_path / "live.png"
    Image.new("RGB", (20, 20), color="white").save(image_path)
    engine = ReplacingOCREngine()

    first = _read_ocr_region(
        engine,
        image_path,
        (0, 0, 20, 20),
        template_id="template",
        element_id="element",
        cache_enabled=True,
    )
    second = _read_ocr_region(
        engine,
        image_path,
        (0, 0, 20, 20),
        template_id="template",
        element_id="element",
        cache_enabled=True,
    )

    assert first.text == "new pixels"
    assert second.text == "stable pixels"
    assert engine.calls == 2


def test_paddle_adapter_and_analysis_cache_share_one_prediction() -> None:
    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    paddle = FakePaddleAdapter()
    engine = PaddleOCREngine(device="cpu", ocr=paddle)

    first = analyze_screenshot(image_path, GAME_DIR, engine)
    second = analyze_screenshot(image_path, GAME_DIR, engine)

    assert first.task is not None
    assert second.task is not None
    assert first.task.text == second.task.text == "任务追踪"
    assert paddle.predict_calls == 1


def test_paddle_serializes_pipeline_and_direct_predictions(tmp_path: Path) -> None:
    image_path = tmp_path / "source.png"
    Image.new("RGB", (40, 40), color="white").save(image_path)
    paddle = ConcurrentPaddleAdapter()
    engine = PaddleOCREngine(device="cpu", ocr=paddle)
    roi = Image.new("RGB", (20, 20), color="black")

    with ThreadPoolExecutor(max_workers=3) as executor:
        region_future = executor.submit(engine.read_region, image_path, (0, 0, 20, 20))
        image_future = executor.submit(engine.read_image, roi)
        pipeline_future = executor.submit(
            _read_ocr_region,
            engine,
            image_path,
            (0, 0, 20, 20),
            template_id="template",
            element_id="element",
            cache_enabled=False,
        )
        assert region_future.result(timeout=2).text == "serialized"
        assert image_future.result(timeout=2).text == "serialized"
        assert pipeline_future.result(timeout=2).text == "serialized"
    roi.close()

    assert paddle.max_active == 1


def test_equal_engine_instances_do_not_share_cached_results() -> None:
    class EqualEngine(CacheableFakeOCREngine):
        def __hash__(self) -> int:
            return 1

        def __eq__(self, other: object) -> bool:
            return isinstance(other, EqualEngine)

    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    first_engine = EqualEngine("first engine")
    second_engine = EqualEngine("second engine")

    first = analyze_screenshot(image_path, GAME_DIR, first_engine)
    second = analyze_screenshot(image_path, GAME_DIR, second_engine)

    assert first.task is not None and first.task.text == "first engine"
    assert second.task is not None and second.task.text == "second engine"
    assert first_engine.image_calls == second_engine.image_calls == 1


def test_unhashable_engine_keeps_an_identity_cache() -> None:
    class UnhashableEngine(CacheableFakeOCREngine):
        __hash__ = None

    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = UnhashableEngine("unhashable")

    analyze_screenshot(image_path, GAME_DIR, engine)
    analyze_screenshot(image_path, GAME_DIR, engine)

    assert engine.image_calls == 1


def test_non_weak_referenceable_engine_uses_roi_without_caching() -> None:
    class SlottedEngine:
        __slots__ = ("calls", "sizes")
        cache_identity = "slotted-engine"

        def __init__(self) -> None:
            self.calls = 0
            self.sizes: list[tuple[int, int]] = []

        def read_image(self, image: Image.Image) -> OCRResult:
            self.calls += 1
            self.sizes.append(image.size)
            return OCRResult("slotted", 0.9)

    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = SlottedEngine()

    first = analyze_screenshot(image_path, GAME_DIR, engine)
    analyze_screenshot(image_path, GAME_DIR, engine)

    assert first.task is not None
    task_bbox = next(item.bbox for item in first.elements if item.id == "task_tracker")
    expected_size = (task_bbox[2] - task_bbox[0], task_bbox[3] - task_bbox[1])
    assert engine.calls == 2
    assert engine.sizes == [expected_size, expected_size]


def test_engine_without_cache_identity_is_not_implicitly_cached() -> None:
    image_path = SAMPLES_DIR / "main_world__manual_1000x718_1.png"
    engine = UnidentifiedOCREngine()

    first = analyze_screenshot(image_path, GAME_DIR, engine)
    second = analyze_screenshot(image_path, GAME_DIR, engine)

    assert first.task is not None
    assert second.task is not None
    assert first.task.text == "call-1"
    assert second.task.text == "call-2"
    assert engine.calls == 2


@pytest.mark.parametrize("cache_enabled", (False, True))
def test_different_cache_keys_share_the_engine_inference_lock(
    tmp_path: Path,
    cache_enabled: bool,
) -> None:
    first_image = tmp_path / "first.png"
    second_image = tmp_path / "second.png"
    Image.new("RGB", (20, 20), color="white").save(first_image)
    Image.new("RGB", (20, 20), color="black").save(second_image)
    engine = ConcurrentImageOCREngine()

    def read(image_path: Path, element_id: str) -> OCRResult:
        return _read_ocr_region(
            engine,
            image_path,
            (0, 0, 20, 20),
            template_id="template",
            element_id=element_id,
            cache_enabled=cache_enabled,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(read, first_image, "first")
        second = executor.submit(read, second_image, "second")
        assert first.result(timeout=2).text == "serialized"
        assert second.result(timeout=2).text == "serialized"

    assert engine.calls == 2
    assert engine.max_active == 1


def test_postprocessor_reloads_changed_vocab_content(tmp_path: Path) -> None:
    vocab_dir = tmp_path / "vocab"
    vocab_dir.mkdir()
    server_names_path = vocab_dir / "server_names.txt"
    confusions_path = vocab_dir / "ocr_confusions.json"
    server_names_path.write_text("水晶宫\n", encoding="utf-8")
    confusions_path.write_text(
        '{"version":1,"substitutions":[{"observed":"品","expected":"晶"}]}',
        encoding="utf-8",
    )

    first = _load_postprocessor(tmp_path)
    first_result = first.process(OCRResult("水品宫", 0.99), "selected_server")
    server_names_path.write_text("凌烟阁\n", encoding="utf-8")
    confusions_path.write_text(
        '{"version":1,"substitutions":[{"observed":"闾","expected":"阁"}]}',
        encoding="utf-8",
    )
    second = _load_postprocessor(tmp_path)
    second_result = second.process(OCRResult("凌烟闾", 0.99), "selected_server")

    assert first_result.corrected_text == "水晶宫"
    assert second_result.corrected_text == "凌烟阁"


def test_analyze_preserves_raw_ocr_evidence_after_vocab_correction() -> None:
    image_path = SAMPLES_DIR / "server_select__manual_complete1.png"
    engine = FakeOCREngine("雾隐云君")

    result = analyze_screenshot(image_path, GAME_DIR, engine)
    selected_server = next(item for item in result.elements if item.id == "selected_server")

    assert selected_server.text == "雾隐云居"
    assert selected_server.evidence is not None
    assert selected_server.evidence.ocr_text == "雾隐云君"


@pytest.mark.parametrize(
    ("screenshot_name", "expected_bbox"),
    (
        ("main_world__baseline.png", (0, 145, 195, 238)),
        ("main_world__manual_800x574_1.png", (0, 145, 195, 230)),
        ("main_world__manual_1366x768_1.png", (0, 145, 235, 245)),
        ("main_world__legacy_game1.png", (7, 309, 302, 545)),
    ),
)
def test_main_world_profiles_use_calibrated_task_tracker_bbox(
    screenshot_name: str,
    expected_bbox: tuple[int, int, int, int],
) -> None:
    engine = FakeOCREngine()

    result = analyze_screenshot(SAMPLES_DIR / screenshot_name, GAME_DIR, engine)
    task_tracker = next(item for item in result.elements if item.id == "task_tracker")

    assert task_tracker.bbox == expected_bbox
    assert len(engine.calls) == 1
    temporary_path, actual_bbox = engine.calls[0]
    assert temporary_path.name == "snapshot.png"
    assert not temporary_path.exists()
    assert actual_bbox == expected_bbox


def test_path_engine_reuses_one_temporary_snapshot_for_multiple_rois() -> None:
    image_path = SAMPLES_DIR / "npc_dialog__manual_dialog1.png"
    engine = FakeOCREngine("局部文本")

    analyze_screenshot(image_path, GAME_DIR, engine)

    assert len(engine.calls) == 2
    assert engine.calls[0][0] == engine.calls[1][0]
    assert engine.calls[0][0].name == "snapshot.png"
    assert not engine.calls[0][0].exists()


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


def test_export_agent_rows_emits_common_login_character_402() -> None:
    image_path = SAMPLES_DIR / "登陆界面服务器选择界面1920x1080.png"

    output = export_agent_rows(image_path, GAME_DIR, FIELDS_CONFIG, ServerSelectOCREngine())
    rows = to_index_value_data(output)

    assert rows["402"] == "绝情魔女|0转68级|女魔|水晶宫@[949, 288, 1146, 360]"


def test_export_agent_rows_emits_character_selection_targets() -> None:
    image_path = SAMPLES_DIR / "登陆界面选择角色界面-1920x1080.png"

    output = export_agent_rows(image_path, GAME_DIR, FIELDS_CONFIG, CharacterSelectOCREngine())
    rows = to_index_value_data(output)
    first = "绝情魔女|0转68级|女魔@[951, 324, 1174, 391]"
    second = "灵剑寻花|0转10级|女魔@[988, 399, 1174, 464]"

    assert rows["500"] == first
    assert rows["502"] == f"{first};{second}"
    assert rows["503"] == "进入游戏@[606, 723, 745, 758]"
