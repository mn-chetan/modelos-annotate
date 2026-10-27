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
