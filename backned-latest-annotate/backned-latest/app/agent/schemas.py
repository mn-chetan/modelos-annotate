"""Structured agent I/O schemas validated at the backend boundary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ModelRecommendation(BaseModel):
    key: Literal["yolo26", "faster_rcnn", "florence", "dino", "sam2", "tracker", "gliner", "qwen3_embedding", "qwen3_reranker", "paddleocr"]
    purpose: str
    required: bool = True


class ClarifyingQuestion(BaseModel):
    id: str
    question: str
    options: list[str] = Field(default_factory=list)
    rationale: str = ""
    decision_type: str = "boundary"
    proposed_default: str = ""
    affects_count: int = 0
    example_asset_ids: list[str] = Field(default_factory=list)

    @field_validator("affects_count", mode="before")
    @classmethod
    def coerce_affects_count(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @field_validator("options", "example_asset_ids", mode="before")
    @classmethod
    def coerce_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v if x is not None]
        return []

    @field_validator("rationale", "decision_type", "proposed_default", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class IntakeAgentResult(BaseModel):
    summary: str
    needs_clarification: bool = False
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)
    proposed_labels: list[str] = Field(default_factory=list)
    label_strategy: Literal["generic", "detailed", "custom"] = "detailed"
    recommended_models: list[ModelRecommendation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    review_policy_notes: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ProjectPlanPayload(BaseModel):
    summary: str
    taxonomy: list[str]
    label_strategy: str
    workflow: list[ModelRecommendation]
    ambiguities: list[Any] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    review_policy: dict[str, object] = Field(default_factory=dict)
    clarifications: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class OntologyAgentLabel(BaseModel):
    name: str
    definition: str = ""
    includes: str = ""
    excludes: str = ""
    aliases: list[str] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_asset_ids: list[str] = Field(default_factory=list)
    prevalence_estimate: float | None = None
    kind: Literal["object", "image", "attribute"] = "object"


class OntologyAgentResult(BaseModel):
    summary: str
    proposed_labels: list[OntologyAgentLabel] = Field(default_factory=list)
    needs_decision: bool = False
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)
    recommended_models: list[ModelRecommendation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    review_policy_notes: str = ""
    label_strategy: Literal["generic", "detailed", "custom"] = "detailed"
