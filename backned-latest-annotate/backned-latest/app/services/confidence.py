"""Canonical image-level confidence aggregation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


_INVALID_LIFECYCLE_STATES = {
    "rejected",
    "stale",
    "superseded",
    "deleted",
    "invalid",
}


def valid_ai_object_confidences(annotations: Iterable[Any]) -> list[float]:
    """Return genuine scores from the current AI annotation set.

    Human-created or human-modified rows are never new model evidence. Rows
    explicitly marked stale/superseded/rejected are also excluded so repeated
    executions cannot affect the image aggregate.
    """
    values: list[float] = []
    for annotation in annotations:
        if isinstance(annotation, dict):
            source = str(annotation.get("source") or "ai").lower()
            provenance = annotation.get("provenance") or {}
            value = annotation.get("confidence")
        else:
            source = str(getattr(annotation, "source", "ai") or "ai").lower()
            provenance = getattr(annotation, "provenance", None) or {}
            value = getattr(annotation, "confidence", None)

        if source in ("human", "human_created", "human_modified", "reviewer_edited"):
            continue
        lifecycle = str(
            provenance.get("lifecycle_status")
            or provenance.get("annotation_status")
            or "active"
        ).lower()
        if lifecycle in _INVALID_LIFECYCLE_STATES:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if 0.0 <= numeric <= 1.0:
            values.append(numeric)
    return values


def calculate_image_confidence(annotations: Iterable[Any]) -> float | None:
    """Calculate the arithmetic mean of valid object scores, or ``None``."""
    values = valid_ai_object_confidences(annotations)
    return sum(values) / len(values) if values else None
