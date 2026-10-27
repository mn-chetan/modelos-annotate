"""ExecutionObservation -- structured inference result fed to the quality/verification agent.

Every inference execution produces one observation.
The observation is the ONLY input to the quality agent's decision.
The quality agent decides: APPROVE | RETRY | ALTERNATE_MODEL | DIFFERENT_STRATEGY |
                           VERIFY | SEGMENT | HUMAN_REVIEW | FAIL

This module does NOT contain routing logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ConfidenceStats:
    """Genuine confidence statistics from model inference. Never fabricated."""

    count: int = 0
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    p50: float | None = None  # Median

    @classmethod
    def from_detections(cls, detections: list[Any]) -> "ConfidenceStats":
        """Compute honest confidence statistics from raw model outputs."""
        confidences = sorted(
            float(getattr(d, "confidence", 0.0) or 0.0)
            for d in detections
            if getattr(d, "confidence", None) is not None
        )
        if not confidences:
            return cls(count=0)
        n = len(confidences)
        return cls(
            count=n,
            minimum=confidences[0],
            maximum=confidences[-1],
            mean=sum(confidences) / n,
            p50=confidences[n // 2],
        )


@dataclass
class ExecutionObservation:
    """Structured observation of a single model inference execution.

    This is the evidence the quality agent uses to make its decision.
    It contains only factual measurements -- no routing recommendations.
    """

    execution_id: str
    agent_run_id: str
    project_id: str
    asset_id: str

    model_key: str
    strategy: str

    duration_ms: float = 0.0

    input_width: int | None = None
    input_height: int | None = None

    output_count: int = 0
    per_label_counts: dict[str, int] = field(default_factory=dict)

    confidence_stats: ConfidenceStats = field(default_factory=ConfidenceStats)

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    provenance: dict[str, Any] = field(default_factory=dict)

    job_id: str | None = None
    job_item_id: str | None = None

    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize for agent payload."""
        return {
            "execution_id": self.execution_id,
            "agent_run_id": self.agent_run_id,
            "project_id": self.project_id,
            "asset_id": self.asset_id,
            "model_key": self.model_key,
            "strategy": self.strategy,
            "duration_ms": self.duration_ms,
            "input_dimensions": {
                "width": self.input_width,
                "height": self.input_height,
            },
            "output_count": self.output_count,
            "per_label_counts": self.per_label_counts,
            "confidence_stats": {
                "count": self.confidence_stats.count,
                "min": self.confidence_stats.minimum,
                "mean": self.confidence_stats.mean,
                "max": self.confidence_stats.maximum,
                "p50": self.confidence_stats.p50,
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "provenance": self.provenance,
            "job_id": self.job_id,
            "job_item_id": self.job_item_id,
            "observed_at": self.observed_at.isoformat(),
        }

    @classmethod
    def from_detections(
        cls,
        *,
        execution_id: str,
        agent_run_id: str,
        project_id: str,
        asset_id: str,
        model_key: str,
        strategy: str,
        detections: list[Any],
        duration_ms: float = 0.0,
        input_width: int | None = None,
        input_height: int | None = None,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
        job_id: str | None = None,
        job_item_id: str | None = None,
    ) -> "ExecutionObservation":
        """Build an observation from raw detections."""
        per_label: dict[str, int] = {}
        for det in detections:
            lbl = str(getattr(det, "label", "unknown"))
            per_label[lbl] = per_label.get(lbl, 0) + 1

        return cls(
            execution_id=execution_id,
            agent_run_id=agent_run_id,
            project_id=project_id,
            asset_id=asset_id,
            model_key=model_key,
            strategy=strategy,
            duration_ms=duration_ms,
            input_width=input_width,
            input_height=input_height,
            output_count=len(detections),
            per_label_counts=per_label,
            confidence_stats=ConfidenceStats.from_detections(detections),
            errors=errors or [],
            warnings=warnings or [],
            provenance=provenance or {},
            job_id=job_id,
            job_item_id=job_item_id,
        )
