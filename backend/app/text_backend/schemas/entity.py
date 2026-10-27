from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EntityMatch(BaseModel):
    entity_name: str
    matched_text: str | None = None
    tag: str
    found: bool = False
    confidence_score: float | None = None


class EntityAnalysisResult(BaseModel):
    entities: list[EntityMatch] = Field(default_factory=list)


class EntityValidationResponse(BaseModel):
    entities: list[EntityMatch] = Field(default_factory=list)


class SemanticVerification(BaseModel):
    annotation_id: str
    semantic_validity: bool
    ontology_validity: bool
    contextual_validity: bool
    conflict_detected: bool = False
    alternative_label: str | None = None
    reason: str = ""
    verification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    decision: Literal["VALID", "INVALID", "UNCERTAIN"]


class SemanticVerificationResponse(BaseModel):
    verifications: list[SemanticVerification] = Field(default_factory=list)

