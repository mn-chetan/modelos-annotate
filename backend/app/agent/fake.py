"""Fake agent client for offline, testing, or disabled agent execution."""

from __future__ import annotations

from typing import Any

from app.agent.client import AgentUsage
from app.agent.schemas import ModelRecommendation, ProjectPlanPayload
from app.recon.ontology import OntologyProposal, ProposedLabel


class FakeAgentClient:
    """Mock agent client that returns structured fallback responses without calling Vertex AI."""

    def __init__(self, model_id: str = "fake-gemini") -> None:
        self.model_id = model_id

    def propose_ontology(
        self,
        recon_context: dict[str, Any],
        images: list[Any] | None = None,
    ) -> tuple[OntologyProposal, AgentUsage]:
        project_meta = recon_context.get("project", {}) if isinstance(recon_context, dict) else {}
        labels_input = project_meta.get("labels", []) or ["object"]
        proposed_labels = [
            ProposedLabel(
                name=str(lbl),
                definition=f"Auto-generated definition for {lbl}",
                includes="",
                excludes="",
                aliases=[],
                relations=[],
                evidence_asset_ids=[],
                prevalence_estimate=0.5,
                kind="object",
            )
            for lbl in labels_input
        ]
        proposal = OntologyProposal(
            summary="Offline mock ontology proposal generated successfully.",
            proposed_labels=proposed_labels,
            needs_decision=False,
            clarifying_questions=[],
            recommended_models=[
                ModelRecommendation(key="yolo26", purpose="Primary object detection", required=True),
                ModelRecommendation(key="dino", purpose="Open-vocabulary object verification", required=False),
            ],
            risks=[],
            review_policy_notes="Mock review policy: high confidence auto-approves.",
            label_strategy="detailed",
        )
        usage = AgentUsage(
            tokens_in=100,
            tokens_out=50,
            model_id=self.model_id,
            raw={"fake": True},
            images_sent=len(images) if images else 0,
        )
        return proposal, usage

    def plan(
        self,
        *,
        name: str,
        goal: str,
        task_type: str,
        strategy: str,
        labels: list[str],
        clarifications: dict[str, str],
        intake_summary: str,
        modality: str = "image",
    ) -> tuple[ProjectPlanPayload, AgentUsage]:
        payload = ProjectPlanPayload(
            summary=f"Offline mock plan for project '{name}'.",
            taxonomy=labels or ["object"],
            label_strategy=strategy or "detailed",
            workflow=[
                ModelRecommendation(key="yolo26", purpose="Closed-vocabulary object detection", required=True),
                ModelRecommendation(key="dino", purpose="Open-vocabulary detection & verification", required=False),
            ],
            ambiguities=[],
            risks=[],
            review_policy={"auto_approve_threshold": 0.92},
            clarifications=clarifications or {},
            rationale="Offline fallback plan generated because agent client is running in mock mode.",
        )
        usage = AgentUsage(
            tokens_in=150,
            tokens_out=80,
            model_id=self.model_id,
            raw={"fake": True},
            images_sent=0,
        )
        return payload, usage
