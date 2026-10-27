"""Authoritative confidence-threshold resolution for image inference."""

from __future__ import annotations

import math
from typing import Any


# Preserve the adapter safety bounds that existed before planner thresholds
# were forwarded.  The resolver makes any clamp explicit to the caller/logs.
MODEL_MINIMUMS = {
    # Planner thresholds must not lower the production precision floor.
    # Challenging scenes can still be routed to review/retry.
    "yolo26": 0.50,
    "faster_rcnn": 0.50,
    "dino": 0.0,
}


def resolve_confidence_threshold(
    model: str,
    requested: Any,
    configured_default: float,
) -> dict[str, Any]:
    """Resolve one threshold for both diagnostics and adapter execution."""
    model_key = str(model).strip().lower()
    requested_present = requested is not None
    source = "agent_plan" if requested_present else "model_default"
    try:
        value = float(requested if requested_present else configured_default)
    except (TypeError, ValueError):
        value = float(configured_default)
        source = "model_default_invalid_plan_value"

    if not math.isfinite(value):
        value = float(configured_default)
        source = "model_default_invalid_plan_value"

    minimum = float(MODEL_MINIMUMS.get(model_key, 0.0))
    effective = max(minimum, min(0.95, value))
    clamped = effective != value
    reasons: list[str] = []
    if value < minimum:
        reasons.append(f"existing {model_key} minimum {minimum}")
    if value > 0.95:
        reasons.append("existing maximum 0.95")

    return {
        "requested_threshold": value if requested_present else None,
        "effective_threshold": effective,
        "threshold_source": source,
        "threshold_clamped": clamped,
        "clamp_reason": "; ".join(reasons) or None,
    }
