"""Verification MCP tool — delegates to the existing evidence-based review decision."""

from __future__ import annotations

from typing import Any

from app.mcp.instrumentation import mcp_tool
from app.services.review_decision import ReviewDecision, decide_review


@mcp_tool("verification")
def verify_result(
    *,
    asset_id: str,
    merged: list[Any],
    all_detections: list[Any],
    scene_evidence: Any | None,
    completed_models: list[str],
    required_verification: str = "standard",
    rejected_count: int = 0,
    model_availability: dict[str, bool] | None = None,
) -> ReviewDecision:
    """Run the existing conflict/agreement/geometry verification logic unchanged.

    Confidence is never used as the sole approval signal here; ``decide_review``
    also weighs cross-model conflicts, label validity, and geometry checks.
    """
    return decide_review(
        merged=merged,
        all_detections=all_detections,
        scene_evidence=scene_evidence,
        completed_models=completed_models,
        required_verification=required_verification,
        rejected_count=rejected_count,
        model_availability=model_availability,
    )
