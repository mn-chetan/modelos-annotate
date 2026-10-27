"""Audit Logger for Agentic Execution Trajectory and Governance."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
import json
import uuid
from typing import Any
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AgentAuditRecord:
    agent_run_id: str
    project_id: str
    asset_id: str
    user_request: str
    ontology_snapshot: list[str]
    available_models: dict[str, bool]
    selected_models: list[str]
    selected_tools: list[str]
    execution_plan: dict[str, Any]
    planner_source: str  # "agent" | "technical_validator"
    structured_intent: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    model_results: dict[str, Any] = field(default_factory=dict)
    tool_outputs: dict[str, Any] = field(default_factory=dict)
    fusion_metrics: dict[str, Any] = field(default_factory=dict)
    quality_results: dict[str, Any] = field(default_factory=dict)
    capability_gaps: list[dict[str, Any]] = field(default_factory=list)
    replan_count: int = 0
    final_decision: str = "AUTO_APPROVE"
    review_reason: str = ""
    persisted_annotation_count: int = 0
    timings: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def log_event(self, event_type: str, details: dict[str, Any] | None = None) -> None:
        action_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "details": details or {},
        }
        self.actions.append(action_entry)
        event_fields = {
            "agent_run_id": self.agent_run_id,
            "project_id": self.project_id,
            "asset_id": self.asset_id,
        }
        # Merge overlapping context fields before calling structlog so each
        # keyword is emitted at most once while preserving payload values.
        event_fields.update(dict(details or {}))
        logger.info(
            f"agent_audit_{event_type}",
            **event_fields,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_audit_record(
    project_id: str,
    asset_id: str,
    user_request: str,
    ontology_snapshot: list[str],
    available_models: dict[str, bool],
) -> AgentAuditRecord:
    return AgentAuditRecord(
        agent_run_id=str(uuid.uuid4()),
        project_id=project_id,
        asset_id=asset_id,
        user_request=user_request,
        ontology_snapshot=ontology_snapshot,
        available_models=available_models,
        selected_models=[],
        selected_tools=[],
        execution_plan={},
        planner_source="agentic",
    )
