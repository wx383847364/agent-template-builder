from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json

from PIL import Image

from agent_template_builder.discovery.processing import (
    PROMPT_VERSION,
    DiscoveryProcessingError,
    build_discovery_data,
    file_sha256,
    sanitize_review_candidates,
)
from agent_template_builder.discovery.prompt import build_prompt
from agent_template_builder.discovery.provider import FileDiscoveryProvider
from agent_template_builder.discovery.render import render_annotated_screenshot
from agent_template_builder.discovery.schema import (
    DiscoveryAudit,
    DiscoveryData,
    DiscoveryReview,
    ElementCandidate,
    ElementReview,
    KnownTemplateContext,
    ModelDiscoveryOutput,
    PanelCandidate,
    PanelReview,
    PreparationRequest,
    ResolutionInfo,
    ReviewApplied,
    ReviewedDiscoveryData,
    SourceInfo,
)
from agent_template_builder.ocr.base import OCREngine


EXPECTED_RESOLUTION = (1920, 1080)


def prepare_discovery(
    screenshot_path: Path,
    *,
    output_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    game_dir: Optional[Path] = None,
) -> Path:
    screenshot_path = screenshot_path.resolve()
    _validate_screenshot(screenshot_path)
    screenshot_sha = file_sha256(screenshot_path)
    run_id = run_id or _new_run_id()
    project_root = _project_root_from_cwd()
    output_dir = (
        output_dir
        or project_root / "runtime" / "discovery"
    ).resolve()
    run_dir = output_dir / f"{screenshot_path.stem}__{screenshot_sha[:8]}" / run_id
    if run_dir.exists():
        raise FileExistsError(f"discovery run already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    known_context = _known_template_context(
        screenshot_path,
        game_dir or _game_dir_from_project_root(project_root),
    )
    request = PreparationRequest(
        source=SourceInfo(
            screenshot=str(screenshot_path),
            sha256=screenshot_sha,
            resolution=ResolutionInfo(),
        ),
        run_id=run_id,
        prompt_version=PROMPT_VERSION,
        known_template_context=known_context,
    )
    request_path = run_dir / "request.json"
    _write_model(request_path, request)
    (run_dir / "prompt.md").write_text(
        build_prompt(
            screenshot=str(screenshot_path),
            sha256=screenshot_sha,
            run_id=run_id,
        ),
        encoding="utf-8",
    )
    _write_json(
        run_dir / "model_output.schema.json",
        ModelDiscoveryOutput.model_json_schema(),
    )
    placeholder = {
        "_instructions": (
            "Replace this object with one JSON object that validates against "
            "model_output.schema.json."
        )
    }
    _write_json(run_dir / "model_output.initial.json", placeholder)
    _write_json(run_dir / "model_output.final.json", placeholder)
    _write_model(
        run_dir / "audit.json",
        DiscoveryAudit(
            source_screenshot_sha256=screenshot_sha,
            source_run_id=run_id,
            source_request_sha256=file_sha256(request_path),
        ),
    )
    return run_dir


def finalize_discovery(
    run_dir: Path,
    *,
    model_output_path: Path,
    draft: bool = False,
    ocr_engine: Optional[OCREngine] = None,
    extra_warnings: tuple[str, ...] = (),
    status: str = "complete",
) -> tuple[Path, Path, Optional[Path]]:
    run_dir = run_dir.resolve()
    request = _load_model(run_dir / "request.json", PreparationRequest)
    screenshot_path = Path(request.source.screenshot)
    _validate_bound_source(screenshot_path, request)

    if not model_output_path.is_absolute():
        model_output_path = run_dir / model_output_path
    model_output_path = model_output_path.resolve()
    provider = FileDiscoveryProvider(model_output_path)
    model_output = provider.discover(screenshot_path, request)
    model_output_sha = file_sha256(model_output_path)

    data = build_discovery_data(
        screenshot_path=screenshot_path,
        request=request,
        model_output=model_output,
        model_output_sha256=model_output_sha,
        ocr_engine=ocr_engine,
        extra_warnings=extra_warnings,
        status=status,
    )

    if draft:
        data_path = run_dir / "draft.discovery.json"
        annotated_path = run_dir / "annotated.draft.png"
        review_path = None
    else:
        _require_passed_audit(
            run_dir=run_dir,
            request=request,
            model_output_sha=model_output_sha,
        )
        data_path = run_dir / "discovery.json"
        annotated_path = run_dir / "annotated.png"
        review_path = run_dir / "review.json"
        if data_path.exists():
            raise FileExistsError(
                f"final discovery is immutable and already exists: {data_path}"
            )

    _write_model(data_path, data)
    render_annotated_screenshot(screenshot_path, data, annotated_path)
    if draft:
        _write_model(
            run_dir / "audit.json",
            DiscoveryAudit(
                source_screenshot_sha256=request.source.sha256,
                source_run_id=request.run_id,
                source_request_sha256=file_sha256(run_dir / "request.json"),
                source_model_sha256=model_output_sha,
                source_draft_discovery_sha256=file_sha256(data_path),
                source_annotated_draft_sha256=file_sha256(annotated_path),
            ),
        )
    elif review_path is not None:
        review = _build_review(data, data_path)
        _write_json(
            review_path,
            review.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
        )
    return data_path, annotated_path, review_path


def apply_discovery_review(review_path: Path) -> tuple[Path, Path]:
    review_path = review_path.resolve()
    run_dir = review_path.parent
    discovery_path = run_dir / "discovery.json"
    review = _load_model(review_path, DiscoveryReview)
    discovery = _load_model(discovery_path, DiscoveryData)
    _validate_discovery_source(discovery)

    if review.source_screenshot_sha256 != discovery.source.sha256:
        raise DiscoveryProcessingError("review screenshot SHA256 does not match discovery")
    if review.source_run_id != discovery.run.run_id:
        raise DiscoveryProcessingError("review run ID does not match discovery")
    if review.source_discovery_sha256 != file_sha256(discovery_path):
        raise DiscoveryProcessingError("review discovery SHA256 does not match immutable discovery")
    _require_known_review_ids(discovery, review)

    panels = _apply_panel_reviews(discovery.panels, review)
    elements = _apply_element_reviews(discovery.elements, review)
    panels.extend(
        panel.model_copy(update={"review_status": "keep"})
        for panel in review.new_panels
    )
    elements.extend(
        element.model_copy(update={"review_status": "keep"})
        for element in review.new_elements
    )
    panels, elements, review_warnings = sanitize_review_candidates(panels, elements)

    payload = discovery.model_dump(mode="json", by_alias=True)
    payload["schema"] = "agent_ui_discovery_reviewed/v1"
    payload["panels"] = [item.model_dump(mode="json") for item in panels]
    payload["elements"] = [item.model_dump(mode="json") for item in elements]
    payload["warnings"] = list(
        dict.fromkeys([*discovery.warnings, *review_warnings])
    )
    payload["review_applied"] = ReviewApplied(
        source_review=str(review_path),
        source_review_sha256=file_sha256(review_path),
        kept_panel_count=len(panels),
        kept_element_count=len(elements),
    ).model_dump(mode="json")
    reviewed = ReviewedDiscoveryData.model_validate(payload)

    reviewed_path = run_dir / "reviewed.json"
    annotated_path = run_dir / "annotated_reviewed.png"
    _write_model(reviewed_path, reviewed)
    render_annotated_screenshot(
        Path(discovery.source.screenshot),
        reviewed,
        annotated_path,
    )
    return reviewed_path, annotated_path


def _validate_screenshot(screenshot_path: Path) -> None:
    if not screenshot_path.is_file():
        raise FileNotFoundError(f"screenshot does not exist: {screenshot_path}")
    with Image.open(screenshot_path) as image:
        if image.size != EXPECTED_RESOLUTION:
            raise ValueError(
                "unsupported_resolution: expected "
                f"{EXPECTED_RESOLUTION[0]}x{EXPECTED_RESOLUTION[1]}, "
                f"got {image.width}x{image.height}"
            )


def _validate_bound_source(
    screenshot_path: Path,
    request: PreparationRequest,
) -> None:
    _validate_screenshot(screenshot_path)
    if file_sha256(screenshot_path) != request.source.sha256:
        raise DiscoveryProcessingError("source screenshot SHA256 changed after preparation")


def _validate_discovery_source(discovery: DiscoveryData) -> None:
    screenshot_path = Path(discovery.source.screenshot)
    _validate_screenshot(screenshot_path)
    if file_sha256(screenshot_path) != discovery.source.sha256:
        raise DiscoveryProcessingError("source screenshot SHA256 changed after discovery")


def _known_template_context(
    screenshot_path: Path,
    game_dir: Path | None,
) -> KnownTemplateContext | None:
    if game_dir is None or not game_dir.is_dir():
        return None
    try:
        from agent_template_builder.pipeline.analyze import analyze_screenshot

        data = analyze_screenshot(screenshot_path, game_dir)
    except Exception:
        return None
    calibration = data.raw.get("calibration", {})
    return KnownTemplateContext(
        screen_type=data.screen.type,
        template_id=data.screen.template_id,
        confidence=data.screen.confidence,
        calibration_status=str(calibration.get("status", "unknown")),
        calibration_reason=calibration.get("reason"),
    )


def _require_passed_audit(
    *,
    run_dir: Path,
    request: PreparationRequest,
    model_output_sha: str,
) -> None:
    audit = _load_model(run_dir / "audit.json", DiscoveryAudit)
    if audit.status != "passed":
        raise DiscoveryProcessingError(
            f"final discovery requires a passed subagent audit, got {audit.status}"
        )
    expected = {
        "source_screenshot_sha256": request.source.sha256,
        "source_run_id": request.run_id,
        "source_request_sha256": file_sha256(run_dir / "request.json"),
        "source_model_sha256": model_output_sha,
        "source_draft_discovery_sha256": _required_file_sha256(
            run_dir / "draft.discovery.json"
        ),
        "source_annotated_draft_sha256": _required_file_sha256(
            run_dir / "annotated.draft.png"
        ),
    }
    for field_name, expected_value in expected.items():
        if getattr(audit, field_name) != expected_value:
            raise DiscoveryProcessingError(
                f"audit {field_name} does not match the current discovery run"
            )


def _required_file_sha256(path: Path) -> str:
    if not path.is_file():
        raise DiscoveryProcessingError(
            f"final discovery requires an audited draft artifact: {path.name}"
        )
    return file_sha256(path)


def _require_known_review_ids(
    discovery: DiscoveryData,
    review: DiscoveryReview,
) -> None:
    unknown_panels = sorted(set(review.panels) - {item.id for item in discovery.panels})
    unknown_elements = sorted(
        set(review.elements) - {item.id for item in discovery.elements}
    )
    if unknown_panels:
        raise DiscoveryProcessingError(
            f"review references unknown panel IDs: {', '.join(unknown_panels)}"
        )
    if unknown_elements:
        raise DiscoveryProcessingError(
            f"review references unknown element IDs: {', '.join(unknown_elements)}"
        )


def _build_review(data: DiscoveryData, discovery_path: Path) -> DiscoveryReview:
    return DiscoveryReview(
        source_screenshot_sha256=data.source.sha256,
        source_run_id=data.run.run_id,
        source_discovery_sha256=file_sha256(discovery_path),
        panels={item.id: PanelReview() for item in data.panels},
        elements={item.id: ElementReview() for item in data.elements},
    )


def _apply_panel_reviews(
    panels: list[PanelCandidate],
    review: DiscoveryReview,
) -> list[PanelCandidate]:
    result: list[PanelCandidate] = []
    for panel in panels:
        item_review = review.panels.get(panel.id, PanelReview())
        if item_review.decision == "discard":
            continue
        updates = item_review.overrides.model_dump(exclude_unset=True)
        updates["review_status"] = "keep"
        result.append(panel.model_copy(update=updates))
    return result


def _apply_element_reviews(
    elements: list[ElementCandidate],
    review: DiscoveryReview,
) -> list[ElementCandidate]:
    result: list[ElementCandidate] = []
    for element in elements:
        item_review = review.elements.get(element.id, ElementReview())
        if item_review.decision == "discard":
            continue
        updates = item_review.overrides.model_dump(exclude_unset=True)
        updates["review_status"] = "keep"
        result.append(element.model_copy(update=updates))
    return result


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _project_root_from_cwd() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "agent_template_builder").is_dir()
        ):
            return candidate
    return current


def _game_dir_from_project_root(project_root: Path) -> Path | None:
    candidate = project_root / "configs" / "games" / "dhxy2_classic_pc"
    return candidate if candidate.is_dir() else None


def _write_model(path: Path, model: object) -> None:
    payload = model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined]
    _write_json(path, payload)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_model(path: Path, model_type: type):
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return model_type.model_validate(payload)
