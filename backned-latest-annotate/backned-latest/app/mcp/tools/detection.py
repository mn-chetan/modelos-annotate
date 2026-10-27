"""Vision MCP tool: closed-set and open-vocabulary object detection.

Delegates to the existing :class:`app.inference.registry.ModelRegistry`
(already-loaded adapters) — no model logic is duplicated here.
"""

from __future__ import annotations

from pathlib import Path

from app.inference.contracts import ModelKey, NormalizedDetection
from app.inference.registry import ModelRegistry
from app.mcp.contracts import INVALID_INPUT, fail
from app.mcp.instrumentation import mcp_tool

_CLOSED_SET_MODELS = {ModelKey.YOLO26.value, ModelKey.FASTER_RCNN.value}


@mcp_tool("object_detection")
def detect_objects(
    registry: ModelRegistry,
    image_path: Path,
    *,
    asset_id: str,
    model: str = ModelKey.YOLO26.value,
    labels: list[str] | None = None,
    confidence_threshold: float | None = None,
) -> list[NormalizedDetection]:
    """Run closed-set detection (YOLO26 / Faster R-CNN) via the shared registry."""
    if model not in _CLOSED_SET_MODELS:
        return fail(  # type: ignore[return-value]
            INVALID_INPUT,
            f"detect_objects does not support model {model!r}; "
            "use detect_custom_objects for open-vocabulary models",
            details={"model": model, "supported": sorted(_CLOSED_SET_MODELS)},
        )
    detections = registry.predict_detections(model, image_path, asset_id=asset_id, labels=labels)
    if confidence_threshold is not None:
        detections = [d for d in detections if d.confidence >= confidence_threshold]
    return detections


@mcp_tool("custom_detection")
def detect_custom_objects(
    registry: ModelRegistry,
    image_path: Path,
    *,
    asset_id: str,
    prompts: list[str] | None = None,
) -> list[NormalizedDetection]:
    """Run open-vocabulary detection (Grounding DINO) against free-text prompts.

    An empty/None prompt list is valid: the underlying adapter falls back to
    its own default taxonomy, matching existing direct-call behavior.
    """
    return registry.predict_detections(ModelKey.DINO.value, image_path, asset_id=asset_id, labels=prompts)
