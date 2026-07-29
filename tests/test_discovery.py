from __future__ import annotations

from pathlib import Path
import json

import pytest
from PIL import Image
from pydantic import ValidationError

from agent_template_builder.discovery.processing import DiscoveryProcessingError, file_sha256
from agent_template_builder.discovery.provider import FileDiscoveryProvider
from agent_template_builder.discovery.schema import (
    DiscoveryAudit,
    DiscoveryData,
    ModelDiscoveryOutput,
    PreparationRequest,
    ReviewedDiscoveryData,
)
from agent_template_builder.discovery.workflow import (
    apply_discovery_review,
    finalize_discovery,
    prepare_discovery,
)
from agent_template_builder.exporters.agent_rows import AgentRowsExporter
from agent_template_builder.ocr.base import OCRResult


def _screenshot(tmp_path: Path, size: tuple[int, int] = (1920, 1080)) -> Path:
    path = tmp_path / "screen.png"
    Image.new("RGB", size, (20, 30, 40)).save(path)
    return path


def _model_payload() -> dict[str, object]:
    return {
        "scene": {
            "type_guess": "character_attributes",
            "display_name_guess": "人物属性",
            "confidence": 0.92,
        },
        "panels": [
            {
                "id": "panel_attributes",
                "type_guess": "character_attributes",
                "title": "人物属性",
                "bbox": [200, 100, 1100, 900],
                "modal_guess": False,
                "confidence": 0.95,
                "review_status": "pending",
            },
            {
                "id": "empty_panel",
                "type_guess": "unknown",
                "title": "",
                "bbox": [10, 10, 10, 20],
                "modal_guess": None,
                "confidence": 0.2,
                "review_status": "pending",
            },
        ],
        "elements": [
            {
                "id": "button_add",
                "type": "button",
                "category": "action",
                "bbox": [-10, 620, 180, 680],
                "interaction_bbox_guess": [5, 628, 170, 672],
                "text": {"raw": "加点", "normalized": "加点"},
                "data_field": None,
                "interactive_guess": True,
                "suggested_actions": [
                    {
                        "action": "click",
                        "purpose": "分配属性点",
                        "confidence": 0.85,
                    }
                ],
                "enabled_guess": True,
                "selected_guess": False,
                "semantic_role_guess": "allocate_attribute_points",
                "usefulness": "high",
                "confidence": 0.9,
                "evidence_ids": ["ev_button"],
                "review_status": "pending",
                "interaction_safety": "candidate_only",
            },
            {
                "id": "button_add_duplicate",
                "type": "button",
                "category": "action",
                "bbox": [0, 620, 180, 680],
                "interaction_bbox_guess": None,
                "text": {"raw": "", "normalized": ""},
                "data_field": None,
                "interactive_guess": True,
                "suggested_actions": [],
                "enabled_guess": None,
                "selected_guess": None,
                "semantic_role_guess": None,
                "usefulness": "medium",
                "confidence": 0.6,
                "evidence_ids": [],
                "review_status": "pending",
                "interaction_safety": "candidate_only",
            },
            {
                "id": "player_hp",
                "type": "data_field",
                "category": "information",
                "bbox": [500, 250, 760, 290],
                "interaction_bbox_guess": None,
                "text": {"raw": "", "normalized": ""},
                "data_field": {
                    "label": "气血",
                    "value": "12580/12580",
                    "unit": None,
                    "current": "12580",
                    "max": "12580",
                },
                "interactive_guess": False,
                "suggested_actions": [],
                "enabled_guess": None,
                "selected_guess": None,
                "semantic_role_guess": "player_hp",
                "usefulness": "high",
                "confidence": 0.93,
                "evidence_ids": ["ev_hp"],
                "review_status": "pending",
                "interaction_safety": "candidate_only",
            },
        ],
        "evidence": [
            {
                "id": "ev_button",
                "source": "codex_vision",
                "description": "可见按钮",
                "confidence": 0.9,
            },
            {
                "id": "ev_hp",
                "source": "codex_vision",
                "description": "可见气血字段",
                "confidence": 0.93,
            },
        ],
        "warnings": [],
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _prepared_run(tmp_path: Path) -> tuple[Path, Path]:
    screenshot = _screenshot(tmp_path)
    run_dir = prepare_discovery(
        screenshot,
        output_dir=tmp_path / "discovery",
        run_id="run-test",
        game_dir=tmp_path / "missing-game",
    )
    return screenshot, run_dir


def _pass_audit(run_dir: Path, model_output: Path) -> None:
    request_path = run_dir / "request.json"
    request = PreparationRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    draft_path = run_dir / "draft.discovery.json"
    annotated_path = run_dir / "annotated.draft.png"
    audit = DiscoveryAudit.model_validate_json(
        (run_dir / "audit.json").read_text(encoding="utf-8")
    ).model_copy(
        update={
            "status": "passed",
            "source_screenshot_sha256": request.source.sha256,
            "source_run_id": request.run_id,
            "source_request_sha256": file_sha256(request_path),
            "source_model_sha256": file_sha256(model_output),
            "source_draft_discovery_sha256": file_sha256(draft_path),
            "source_annotated_draft_sha256": file_sha256(annotated_path),
            "notes": ["独立检查通过"],
        }
    )
    _write_json(
        run_dir / "audit.json",
        audit.model_dump(mode="json", by_alias=True),
    )


def _draft_and_pass_audit(run_dir: Path, model_output: Path) -> None:
    finalize_discovery(
        run_dir,
        model_output_path=model_output,
        draft=True,
    )
    _pass_audit(run_dir, model_output)


def test_prepare_rejects_non_1920_without_creating_run(tmp_path: Path) -> None:
    screenshot = _screenshot(tmp_path, (1280, 720))
    output_dir = tmp_path / "discovery"

    with pytest.raises(ValueError, match="unsupported_resolution"):
        prepare_discovery(screenshot, output_dir=output_dir)

    assert not output_dir.exists()


def test_prepare_creates_prompt_schema_and_flat_contract(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)

    assert (run_dir / "request.json").is_file()
    assert (run_dir / "prompt.md").is_file()
    assert (run_dir / "model_output.schema.json").is_file()
    assert (run_dir / "model_output.initial.json").is_file()
    assert (run_dir / "audit.json").is_file()
    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "不使用 game_view" in prompt
    assert "禁止 parent_id、panel_id、z_index" in prompt

    payload = _model_payload()
    payload["panels"][0]["parent_id"] = "forbidden"  # type: ignore[index]
    with pytest.raises(ValidationError, match="parent_id"):
        ModelDiscoveryOutput.model_validate(payload)


def test_file_provider_rejects_element_layout_relationship(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    payload = _model_payload()
    payload["elements"][0]["panel_id"] = "panel_attributes"  # type: ignore[index]
    output = run_dir / "bad.json"
    _write_json(output, payload)
    request = PreparationRequest.model_validate_json(
        (run_dir / "request.json").read_text(encoding="utf-8")
    )

    with pytest.raises(ValidationError, match="panel_id"):
        FileDiscoveryProvider(output).discover(Path(request.source.screenshot), request)


@pytest.mark.parametrize(
    "bbox",
    (
        [0, 0, 10],
        [0, 0, 10, 10.5],
        [0, 0, "10", 10],
        [0, 0, True, 10],
    ),
)
def test_model_output_rejects_non_integer_bbox(bbox: object) -> None:
    payload = _model_payload()
    payload["elements"][0]["bbox"] = bbox  # type: ignore[index]

    with pytest.raises(ValidationError, match="bbox"):
        ModelDiscoveryOutput.model_validate(payload)


def test_model_output_rejects_coerced_confidence() -> None:
    payload = _model_payload()
    payload["scene"]["confidence"] = "0.92"  # type: ignore[index]

    with pytest.raises(ValidationError, match="confidence"):
        ModelDiscoveryOutput.model_validate(payload)


def test_model_output_rejects_duplicate_and_unknown_evidence_ids() -> None:
    payload = _model_payload()
    payload["evidence"].append(payload["evidence"][0].copy())  # type: ignore[index,union-attr]
    with pytest.raises(ValidationError, match="duplicate evidence IDs"):
        ModelDiscoveryOutput.model_validate(payload)

    payload = _model_payload()
    payload["elements"][0]["evidence_ids"] = ["missing"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown evidence IDs"):
        ModelDiscoveryOutput.model_validate(payload)


def test_draft_finalize_clips_rejects_and_deduplicates_bbox(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.initial.json"
    _write_json(model_output, _model_payload())

    data_path, annotated_path, review_path = finalize_discovery(
        run_dir,
        model_output_path=model_output,
        draft=True,
    )

    assert review_path is None
    data = DiscoveryData.model_validate_json(data_path.read_text(encoding="utf-8"))
    assert [item.id for item in data.panels] == ["panel_attributes"]
    assert [item.id for item in data.elements] == ["button_add", "player_hp"]
    assert data.elements[0].bbox == (0, 620, 180, 680)
    assert any("clipped" in warning for warning in data.warnings)
    assert any("rejected empty bbox" in warning for warning in data.warnings)
    assert any("deduplicated element" in warning for warning in data.warnings)
    with Image.open(annotated_path) as annotated:
        assert annotated.size == (1920, 1080)


def test_draft_deduplicates_same_type_panels(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    payload = _model_payload()
    duplicate = payload["panels"][0].copy()  # type: ignore[index,union-attr]
    duplicate["id"] = "panel_attributes_duplicate"
    duplicate["title"] = ""
    duplicate["bbox"] = [205, 105, 1095, 895]
    payload["panels"].append(duplicate)  # type: ignore[union-attr]
    model_output = run_dir / "model_output.initial.json"
    _write_json(model_output, payload)

    data_path, _, _ = finalize_discovery(
        run_dir,
        model_output_path=model_output,
        draft=True,
    )

    data = DiscoveryData.model_validate_json(data_path.read_text(encoding="utf-8"))
    assert [item.id for item in data.panels] == ["panel_attributes"]
    assert any("deduplicated panel" in warning for warning in data.warnings)


def test_final_requires_passed_audit_bound_to_final_model_output(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.final.json"
    _write_json(model_output, _model_payload())

    with pytest.raises(DiscoveryProcessingError, match="passed subagent audit"):
        finalize_discovery(run_dir, model_output_path=model_output)

    _draft_and_pass_audit(run_dir, model_output)
    data_path, annotated_path, review_path = finalize_discovery(
        run_dir,
        model_output_path=model_output,
    )

    assert data_path.name == "discovery.json"
    assert annotated_path.name == "annotated.png"
    assert review_path is not None and review_path.name == "review.json"
    assert data_path.is_file() and annotated_path.is_file() and review_path.is_file()


def test_final_rejects_audit_for_different_model_output(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.final.json"
    _write_json(model_output, _model_payload())
    _draft_and_pass_audit(run_dir, model_output)
    payload = _model_payload()
    payload["warnings"] = ["changed after audit"]
    _write_json(model_output, payload)

    with pytest.raises(DiscoveryProcessingError, match="source_model_sha256"):
        finalize_discovery(run_dir, model_output_path=model_output)


def test_final_rejects_audit_copied_from_different_run_and_screenshot(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_screenshot = _screenshot(first_dir)
    second_screenshot = _screenshot(second_dir)
    Image.new("RGB", (1920, 1080), (70, 80, 90)).save(second_screenshot)
    first_run = prepare_discovery(
        first_screenshot,
        output_dir=tmp_path / "runs",
        run_id="first-run",
        game_dir=tmp_path / "missing-game",
    )
    second_run = prepare_discovery(
        second_screenshot,
        output_dir=tmp_path / "runs",
        run_id="second-run",
        game_dir=tmp_path / "missing-game",
    )
    first_model = first_run / "model_output.final.json"
    second_model = second_run / "model_output.final.json"
    _write_json(first_model, _model_payload())
    _write_json(second_model, _model_payload())
    _draft_and_pass_audit(first_run, first_model)
    finalize_discovery(second_run, model_output_path=second_model, draft=True)
    _write_json(
        second_run / "audit.json",
        json.loads((first_run / "audit.json").read_text(encoding="utf-8")),
    )

    with pytest.raises(DiscoveryProcessingError, match="source_screenshot_sha256"):
        finalize_discovery(second_run, model_output_path=second_model)


def test_review_discards_overrides_and_adds_elements(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.final.json"
    _write_json(model_output, _model_payload())
    _draft_and_pass_audit(run_dir, model_output)
    discovery_path, _, review_path = finalize_discovery(
        run_dir,
        model_output_path=model_output,
    )
    assert review_path is not None
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["panels"]["panel_attributes"] = {
        "decision": "keep",
        "overrides": {"title": "人物属性（确认）", "bbox": [210, 110, 1090, 890]},
    }
    review["elements"]["button_add"] = {
        "decision": "discard",
        "overrides": {},
    }
    new_element = _model_payload()["elements"][0].copy()  # type: ignore[index,union-attr]
    new_element["id"] = "close_button"
    new_element["bbox"] = [1050, 120, 1080, 150]
    new_element["text"] = {"raw": "关闭", "normalized": "关闭"}
    review["new_elements"] = [new_element]
    _write_json(review_path, review)

    reviewed_path, annotated_path = apply_discovery_review(review_path)

    reviewed = ReviewedDiscoveryData.model_validate_json(
        reviewed_path.read_text(encoding="utf-8")
    )
    assert reviewed.source.sha256 == DiscoveryData.model_validate_json(
        discovery_path.read_text(encoding="utf-8")
    ).source.sha256
    assert reviewed.panels[0].title == "人物属性（确认）"
    assert reviewed.panels[0].review_status == "keep"
    assert {item.id for item in reviewed.elements} == {"player_hp", "close_button"}
    assert all(item.review_status == "keep" for item in reviewed.elements)
    assert reviewed.review_applied.kept_element_count == 2
    assert annotated_path.is_file()


def test_review_rejects_mismatched_discovery_digest(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.final.json"
    _write_json(model_output, _model_payload())
    _draft_and_pass_audit(run_dir, model_output)
    _, _, review_path = finalize_discovery(run_dir, model_output_path=model_output)
    assert review_path is not None
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["source_discovery_sha256"] = "0" * 64
    _write_json(review_path, review)

    with pytest.raises(DiscoveryProcessingError, match="discovery SHA256"):
        apply_discovery_review(review_path)


def test_review_rejects_unknown_element_id(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.final.json"
    _write_json(model_output, _model_payload())
    _draft_and_pass_audit(run_dir, model_output)
    _, _, review_path = finalize_discovery(run_dir, model_output_path=model_output)
    assert review_path is not None
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["elements"]["does_not_exist"] = {
        "decision": "discard",
        "overrides": {},
    }
    _write_json(review_path, review)

    with pytest.raises(DiscoveryProcessingError, match="unknown element IDs"):
        apply_discovery_review(review_path)


def test_review_rejects_source_screenshot_changed_after_discovery(tmp_path: Path) -> None:
    screenshot, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.final.json"
    _write_json(model_output, _model_payload())
    _draft_and_pass_audit(run_dir, model_output)
    _, _, review_path = finalize_discovery(run_dir, model_output_path=model_output)
    assert review_path is not None
    Image.new("RGB", (1920, 1080), (99, 88, 77)).save(screenshot)

    with pytest.raises(DiscoveryProcessingError, match="changed after discovery"):
        apply_discovery_review(review_path)


class _FakeOCR:
    def read_region(
        self,
        image_path: Path,
        bbox: tuple[int, int, int, int],
    ) -> OCRResult:
        del image_path, bbox
        return OCRResult(text="OCR复核", confidence=0.88)


class _FailingOCR:
    def read_region(
        self,
        image_path: Path,
        bbox: tuple[int, int, int, int],
    ) -> OCRResult:
        del image_path, bbox
        raise RuntimeError("temporary OCR failure")


def test_discovery_ocr_adds_evidence_without_overwriting_codex_text(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.initial.json"
    _write_json(model_output, _model_payload())

    data_path, _, _ = finalize_discovery(
        run_dir,
        model_output_path=model_output,
        draft=True,
        ocr_engine=_FakeOCR(),
    )

    data = DiscoveryData.model_validate_json(data_path.read_text(encoding="utf-8"))
    button = next(item for item in data.elements if item.id == "button_add")
    assert button.text.raw == "加点"
    assert "ocr_button_add" in button.evidence_ids
    assert any(item.id == "ocr_button_add" for item in data.evidence)
    assert any("differs from OCR" in warning for warning in data.warnings)


def test_discovery_ocr_collision_uses_new_evidence_id(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    payload = _model_payload()
    payload["evidence"].append(  # type: ignore[union-attr]
        {
            "id": "ocr_button_add",
            "source": "codex_vision",
            "description": "模型已占用同名证据",
            "confidence": 0.5,
        }
    )
    model_output = run_dir / "model_output.initial.json"
    _write_json(model_output, payload)

    data_path, _, _ = finalize_discovery(
        run_dir,
        model_output_path=model_output,
        draft=True,
        ocr_engine=_FakeOCR(),
    )

    data = DiscoveryData.model_validate_json(data_path.read_text(encoding="utf-8"))
    button = next(item for item in data.elements if item.id == "button_add")
    assert "ocr_button_add_2" in button.evidence_ids
    ocr_evidence = next(item for item in data.evidence if item.id == "ocr_button_add_2")
    assert ocr_evidence.source == "ocr"


def test_discovery_ocr_failure_keeps_codex_candidate(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.initial.json"
    _write_json(model_output, _model_payload())

    data_path, _, _ = finalize_discovery(
        run_dir,
        model_output_path=model_output,
        draft=True,
        ocr_engine=_FailingOCR(),
    )

    data = DiscoveryData.model_validate_json(data_path.read_text(encoding="utf-8"))
    button = next(item for item in data.elements if item.id == "button_add")
    assert button.text.raw == "加点"
    assert any("OCR verification failed" in warning for warning in data.warnings)


def test_discovery_is_not_agent_data_or_stable_click_output(tmp_path: Path) -> None:
    _, run_dir = _prepared_run(tmp_path)
    model_output = run_dir / "model_output.initial.json"
    _write_json(model_output, _model_payload())
    data_path, _, _ = finalize_discovery(
        run_dir,
        model_output_path=model_output,
        draft=True,
    )
    data = DiscoveryData.model_validate_json(data_path.read_text(encoding="utf-8"))

    assert not hasattr(data, "game")
    assert not hasattr(data, "state")
    assert all(item.interaction_safety == "candidate_only" for item in data.elements)
    exporter = AgentRowsExporter.from_config_path(
        Path(__file__).parents[1] / "agent_fields.json"
    )
    with pytest.raises(TypeError, match="DiscoveryData candidates"):
        exporter.export(data)  # type: ignore[arg-type]
