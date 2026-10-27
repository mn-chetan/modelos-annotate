"""Vision MCP tool: SAM2 mask segmentation from existing detection boxes."""

from __future__ import annotations

from pathlib import Path

from app.errors import ModelUnavailableError
from app.inference.contracts import ModelKey, NormalizedDetection, NormalizedMask
from app.inference.registry import ModelRegistry
from app.mcp.contracts import INVALID_INPUT, fail
from app.mcp.instrumentation import mcp_tool


@mcp_tool("segmentation")
def segment_objects(
    registry: ModelRegistry,
    image_path: Path,
    *,
    asset_id: str,
    detections: list[NormalizedDetection],
    object_ids: list[str] | None = None,
    storage_dir: Path | None = None,
) -> list[NormalizedMask]:
    """Generate masks for the given detections (or a subset by ``object_ids``) via SAM2."""
    candidates = detections
    if object_ids:
        wanted = set(object_ids)
        candidates = [d for d in detections if d.id in wanted]
    if not candidates:
        return fail(INVALID_INPUT, "No matching detections to segment", details={"asset_id": asset_id})  # type: ignore[return-value]

    adapter = registry.get(ModelKey.SAM2.value)
    if not registry.try_load(ModelKey.SAM2.value):
        raise ModelUnavailableError(
            f"Model {ModelKey.SAM2.value} unavailable", details={"model_key": ModelKey.SAM2.value}
        )

    boxes = [d.bbox for d in candidates]
    box_labels = [d.label for d in candidates]
    annotation_ids = [d.id for d in candidates]
    return adapter.segment_boxes(  # type: ignore[no-any-return]
        image_path,
        asset_id=asset_id,
        boxes=boxes,
        labels=box_labels,
        annotation_ids=annotation_ids,
        storage_dir=storage_dir,
    )
