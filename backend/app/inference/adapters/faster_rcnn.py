"""Faster R-CNN object detection adapter.

Responsibilities:
- Run pretrained Faster R-CNN inference.
- Preserve the detector's original confidence.
- Return normalized bounding boxes using the existing contract.
- Never modify confidence using IoU, model agreement, or review status.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

from app.errors import ModelUnavailableError
from app.inference.contracts import (
    ModelCapability,
    ModelKey,
    NormalizedDetection,
)
from app.inference.device import clamp_box, resolve_device
from app.logging import get_logger

logger = get_logger(__name__)


from app.inference.adapters.yolo26 import DEFAULT_COCO_CLASSES


class FasterRCNNAdapter:
    key = ModelKey.FASTER_RCNN.value
    capabilities = [ModelCapability.DETECTION]

    def __init__(
        self,
        *,
        model_id: str = "fasterrcnn_resnet50_fpn_v2",
        device_preference: str = "auto",
        confidence_threshold: float = 0.15,
    ) -> None:
        self.model_id = model_id
        self.device = resolve_device(device_preference)
        self.confidence_threshold = confidence_threshold

        self._model: Any | None = None
        self._weights: Any | None = None
        self._loaded = False
        self.load_duration_ms: int | None = None
        self.names: dict[int, str] = dict(DEFAULT_COCO_CLASSES)

    def load(self) -> None:
        if self._loaded:
            return

        start = time.perf_counter()

        logger.info(
            "model_load_start",
            model_key=self.key,
            model_id=self.model_id,
            device=self.device,
        )

        try:
            import torch
            from torchvision.models.detection import (
                FasterRCNN_ResNet50_FPN_V2_Weights,
                fasterrcnn_resnet50_fpn_v2,
            )
        except ImportError as exc:
            raise ModelUnavailableError(
                "torch and torchvision are required for Faster R-CNN",
                details={
                    "hint": "Install compatible torch and torchvision versions."
                },
            ) from exc

        try:
            weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
            categories = list(getattr(weights, "meta", {}).get("categories", []) or [])
            self.names = {index: str(value) for index, value in enumerate(categories)}

            model = fasterrcnn_resnet50_fpn_v2(
                weights=weights,
            )

            model.to(self.device)
            model.eval()

            self._weights = weights
            self._model = model

            # Keep torch referenced so lazy imports are explicit.
            _ = torch

        except Exception as exc:
            raise ModelUnavailableError(
                f"Failed to load Faster R-CNN {self.model_id}: {exc}",
                details={
                    "model_id": self.model_id,
                    "device": self.device,
                },
            ) from exc

        self.load_duration_ms = int(
            (time.perf_counter() - start) * 1000
        )

        self._loaded = True

        logger.info(
            "model_load_complete",
            model_key=self.key,
            model_id=self.model_id,
            device=self.device,
            duration_ms=self.load_duration_ms,
        )

    def predict(
        self,
        image_path: Path,
        *,
        asset_id: str,
        labels: list[str] | None = None,
        confidence_threshold: float | None = None,
        **kwargs: Any,
    ) -> list[NormalizedDetection]:
        if not self._loaded:
            self.load()

        if self._model is None or self._weights is None:
            raise ModelUnavailableError(
                "Faster R-CNN model is not loaded"
            )

        if not image_path.exists():
            raise ModelUnavailableError(
                f"Image not found: {image_path}"
            )

        import torch

        image = Image.open(image_path).convert("RGB")
        width, height = image.size

        if width <= 0 or height <= 0:
            return []

        threshold = (
            self.confidence_threshold
            if confidence_threshold is None
            else float(confidence_threshold)
        )

        # Bound execution threshold.
        threshold = max(0.01, min(0.95, threshold))

        import torchvision.transforms.functional as F
        tensor = F.to_tensor(image)

        inference_started = time.perf_counter()
        with torch.no_grad():
            prediction = self._model(
                [tensor.to(self.device)]
            )[0]

        categories = self._weights.meta["categories"]

        boxes = prediction.get("boxes")
        scores = prediction.get("scores")
        class_ids = prediction.get("labels")

        if boxes is None or scores is None or class_ids is None:
            return []

        allowed_labels = None

        if labels:
            allowed_labels = {
                label.strip().casefold()
                for label in labels
                if label.strip()
            }

        now = datetime.now(UTC)
        detections: list[NormalizedDetection] = []

        boxes_cpu = boxes.detach().cpu()
        scores_cpu = scores.detach().cpu()
        class_ids_cpu = class_ids.detach().cpu()
        raw_count = len(boxes_cpu)
        thresholded_count = sum(
            1 for score in scores_cpu if float(score.item()) >= threshold
        )

        for i in range(len(boxes_cpu)):
            confidence = float(scores_cpu[i].item())
            class_id = int(class_ids_cpu[i].item())

            if confidence < threshold:
                continue

            if class_id < 0 or class_id >= len(categories):
                continue

            raw_label = str(categories[class_id]).strip()

            if not raw_label:
                continue

            if allowed_labels is not None and raw_label.casefold() not in allowed_labels:
                continue

            x1, y1, x2, y2 = [
                float(value)
                for value in boxes_cpu[i].tolist()
            ]

            x1 = max(0.0, min(x1, float(width)))
            y1 = max(0.0, min(y1, float(height)))
            x2 = max(0.0, min(x2, float(width)))
            y2 = max(0.0, min(y2, float(height)))

            box_width = x2 - x1
            box_height = y2 - y1

            if box_width <= 0 or box_height <= 0:
                continue

            bbox = clamp_box(
                (x1 / width) * 100.0,
                (y1 / height) * 100.0,
                (box_width / width) * 100.0,
                (box_height / height) * 100.0,
            )

            if bbox.w <= 0 or bbox.h <= 0:
                continue

            detections.append(
                NormalizedDetection(
                    id=str(uuid4()),
                    asset_id=asset_id,
                    label=raw_label,
                    class_id=class_id,
                    bbox=bbox,

                    # IMPORTANT:
                    # This is the original Faster R-CNN score.
                    # Do not modify it.
                    confidence=confidence,

                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,

                    provenance={
                        "engine": "torchvision-faster-rcnn",
                        "raw_model_label": raw_label,
                        "raw_model_confidence": confidence,
                        "confidence_semantics": (
                            "original_model_confidence_only"
                        ),
                        "image_width": width,
                        "image_height": height,
                        "raw_xyxy": [
                            x1,
                            y1,
                            x2,
                            y2,
                        ],
                        "execution": {
                            "confidence_threshold": threshold,
                            "planner_source": "agentic_second_pass",
                        },
                    },
                )
            )

        logger.info(
            "faster_rcnn_prediction_complete",
            asset_id=asset_id,
            detections=len(detections),
            confidence_threshold=threshold,
        )
        logger.info(
            "faster_rcnn_diagnostic",
            asset_id=asset_id,
            faster_rcnn_raw_count=raw_count,
            faster_rcnn_thresholded_count=thresholded_count,
            faster_rcnn_mapped_count=len(detections),
            faster_rcnn_final_count=len(detections),
            faster_rcnn_inference_duration=int(
                (time.perf_counter() - inference_started) * 1000
            ),
        )

        return detections
