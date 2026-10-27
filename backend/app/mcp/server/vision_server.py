"""Vision MCP server: groups detection/segmentation/tracking capabilities.

In-process only — bound to the already-constructed
:class:`app.inference.registry.ModelRegistry` so loaded models are reused,
never re-initialized per call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.inference.contracts import ModelKey, NormalizedDetection
from app.inference.registry import ModelRegistry
from app.mcp.contracts import MCPResult
from app.mcp.tools import classification, detection, segmentation, tracking


class VisionMCPServer:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def detect_objects(
        self,
        image_path: Path,
        *,
        asset_id: str,
        model: str = ModelKey.YOLO26.value,
        labels: list[str] | None = None,
        confidence_threshold: float | None = None,
    ) -> MCPResult[list[NormalizedDetection]]:
        return detection.detect_objects(
            self.registry,
            image_path,
            asset_id=asset_id,
            model=model,
            labels=labels,
            confidence_threshold=confidence_threshold,
        )

    def detect_custom_objects(
        self, image_path: Path, *, asset_id: str, prompts: list[str]
    ) -> MCPResult[list[NormalizedDetection]]:
        return detection.detect_custom_objects(
            self.registry, image_path, asset_id=asset_id, prompts=prompts
        )

    def segment_objects(
        self,
        image_path: Path,
        *,
        asset_id: str,
        detections: list[NormalizedDetection],
        object_ids: list[str] | None = None,
        storage_dir: Path | None = None,
    ) -> MCPResult[Any]:
        return segmentation.segment_objects(
            self.registry,
            image_path,
            asset_id=asset_id,
            detections=detections,
            object_ids=object_ids,
            storage_dir=storage_dir,
        )

    def track_objects(
        self,
        frames_detections: list[list[dict[str, Any]]],
        *,
        asset_id: str,
        iou_threshold: float = 0.3,
    ) -> MCPResult[Any]:
        tracker = self.registry.get(ModelKey.TRACKER.value)
        return tracking.track_objects(
            tracker, frames_detections, asset_id=asset_id, iou_threshold=iou_threshold
        )

    def classify_objects(
        self,
        image_path: Path,
        *,
        asset_id: str,
        regions: list[tuple[str | None, Any]],
        text_labels: list[str],
        model: str = ModelKey.CLIP.value,
    ) -> MCPResult[Any]:
        return classification.classify_objects(
            self.registry,
            image_path,
            asset_id=asset_id,
            regions=regions,
            text_labels=text_labels,
            model=model,
        )
