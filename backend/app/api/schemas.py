"""API request/response schemas."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.schemas.data_connection import (
    DataConnectionCreate,
    DataConnectionOut,
    DataConnectionValidateOut,
    DataConnectionObjectsOut,
)


class BoundingBoxSchema(BaseModel):
    """Percent of natural image (0–100), top-left origin."""

    x: float
    y: float
    w: float
    h: float

    @field_validator("x", "y", "w", "h")
    @classmethod
    def finite(cls, v: float) -> float:
        if v != v:  # NaN
            raise ValueError("bbox values must be finite")
        return v


from pydantic import BaseModel, Field, field_serializer, field_validator


class QualityPolicySchema(BaseModel):
    confidence_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    auto_approve_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    qc_sample_rate: float = Field(default=0.05, ge=0.02, le=0.05)
    sample_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    notes: str = ""

    @field_validator("confidence_threshold", "auto_approve_threshold", "qc_sample_rate", "sample_rate", mode="before")
    @classmethod
    def normalize_percentages(cls, v: Any) -> float:
        if v is None:
            return 0.05
        try:
            val = float(v)
            if val > 1.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.05


class VideoConfigSchema(BaseModel):
    requested_capabilities: list[str] = Field(default_factory=list)
    objective: str = ""


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    goal: str = ""
    task_type: Literal[
        "object_detection", "segmentation", "classification",
        "ENTITY_EXTRACTION", "SENTIMENT_ANALYSIS", "TEXT_CLASSIFICATION", "RELATION_EXTRACTION", "DRUG_MATCHING", "NER"
    ] = "object_detection"
    classification_mode: Literal["single", "multi"] = "single"
    labels: list[str] = Field(default_factory=list)
    label_ontology: list[Any] = Field(default_factory=list)
    label_strategy: str = "generic"
    expected_output_format: str | None = Field(default=None, description="Expected output format: COCO JSON, YOLO, Pascal VOC, LabelMe, CreateML, CSV, JSON")
    quality_policy: QualityPolicySchema = Field(default_factory=QualityPolicySchema)
    modality: Literal["image", "video", "text", "document"] = "image"
    video_config: VideoConfigSchema | None = None
    confidence_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    high_confidence_qc_sample_rate: float = Field(default=0.02, ge=0.02, le=0.05)
    annotation_guidelines: str = ""
    sentiment_analysis_level: Literal["document", "page", "paragraph", "sentence"] = "document"
    classification_analysis_level: Literal["document", "page", "paragraph", "sentence"] = "document"


class ProjectUpdate(BaseModel):
    name: str | None = None
    goal: str | None = None
    labels: list[str] | None = None
    label_strategy: str | None = None
    expected_output_format: str | None = None
    quality_policy: QualityPolicySchema | None = None
    status: str | None = None
    modality: str | None = None
    video_config: VideoConfigSchema | None = None
    confidence_threshold: float | None = None
    high_confidence_qc_sample_rate: float | None = None
    annotation_guidelines: str | None = None
    sentiment_analysis_level: Literal["document", "page", "paragraph", "sentence"] | None = None
    classification_analysis_level: Literal["document", "page", "paragraph", "sentence"] | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    goal: str
    task_type: str
    classification_mode: str = "single"
    labels: list[str]
    label_ontology: list[Any] = Field(default_factory=list)
    ontology_status: str = "approved"
    ontology_revision: int = 0
    ontology_changes: list[Any] = Field(default_factory=list)
    ontology_recommendations: list[Any] = Field(default_factory=list)
    label_strategy: str
    expected_output_format: str | None = None
    quality_policy: dict[str, Any]
    status: str
    state_label: str = ""
    next_action: str = ""
    modality: str = "image"
    video_config: dict[str, Any] | None = None
    confidence_threshold: float = 0.95
    high_confidence_qc_sample_rate: float = 0.02
    sentiment_analysis_level: Literal["document", "page", "paragraph", "sentence"] = "document"
    classification_analysis_level: Literal["document", "page", "paragraph", "sentence"] = "document"
    annotation_guidelines: str = ""
    asset_count: int = 0
    annotated_count: int = 0
    approved_count: int = 0
    reviewed_count: int = 0
    pending_review_count: int = 0
    auto_approved_count: int = 0
    human_approved_count: int = 0
    rejected_count: int = 0
    rework_count: int = 0
    mean_confidence: float | None = None
    label_usage: dict[str, int] = Field(default_factory=dict)
    color_map: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def ensure_valid_datetime(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=UTC)
        if isinstance(v, str) and v.strip():
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.now(UTC)

    @field_serializer("created_at", "updated_at")
    def serialize_utc_timestamp(self, value: datetime | None) -> str | None:
        """Always emit an explicit UTC ISO 8601 string ending in 'Z'.

        This guarantees the browser can parse the timestamp as a UTC instant
        and display it in the user's local timezone via Intl.DateTimeFormat.

        A naive datetime is assumed to already be UTC (all backend datetimes
        are produced by ``_utcnow()`` which uses ``datetime.now(UTC)``).
        """
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class QcDecisionRequest(BaseModel):
    decision: Literal["PASS", "FAIL"]
    checklist: dict[str, bool] = Field(default_factory=dict)
    comments: str = ""
    required_correction: str = ""


class QcSubmitRequest(BaseModel):
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    change_reason: str = "Human annotation completed"


class ColorMapEntry(BaseModel):
    color: str
    manual: bool = False


class ColorMapOut(BaseModel):
    project_id: str
    color_map: dict[str, ColorMapEntry] = Field(default_factory=dict)


class ColorMapUpdate(BaseModel):
    """Maps class name -> new color; null clears the override (reverts to auto)."""

    overrides: dict[str, str | None] = Field(default_factory=dict)


class ClassifyRegionIn(BaseModel):
    """One region to classify: either an existing annotation_id or a raw bbox."""

    annotation_id: str | None = None
    bbox: BoundingBoxSchema | None = None
    text_labels: list[str] = Field(default_factory=list)


class ClassifyRequest(BaseModel):
    asset_id: str
    regions: list[ClassifyRegionIn] = Field(min_length=1)
    model: str = "clip"
    # Candidates at/above this score are all persisted (multi-label); the
    # single best-scoring candidate is always kept even if none clear it.
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class PromptDetectionRequest(BaseModel):
    prompt: str | None = Field(default=None, max_length=2000)
    prompts: list[str] = Field(default_factory=list, max_length=32)
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    def normalized_prompts(self) -> list[str]:
        values = list(self.prompts)
        if self.prompt:
            values.insert(0, self.prompt)
        result: list[str] = []
        for value in values:
            for part in re.split(r"[\r\n,]+", value):
                cleaned = part.strip()
                if cleaned and cleaned.casefold() not in {p.casefold() for p in result}:
                    result.append(cleaned)
        return result


class ClassificationAttributesOut(BaseModel):
    id: str | None = None
    annotation_id: str | None = None
    label: str
    taxonomy_path: str | None = None
    taxonomy_hierarchy: list[str] = Field(default_factory=list)
    confidence: float
    attributes: dict[str, Any] = Field(default_factory=dict)
    model_id: str | None = None
    model_key: str | None = None
    source: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AnnotationAttributesUpdate(BaseModel):
    label: str
    confidence: float = 1.0
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: str = "human"


class LabelEntry(BaseModel):
    """One granular classification label for an annotation.

    ``review_status`` is encoded inside the persisted attributes JSON
    as ``attributes["review_status"]`` to avoid a schema migration.
    """

    label: str = Field(min_length=1, max_length=512)
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: Literal["human", "model"] = "human"
    review_status: Literal[
        "ai_proposed", "human_verified", "rejected", "needs_rework", "flagged"
    ] | None = None


class AnnotationClassificationUpdate(BaseModel):
    """Batch upsert of granular classification labels for one annotation."""

    labels: list[LabelEntry] = Field(min_length=1)


class ClassifyRegionRequest(BaseModel):
    """Request a classifier to classify an existing or newly drawn region."""

    annotation_id: str | None = None
    asset_id: str | None = None
    bbox: BoundingBoxSchema | None = None
    text_labels: list[str] = Field(min_length=1, max_length=64)
    model: str = "clip"
    threshold: float = Field(default=0.0, ge=0.0, le=1.0)


class GranularAnnotationOut(BaseModel):
    annotation_id: str
    label: str
    attributes: list[ClassificationAttributesOut] = Field(default_factory=list)



class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str = ""
    filename: str = ""
    content_type: str = "image/jpeg"
    width: int = 0
    height: int = 0
    status: str = "uploaded"
    review_status: str = "pending"
    review_reason: str = ""
    workflow_status: str | None = None
    current_real_status: str | None = None
    qc_status: str | None = None
    is_locked: bool = False
    qc_auditor_feedback: str | None = None
    qc_rework_instruction: str | None = None
    auditor_comments: str | None = None
    required_correction: str | None = None
    mean_confidence: float | None = None
    review_priority: float = 0.0
    cluster_id: int | None = None
    is_outlier: bool = False
    is_duplicate: bool = False
    duplicate_of_asset_id: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    fps: float | None = None
    duration: float | None = None
    frame_count: int | None = None
    byte_size: int | None = None
    annotation_count: int = 0
    image_url: str = ""
    preview_url: str | None = None
    source_provider: str | None = None
    source_connection_id: str | None = None
    source_bucket: str | None = None
    source_object: str | None = None
    source_generation: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    caption: str | None = None
    inference_error: str | None = None
    ai_completed_at: datetime | None = None
    decode_error: str | None = None
    relevance_status: str = "pending"
    relevance_reason: str = ""
    relevance_confidence: float | None = None
    matched_categories: list[str] = Field(default_factory=list)


class AnnotationOut(BaseModel):
    # Segment updates return a refreshed MongoDB MongoDoc. Enable
    # Pydantic's attribute adapter for that response boundary.
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_id: str
    label: str
    canonical_label: str | None = None
    display_label: str | None = None
    class_id: int | None = None
    geometry_type: str = "box"
    geometry: dict[str, Any] | None = None
    x: float
    y: float
    w: float
    h: float
    confidence: float | None
    evidence_confidence: float | None = None
    original_ai_confidence: float | None = None
    source: str
    model_id: str | None = None
    inferred_at: datetime | None = None
    provenance: dict[str, Any]
    polygon: list[list[float]] | None = None
    mask_id: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
    review_status: str | None = None

    @field_validator("polygon", mode="before")
    @classmethod
    def normalize_polygon(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, list):
            normalized: list[list[float]] = []
            for pt in v:
                if isinstance(pt, dict) and "x" in pt and "y" in pt:
                    try:
                        normalized.append([float(pt["x"]), float(pt["y"])])
                    except (ValueError, TypeError):
                        continue
                elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        normalized.append([float(pt[0]), float(pt[1])])
                    except (ValueError, TypeError):
                        continue
                else:
                    normalized.append(pt)
            return normalized
        return v

    @field_validator("geometry", mode="before")
    @classmethod
    def normalize_geometry(cls, v: Any) -> Any:
        if isinstance(v, dict) and "points" in v and isinstance(v["points"], list):
            new_geom = dict(v)
            pts: list[Any] = []
            for pt in v["points"]:
                if isinstance(pt, dict) and "x" in pt and "y" in pt:
                    try:
                        pts.append([float(pt["x"]), float(pt["y"])])
                    except (ValueError, TypeError):
                        continue
                elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        pts.append([float(pt[0]), float(pt[1])])
                    except (ValueError, TypeError):
                        continue
                else:
                    pts.append(pt)
            new_geom["points"] = pts
            return new_geom
        return v


class AnnotationCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    geometry_type: Literal["box", "polygon", "polyline", "point", "classification", "text_span"] = "box"
    geometry: dict[str, Any] | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: Literal["ai", "human"] = "human"
    class_id: int | None = None
    model_id: str | None = None
    inferred_at: datetime | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class AnnotationUpdate(BaseModel):
    label: str | None = None
    class_id: str | None = None
    geometry_type: Literal["box", "polygon", "polyline", "point", "classification", "text_span"] | None = None
    geometry: dict[str, Any] | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None
    provenance: dict[str, Any] | None = None
    version: int | None = Field(default=None, ge=1)


class ReviewRequest(BaseModel):
    status: Literal["approved", "flagged", "review"]
    reason: str = ""


class ReviewNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    kind: Literal["note", "issue"] = "note"
    annotation_id: str | None = None
    author: str = Field(default="local", max_length=128)


class ReviewNoteUpdate(BaseModel):
    body: str | None = Field(default=None, max_length=4000)
    status: Literal["open", "resolved"] | None = None


class ReviewNoteOut(BaseModel):
    id: str
    asset_id: str
    annotation_id: str | None
    kind: str
    status: str
    body: str
    author: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class BatchCreate(BaseModel):
    asset_ids: list[str] | None = None  # default: all project assets not yet processed
    idempotency_key: str | None = Field(default=None, max_length=128)


class JobItemOut(BaseModel):
    id: str
    batch_id: str
    asset_id: str
    status: str
    attempt: int
    error_message: str
    detection_count: int
    duration_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None
    model_runs: list[dict[str, Any]] = Field(default_factory=list)


class BatchOut(BaseModel):
    id: str
    project_id: str
    status: str
    idempotency_key: str | None
    total: int
    completed: int
    failed: int
    running: int
    model_id: str
    workflow: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error_summary: str
    items: list[JobItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None = None
class MaskOut(BaseModel):
    id: str
    project_id: str | None = None
    asset_id: str
    annotation_id: str | None
    label: str
    confidence: float | None
    width: int
    height: int
    storage_path: str | None = None
    image_url: str
    mask_rle: dict[str, Any] | None
    model_id: str | None
    model_key: str | None
    provenance: dict[str, Any]
    created_at: datetime


class ModelStatusOut(BaseModel):
    key: str
    model_id: str
    capabilities: list[str]
    availability: str
    device: str
    loaded: bool
    load_duration_ms: int | None = None
    error: str | None = None
    purpose: str = ""


class HealthOut(BaseModel):
    status: str
    model_id: str
    model_loaded: bool
    device: str
    database: str
    database_provider: str = "firebase"
    database_project: str = ""
    database_database_name: str = "engenii-annotate-native"
    database_connection_status: str = "healthy"
    database_persistence_mode: str = "durable"
    models: list[ModelStatusOut] = Field(default_factory=list)
    version: str = "0.2.0"


class ErrorOut(BaseModel):
    error: str
    code: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ClarificationAnswer(BaseModel):
    answers: dict[str, str]


class ProposedLabelIn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    definition: str = ""
    includes: str = ""
    excludes: str = ""
    aliases: list[str] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_asset_ids: list[str] = Field(default_factory=list)
    hard_negative_asset_ids: list[str] = Field(default_factory=list)
    evidence_state: str | None = None
    prevalence_estimate: float | None = None
    validation: dict[str, Any] = Field(default_factory=dict)
    kind: str = "object"


class LabelsUpdate(BaseModel):
    labels: list[ProposedLabelIn | str]


class OntologyRecommendationDecision(BaseModel):
    """Empty body; decision is encoded in the path (accept|reject)."""

    note: str = ""


class DecisionResolve(BaseModel):
    resolution: str | None = None
    answer: str | None = None
    defect_category: str | None = None
    feedback: str | None = None
    auditor_id: str | None = "QUALITY_AUDITOR"
    timestamp: str | None = None
    annotations: list[Any] | None = None


class DecisionOut(BaseModel):
    id: str
    project_id: str
    status: str
    decision_type: str
    question: str
    options: list[Any] = Field(default_factory=list)
    proposed_default: str = ""
    rationale: str = ""
    affects_count: int | None = 0
    example_asset_ids: list[Any] = Field(default_factory=list)
    affected_asset_ids: list[Any] = Field(default_factory=list)
    answer: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class ReconOut(BaseModel):
    id: str | None = None
    project_id: str
    status: str
    phase: str
    error_message: str = ""
    stats: dict[str, Any] = Field(default_factory=dict)
    clusters: list[Any] = Field(default_factory=list)
    sample_asset_ids: list[Any] = Field(default_factory=list)
    proposed_labels: list[Any] = Field(default_factory=list)
    clarifying_questions: list[Any] = Field(default_factory=list)
    decisions: dict[str, Any] = Field(default_factory=dict)
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    limit: int = Field(default=24, ge=1, le=100)
    neighbor_count: int = Field(default=5, ge=0, le=12)


class DatasetMapPointOut(BaseModel):
    asset_id: str
    filename: str
    x: float
    y: float
    cluster_id: int | None = None
    review_status: str
    is_outlier: bool = False
    is_duplicate: bool = False
    duplicate_of_asset_id: str | None = None
    mean_confidence: float | None = None
    preview_url: str


class DatasetMapOut(BaseModel):
    project_id: str
    points: list[DatasetMapPointOut] = Field(default_factory=list)
    point_count: int = 0
    assets_without_coords: int = 0
    clusters: list[Any] = Field(default_factory=list)
    projection: dict[str, Any] | None = None


class DatasetSearchNeighborOut(BaseModel):
    asset_id: str
    score: float
    filename: str


class DatasetSearchHitOut(BaseModel):
    asset_id: str
    filename: str
    score: float
    cluster_id: int | None = None
    review_status: str
    preview_url: str
    neighbors: list[DatasetSearchNeighborOut] = Field(default_factory=list)


class DatasetSearchOut(BaseModel):
    project_id: str
    query: str
    results: list[DatasetSearchHitOut] = Field(default_factory=list)
    result_count: int = 0
    note: str = ""


class DatasetHealthSignalOut(BaseModel):
    key: str
    title: str
    count: int
    asset_ids: list[str] = Field(default_factory=list)
    action_label: str = "Review images"


class DatasetHealthOut(BaseModel):
    project_id: str
    signals: list[DatasetHealthSignalOut] = Field(default_factory=list)
    signal_count: int = 0
    recon_status: str = "absent"


class DatasetCoverageClusterOut(BaseModel):
    cluster_id: int | None = None
    size: int = 0
    dataset_share: float = 0.0
    reviewed_count: int = 0
    reviewed_proportion: float = 0.0
    pending_count: int = 0
    flagged_count: int = 0
    flagged_rate: float = 0.0
    avg_detector_confidence: float | None = None
    label_distribution: dict[str, int] = Field(default_factory=dict)
    is_rare: bool = False
    medoid_asset_id: str | None = None
    member_asset_ids: list[str] = Field(default_factory=list)


class DatasetCoverageOut(BaseModel):
    project_id: str
    asset_count: int = 0
    reviewed_count: int = 0
    reviewed_proportion: float = 0.0
    clusters: list[DatasetCoverageClusterOut] = Field(default_factory=list)
    summaries: list[str] = Field(default_factory=list)


class ModelRecommendationOut(BaseModel):
    key: str
    purpose: str
    required: bool = True


class ProjectPlanOut(BaseModel):
    id: str
    project_id: str
    status: str
    summary: str
    taxonomy: list[str]
    label_strategy: str
    workflow: list[dict[str, Any]]
    ambiguities: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    review_policy: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    clarifications: dict[str, Any] = Field(default_factory=dict)
    clarifying_questions: list[Any] = Field(default_factory=list)
    agent_model_id: str = ""
    confidence: float | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    pricing_version: str = ""


class BoundingBoxSchema(BaseModel):
    x: float
    y: float
    w: float
    h: float


class SegmentRequest(BaseModel):
    box: BoundingBoxSchema | None = None
    points: list[list[float]] = Field(default_factory=list)
    point_labels: list[int] = Field(default_factory=list)
    label: str = "Good fruit"
    annotation_id: str | None = None


class ProjectTemplateOut(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    version: str
    updated: str
    labels: int
    geometry: str
    projects: int
    color: str
    initials: str
    state: str
    ontology: str
    assistance: str
    qa: str
    export: str
    versions: list[dict[str, Any]] = Field(default_factory=list)


class ExportRequest(BaseModel):
    format: str | None = Field(default=None, description="Export format: yolo, yolo_seg, coco, coco_seg, pascal_voc, labelme, createml, json, csv")
    annotation_source: str = Field(default="approved", description="Source filter: all, ai, human, approved")
    include_images: bool = Field(default=True, description="Whether to bundle image files into zip")


class HumanFeedbackPayload(BaseModel):
    action: str = Field(default="reprocess", description="Action name: reprocess, reject, modify")
    reason: str = Field(default="", description="Structured reason code: wrong_label, wrong_geometry, missing_object, false_positive, duplicate_object, poor_segmentation, insufficient_detection, low_quality, other")
    annotation_id: str | None = None
    human_label: str | None = None
    geometry: dict[str, Any] | None = None
    details: str | None = None


class AssetReviewRequest(BaseModel):
    action: str = Field(default="approve", description="Action: approve, reject, modify, add_missing, delete_wrong, reprocess, escalate")
    status: str | None = Field(default=None, description="Optional status override")
    reason: str = ""
    notes: str = ""
    reviewer_id: str | None = None
    reviewer_tier: str = Field(default="reviewer_1", description="Reviewer tier: reviewer_1, reviewer_2")
    feedback: HumanFeedbackPayload | dict[str, Any] | None = None
    annotation_id: str | None = None
    human_label: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None


class AnnotationReviewRequest(BaseModel):
    action: str = Field(default="approve", description="Action: approve, reject, modify, delete_wrong")
    reason: str = ""
    reviewer_id: str | None = None
    human_label: str | None = None
    geometry: dict[str, Any] | None = None


class CloudStorageConfigOut(BaseModel):
    configured_provider: str
    available_providers: list[str] = Field(default_factory=list)
    default_gcs_bucket: str = ""
    default_s3_bucket: str = ""
    aws_region: str = "us-east-1"
    gcs_prefix: str = ""
    cloud_storage_status: str = "not_configured"
    cloud_storage_message: str = ""


class CloudObjectItem(BaseModel):
    name: str
    size: int = 0
    content_type: str = "image/jpeg"
    updated_at: str | None = None
    uri: str = ""


class CloudListObjectsOut(BaseModel):
    provider: str
    bucket: str
    prefix: str = ""
    objects: list[CloudObjectItem] = Field(default_factory=list)
    next_token: str | None = None
    count: int = 0


class CloudImportItem(BaseModel):
    name: str
    size: int = 0
    content_type: str = "image/jpeg"
    uri: str | None = None


class CloudImportRequest(BaseModel):
    provider: str = "gcs"
    bucket: str
    objects: list[CloudImportItem] = Field(default_factory=list)
    # Asset import is asset registration only unless inference is explicitly requested.
    run_inference: bool = False


class CloudImportOut(BaseModel):
    job_id: str | None = None
    batch_id: str | None = None
    imported_count: int = 0
    duplicate_count: int = 0
    failed_count: int = 0
    total_selected: int = 0
    assets: list[AssetOut] = Field(default_factory=list)
    message: str = ""


class CloudValidateRequest(BaseModel):
    provider: str = "gcs"
    bucket: str


class CloudValidateOut(BaseModel):
    valid: bool = True
    provider: str
    bucket: str
    location: str | None = None
    region: str | None = None
    message: str = ""


class CloudConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = "google_cloud_storage"
    scope: str = Field(min_length=1, max_length=1100)


class CloudAuthorizationOut(BaseModel):
    provider: str
    status: str
    message: str


class CloudConnectionOut(BaseModel):
    id: str
    name: str
    provider: str
    scope: str
    bucket: str
    prefix: str
    auth_status: str
    validation_status: str
    last_error: str = ""
    created_at: datetime
    updated_at: datetime


AssetOut.model_rebuild()
ExportRequest.model_rebuild()
AssetReviewRequest.model_rebuild()
