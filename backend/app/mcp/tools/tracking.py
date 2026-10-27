"""Vision MCP tool: multi-frame object tracking (video workflows)."""

from __future__ import annotations

from typing import Any

from app.inference.adapters.multimodal_experts import TrackerAdapter
from app.mcp.instrumentation import mcp_tool


@mcp_tool("tracking")
def track_objects(
    tracker: TrackerAdapter,
    frames_detections: list[list[dict[str, Any]]],
    *,
    asset_id: str,
    iou_threshold: float = 0.3,
) -> list[list[dict[str, Any]]]:
    """Associate per-frame detections into persistent tracks.

    Reuses the existing IoU-association tracker; detection is not re-run
    per frame — this only maintains identity across already-detected boxes.
    """
    tracker.load()
    return tracker.track(frames_detections, iou_threshold=iou_threshold)
