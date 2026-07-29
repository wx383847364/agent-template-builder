from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def _validate_bbox_input(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("bbox must contain exactly four integers")
    if any(type(coordinate) is not int for coordinate in value):
        raise ValueError("bbox coordinates must be integers")
    return tuple(value)


BBox = Annotated[
    tuple[int, int, int, int],
    BeforeValidator(_validate_bbox_input),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TextContent(StrictModel):
    raw: str = ""
    normalized: str = ""


class DataFieldContent(StrictModel):
    label: Optional[str] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    current: Optional[str] = None
    max: Optional[str] = None


class SuggestedAction(StrictModel):
    action: Literal["click", "read", "input", "select", "close", "inspect", "unknown"]
    purpose: str
    confidence: float = Field(ge=0.0, le=1.0)


class SceneCandidate(StrictModel):
    type_guess: str
    display_name_guess: str
    confidence: float = Field(ge=0.0, le=1.0)


class PanelCandidate(StrictModel):
    id: str
    type_guess: str
    title: str = ""
    bbox: BBox
    modal_guess: Optional[bool] = None
    confidence: float = Field(ge=0.0, le=1.0)
    review_status: Literal["pending", "keep"] = "pending"


class ElementCandidate(StrictModel):
    id: str
    type: Literal[
        "button",
        "tab",
        "list_item",
        "input",
        "checkbox",
        "icon",
        "image",
        "text",
        "data_field",
        "unknown",
    ]
    category: Literal["action", "information", "decoration"]
    bbox: BBox
    interaction_bbox_guess: Optional[BBox] = None
    text: TextContent = Field(default_factory=TextContent)
    data_field: Optional[DataFieldContent] = None
    interactive_guess: bool = False
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    enabled_guess: Optional[bool] = None
    selected_guess: Optional[bool] = None
    semantic_role_guess: Optional[str] = None
    usefulness: Literal["high", "medium", "low", "unknown"] = "unknown"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    review_status: Literal["pending", "keep"] = "pending"
    interaction_safety: Literal["candidate_only"] = "candidate_only"


class EvidenceRecord(StrictModel):
    id: str
    source: Literal["codex_vision", "ocr", "geometry", "known_template", "audit", "human"]
    description: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ModelDiscoveryOutput(StrictModel):
    scene: SceneCandidate
    panels: list[PanelCandidate] = Field(default_factory=list)
    elements: list[ElementCandidate] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_pending_candidates(self) -> "ModelDiscoveryOutput":
        if any(item.review_status != "pending" for item in [*self.panels, *self.elements]):
            raise ValueError("model output candidates must use review_status='pending'")
        collections = {
            "panel": [item.id for item in self.panels],
            "element": [item.id for item in self.elements],
            "evidence": [item.id for item in self.evidence],
        }
        for kind, identifiers in collections.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"model output contains duplicate {kind} IDs")
        evidence_ids = set(collections["evidence"])
        missing_evidence = sorted(
            {
                evidence_id
                for element in self.elements
                for evidence_id in element.evidence_ids
                if evidence_id not in evidence_ids
            }
        )
        if missing_evidence:
            raise ValueError(
                "model output references unknown evidence IDs: "
                + ", ".join(missing_evidence)
            )
        return self


class ResolutionInfo(StrictModel):
    width: Literal[1920] = 1920
    height: Literal[1080] = 1080


class SourceInfo(StrictModel):
    screenshot: str
    sha256: str
    resolution: ResolutionInfo


class CoordinateSpace(StrictModel):
    type: Literal["full_screenshot_pixel"] = "full_screenshot_pixel"
    bbox_format: Literal["[left,top,right,bottom)"] = "[left,top,right,bottom)"


class RunInfo(StrictModel):
    run_id: str
    generation_mode: Literal["codex_client"] = "codex_client"
    prompt_version: str
    model_output_sha256: str


class KnownTemplateContext(StrictModel):
    screen_type: str
    template_id: str
    confidence: float
    calibration_status: str
    calibration_reason: Optional[str] = None


class DiscoveryData(StrictModel):
    schema_: Literal["agent_ui_discovery/v1"] = Field(
        default="agent_ui_discovery/v1",
        alias="schema",
        serialization_alias="schema",
    )
    status: Literal["complete", "partial", "failed"]
    source: SourceInfo
    coordinate_space: CoordinateSpace = Field(default_factory=CoordinateSpace)
    run: RunInfo
    known_template_context: Optional[KnownTemplateContext] = None
    scene: SceneCandidate
    panels: list[PanelCandidate] = Field(default_factory=list)
    elements: list[ElementCandidate] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AuditFinding(StrictModel):
    severity: Literal["info", "warning", "error"]
    target_kind: Literal["global", "panel", "element"]
    target_id: Optional[str] = None
    issue: str
    suggested_bbox: Optional[BBox] = None
    suggested_action: Literal["none", "add", "update", "remove"] = "none"


class DiscoveryAudit(StrictModel):
    schema_: Literal["agent_ui_discovery_audit/v1"] = Field(
        default="agent_ui_discovery_audit/v1",
        alias="schema",
        serialization_alias="schema",
    )
    status: Literal["pending", "passed", "changes_required"] = "pending"
    reviewer: str = "codex_subagent"
    source_screenshot_sha256: str = ""
    source_run_id: str = ""
    source_request_sha256: str = ""
    source_model_sha256: str = ""
    source_draft_discovery_sha256: str = ""
    source_annotated_draft_sha256: str = ""
    findings: list[AuditFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_passed_audit(self) -> "DiscoveryAudit":
        if self.status != "passed":
            return self
        hashes = {
            "source_screenshot_sha256": self.source_screenshot_sha256,
            "source_request_sha256": self.source_request_sha256,
            "source_model_sha256": self.source_model_sha256,
            "source_draft_discovery_sha256": self.source_draft_discovery_sha256,
            "source_annotated_draft_sha256": self.source_annotated_draft_sha256,
        }
        for name, value in hashes.items():
            if (
                len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"passed audit requires a lowercase SHA256 {name}")
        if not self.source_run_id:
            raise ValueError("passed audit requires source_run_id")
        if any(finding.severity == "error" for finding in self.findings):
            raise ValueError("passed audit cannot contain error findings")
        if any(finding.suggested_action != "none" for finding in self.findings):
            raise ValueError("passed audit cannot contain unresolved suggested actions")
        return self


class PanelOverrides(StrictModel):
    type_guess: Optional[str] = None
    title: Optional[str] = None
    bbox: Optional[BBox] = None
    modal_guess: Optional[bool] = None


class ElementOverrides(StrictModel):
    type: Optional[
        Literal[
            "button",
            "tab",
            "list_item",
            "input",
            "checkbox",
            "icon",
            "image",
            "text",
            "data_field",
            "unknown",
        ]
    ] = None
    category: Optional[Literal["action", "information", "decoration"]] = None
    bbox: Optional[BBox] = None
    interaction_bbox_guess: Optional[BBox] = None
    text: Optional[TextContent] = None
    data_field: Optional[DataFieldContent] = None
    semantic_role_guess: Optional[str] = None
    usefulness: Optional[Literal["high", "medium", "low", "unknown"]] = None


class PanelReview(StrictModel):
    decision: Literal["pending", "keep", "discard"] = "pending"
    overrides: PanelOverrides = Field(default_factory=PanelOverrides)


class ElementReview(StrictModel):
    decision: Literal["pending", "keep", "discard"] = "pending"
    overrides: ElementOverrides = Field(default_factory=ElementOverrides)


class DiscoveryReview(StrictModel):
    schema_: Literal["agent_ui_discovery_review/v1"] = Field(
        default="agent_ui_discovery_review/v1",
        alias="schema",
        serialization_alias="schema",
    )
    source_screenshot_sha256: str
    source_run_id: str
    source_discovery_sha256: str
    panels: dict[str, PanelReview] = Field(default_factory=dict)
    elements: dict[str, ElementReview] = Field(default_factory=dict)
    new_panels: list[PanelCandidate] = Field(default_factory=list)
    new_elements: list[ElementCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReviewApplied(StrictModel):
    source_review: str
    source_review_sha256: str
    kept_panel_count: int
    kept_element_count: int


class ReviewedDiscoveryData(DiscoveryData):
    schema_: Literal["agent_ui_discovery_reviewed/v1"] = Field(
        default="agent_ui_discovery_reviewed/v1",
        alias="schema",
        serialization_alias="schema",
    )
    review_applied: ReviewApplied


class PreparationRequest(StrictModel):
    schema_: Literal["agent_ui_discovery_request/v1"] = Field(
        default="agent_ui_discovery_request/v1",
        alias="schema",
        serialization_alias="schema",
    )
    source: SourceInfo
    run_id: str
    prompt_version: str
    known_template_context: Optional[KnownTemplateContext] = None
