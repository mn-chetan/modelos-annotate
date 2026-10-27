"""Vision MCP tool: CLIP-based zero-shot region/attribute classification."""

from __future__ import annotations

from pathlib import Path

from app.inference.contracts import BoundingBoxPercent, ModelKey, NormalizedClassification
from app.inference.registry import ModelRegistry
from app.mcp.contracts import INVALID_INPUT, fail
from app.mcp.instrumentation import mcp_tool


@mcp_tool("classification")
def classify_objects(
    registry: ModelRegistry,
    image_path: Path,
    *,
    asset_id: str,
    regions: list[tuple[str | None, BoundingBoxPercent]],
    text_labels: list[str],
    model: str = ModelKey.CLIP.value,
) -> list[NormalizedClassification]:
    """Scores each (annotation_id, region) pair against `text_labels` via CLIP."""
    if not regions:
        return fail(INVALID_INPUT, "No regions to classify", details={"asset_id": asset_id})  # type: ignore[return-value]
    if not text_labels:
        return fail(INVALID_INPUT, "text_labels must not be empty", details={"asset_id": asset_id})  # type: ignore[return-value]
    return registry.classify_regions(
        model, image_path, asset_id=asset_id, regions=regions, text_labels=text_labels
    )
