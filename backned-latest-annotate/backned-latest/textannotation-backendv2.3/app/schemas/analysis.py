from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.core.config import AnalysisType, SourceType
from app.schemas.entity import EntityAnalysisResult
from app.schemas.sentiment import SentimentAnalysisResult


WorkflowStatus = Literal[
    "HUMAN_REVIEW",
    "QC_VERIFICATION",
    "APPROVED",
    "REJECTED",
    "COMPLETED",
]


WorkflowAction = Literal[
    "ANALYSIS_CREATED",
    "ROUTED_TO_HUMAN_REVIEW",
    "HUMAN_REVIEW_SUBMITTED",
    "ROUTED_TO_QC",
    "QC_APPROVED",
    "QC_REJECTED",
]


class WorkflowAuditEvent(BaseModel):
    action: WorkflowAction
    reviewer_name: str
    reviewer_role: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status_before: WorkflowStatus | None = None
    status_after: WorkflowStatus
    updated_fields: list[str] = Field(default_factory=list)
    approval_decision: str | None = None
    rejection_reason: str | None = None
    comments: str | None = None


class WorkflowVersion(BaseModel):
    version: int
    status: WorkflowStatus
    updated_by: str
    reviewer_role: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict)
    comments: str | None = None


class WorkflowDataUpdate(BaseModel):
    result: dict[str, Any]


class HumanReviewSubmitRequest(BaseModel):
    reviewer_name: str
    reviewer_role: str = "HUMAN_REVIEWER"
    result: dict[str, Any]
    comments: str | None = None


class QCReviewSubmitRequest(BaseModel):
    reviewer_name: str
    reviewer_role: str = "QC_REVIEWER"
    approved: bool
    comments: str | None = None


class WorkflowSummary(BaseModel):
    analysis_id: UUID
    source_id: UUID
    source_ids: list[UUID] = Field(default_factory=list)
    analysis_type: AnalysisType
    assessment_name: str
    identification_name: list[str] = Field(default_factory=list)
    model_name: str | None = None
    status: WorkflowStatus
    confidence_score: float | None = None
    result: dict[str, Any]
    results: list[AnalysisResultItem] = Field(default_factory=list)
    human_review_result: dict[str, Any] | None = None
    qc_result: dict[str, Any] | None = None
    assigned_reviewer_role: str | None = None
    assigned_reviewer_name: str | None = None
    reviewer_comments: list[str] = Field(default_factory=list)
    audit_trail: list[WorkflowAuditEvent] = Field(default_factory=list)
    versions: list[WorkflowVersion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisResultItem(BaseModel):
    analysis_id: UUID
    source_id: UUID
    source_type: SourceType
    source_url: str | None = None
    file_name: str | None = None
    original_text: str | None = None
    confidence_threshold: float | None = None
    status: WorkflowStatus
    confidence_score: float | None = None
    result: dict[str, Any]
    human_review_url: str | None = None
    qc_review_url: str | None = None
    created_at: datetime


class AnalysisCreateResponse(BaseModel):
    analysis_type: AnalysisType
    assessment_name: str
    status: WorkflowStatus
    results: list[AnalysisResultItem] = Field(default_factory=list)


class AssessmentLookupItem(BaseModel):
    analysis_id: UUID
    assessment_name: str


class AnalysisRecord(BaseModel):
    analysis_id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    source_ids: list[UUID] = Field(default_factory=list)
    analysis_type: AnalysisType
    status: WorkflowStatus = "COMPLETED"
    assessment_name: str
    identification_name: list[str] = Field(default_factory=list)
    model_name: str | None = None
    confidence_score: float | None = None
    result: dict[str, Any]
    results: list[AnalysisResultItem] = Field(default_factory=list)
    human_review_result: dict[str, Any] | None = None
    qc_result: dict[str, Any] | None = None
    assigned_reviewer_role: str | None = None
    assigned_reviewer_name: str | None = None
    reviewer_comments: list[str] = Field(default_factory=list)
    audit_trail: list[WorkflowAuditEvent] = Field(default_factory=list)
    versions: list[WorkflowVersion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TextClassificationChunkResult(BaseModel):
    chunk_index: int
    chunk_text: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class TextClassificationAnalysisResult(BaseModel):
    analysis_type: Literal["TEXT_CLASSIFICATION"] = "TEXT_CLASSIFICATION"
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    chunk_results: list[TextClassificationChunkResult] = Field(default_factory=list)


class GeminiTextClassificationResponse(BaseModel):
    class ClassificationItem(BaseModel):
        text: str
        category: str
        confidence: float = Field(ge=0.0, le=1.0)
        reasoning: str

    results: list[ClassificationItem]

    @model_validator(mode="before")
    @classmethod
    def _wrap_list_response(cls, value):
        if isinstance(value, list):
            return {"results": value}
        return value


class RelationExtractionRelation(BaseModel):
    source: str
    relation: str
    target: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class RelationExtractionAnalysisResult(BaseModel):
    analysis_type: Literal["RELATION_EXTRACTION"] = "RELATION_EXTRACTION"
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    relations: list[RelationExtractionRelation] = Field(default_factory=list)


class GeminiRelationExtractionResponse(BaseModel):
    class RelationItem(BaseModel):
        source: str
        relation: str
        target: str
        confidence: float = Field(ge=0.0, le=1.0)
        reasoning: str

        @model_validator(mode="before")
        @classmethod
        def _accept_reason_alias(cls, value):
            if isinstance(value, dict) and "reasoning" not in value and "reason" in value:
                value = dict(value)
                value["reasoning"] = value["reason"]
            return value

    analysis_type: Literal["RELATION_EXTRACTION"] = "RELATION_EXTRACTION"
    relations: list[RelationItem] = Field(default_factory=list)
