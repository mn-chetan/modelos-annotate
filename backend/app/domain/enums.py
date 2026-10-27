"""Domain enums and value objects."""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    PROCESSING = "processing"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEW = "review"
    HUMAN_REVIEW = "human_review"
    AUTO_APPROVED = "auto_approved"
    HUMAN_APPROVED = "human_approved"
    HUMAN_MODIFIED_APPROVED = "human_modified_approved"
    HUMAN_REJECTED = "human_rejected"
    REPROCESS_REQUIRED = "reprocess_required"
    ESCALATED = "escalated"
    SECOND_REVIEW = "second_review"
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"
    # Target HITL Workflow States
    AI_ANNOTATED = "ai_annotated"
    CONFIDENCE_ROUTING = "confidence_routing"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    IN_HUMAN_REVIEW = "in_human_review"
    HUMAN_REVIEW_COMPLETED = "human_review_completed"
    SUBMITTED_FOR_QC = "submitted_for_qc"
    HIGH_CONFIDENCE_AUTO_PASS = "high_confidence_auto_pass"
    HIGH_CONFIDENCE_QC_SAMPLE = "high_confidence_qc_sample"
    QUALITY_AUDIT_REQUIRED = "quality_audit_required"
    QC_PASSED = "qc_passed"
    QC_FAILED = "qc_failed"
    HUMAN_REWORK_REQUIRED = "human_rework_required"
    FINAL_APPROVED = "final_approved"
    READY_FOR_MODEL_IMPROVEMENT = "ready_for_model_improvement"


class HumanRole(StrEnum):
    PROJECT_MANAGER = "PROJECT_MANAGER"
    HUMAN_ANNOTATOR = "HUMAN_ANNOTATOR"
    QUALITY_AUDITOR = "QUALITY_AUDITOR"


class DefectCategory(StrEnum):
    WRONG_LABEL = "wrong_label"
    MISSING_ANNOTATION = "missing_annotation"
    EXTRA_ANNOTATION = "extra_annotation"
    BOUNDING_BOX_ERROR = "bounding_box_error"
    POLYGON_SEGMENTATION_ERROR = "polygon_segmentation_error"
    TEXT_SPAN_ERROR = "text_span_error"
    CLASSIFICATION_ERROR = "classification_error"
    OTHER_GUIDELINE_VIOLATION = "other_guideline_violation"


class ReviewAction(StrEnum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    ADD_MISSING = "add_missing"
    DELETE_WRONG = "delete_wrong"
    REPROCESS = "reprocess"
    ESCALATE = "escalate"
    PASS = "pass"
    FAIL = "fail"


class ReviewReason(StrEnum):
    WRONG_LABEL = "wrong_label"
    WRONG_GEOMETRY = "wrong_geometry"
    MISSING_OBJECT = "missing_object"
    FALSE_POSITIVE = "false_positive"
    DUPLICATE_OBJECT = "duplicate_object"
    POOR_SEGMENTATION = "poor_segmentation"
    INSUFFICIENT_DETECTION = "insufficient_detection"
    LOW_QUALITY = "low_quality"
    OTHER = "other"


class AnnotationSource(StrEnum):
    AI = "ai"
    HUMAN = "human"
    HUMAN_MODIFIED = "human_modified"


class GeometryType(StrEnum):
    BOX = "box"
    POLYGON = "polygon"
    POLYLINE = "polyline"
    POINT = "point"
    CLASSIFICATION = "classification"


class BatchStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class JobItemStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    HUMAN_REVIEW = "human_review"
    INTERRUPTED = "interrupted"


class TaskType(StrEnum):
    OBJECT_DETECTION = "object_detection"
    SEGMENTATION = "segmentation"
    CLASSIFICATION = "classification"


class ModelKey(StrEnum):
    YOLO26 = "yolo26"
    FASTER_RCNN = "faster_rcnn"
    FLORENCE = "florence"
    DINO = "dino"
    SAM2 = "sam2"
    TRACKER = "tracker"
    GLINER = "gliner"
    QWEN3_EMBEDDING = "qwen3_embedding"
    QWEN3_RERANKER = "qwen3_reranker"
    PADDLEOCR = "paddleocr"


class ModelRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentRequestKind(StrEnum):
    INTAKE = "intake"
    CLARIFY = "clarify"
    PLAN = "plan"
    OPERATIONAL = "operational"
    ONTOLOGY = "ontology"
    DECISION = "decision"


class ReconStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AWAITING_DECISION = "awaiting_decision"
