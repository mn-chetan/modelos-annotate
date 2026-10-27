"""Ontology proposal schemas for Dataset Reconnaissance."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.schemas import ClarifyingQuestion, ModelRecommendation


class ProposedLabel(BaseModel):
    id: str | None = None
    name: str
    definition: str = ""
    includes: str = ""
    excludes: str = ""
    aliases: list[str] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_asset_ids: list[str] = Field(default_factory=list)
    hard_negative_asset_ids: list[str] = Field(default_factory=list)
    evidence_state: Literal["verified", "candidate", "unverified"] | None = None
    prevalence_estimate: float | None = Field(default=None, ge=0.0, le=1.0)
    validation: dict[str, Any] = Field(default_factory=dict)
    kind: Literal["object", "image", "attribute"] = "object"


class OntologyProposal(BaseModel):
    summary: str = ""
    proposed_labels: list[ProposedLabel] = Field(default_factory=list)
    needs_decision: bool = False
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)
    recommended_models: list[ModelRecommendation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    review_policy_notes: str = ""
    label_strategy: Literal["generic", "detailed", "custom"] = "detailed"
