"""SAM2 segmentation adapter via Ultralytics."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from PIL import Image

from app.errors import ModelUnavailableError
from app.inference.contracts import BoundingBoxPercent, ModelCapability, ModelKey, NormalizedMask
from app.inference.device import resolve_device
from app.logging import get_logger

logger = get_logger(__name__)


class Sam2Adapter:
    key = ModelKey.SAM2.value
    capabilities = [ModelCapability.SEGMENTATION]

    def __init__(
        self,
        *,
        model_id: str = "sam2.1_t.pt",
        weights_path: Path,
        device_preference: str = "auto",
    ) -> None:
        if not (model_id.startswith("sam2") and model_id.endswith(".pt")):
            raise ModelUnavailableError(
                f"Only SAM2 weights (sam2*.pt) are supported; refused {model_id!r}",
                details={"model_id": model_id},
            )
        self.model_id = model_id
        self.weights_path = weights_path
        self.device_preference = device_preference
        self.device = resolve_device(device_preference)
        self._model: Any | None = None
        self.load_duration_ms: int | None = None
        self._loaded: bool = False

    def _get_model_device(self) -> str:
        if self._model is not None:
            model_obj = getattr(self._model, "model", None)
            if model_obj is not None and hasattr(model_obj, "parameters"):
                try:
                    first_param = next(model_obj.parameters(), None)
                    if first_param is not None:
                        return str(first_param.device)
                except Exception:
                    pass
        return self.device

    def _ensure_device_consistency(self) -> None:
        target_device = resolve_device(getattr(self, "device_preference", "auto"))
        actual_device = self._get_model_device()
        if self._model is not None and target_device != self.device:
            logger.info(
                "sam2_device_mismatch_reloading",
                model_id=self.model_id,
                current_device=self.device,
                target_device=target_device,
                actual_model_device=actual_device,
            )
            try:
                if hasattr(self._model, "to"):
                    self._model.to(target_device)
                elif hasattr(self._model, "model") and hasattr(self._model.model, "to"):
                    self._model.model.to(target_device)
                self.device = target_device
            except Exception as exc:
                logger.warning(
                    "sam2_device_move_failed_reloading",
                    error=str(exc),
                    model_id=self.model_id,
                )
                self._model = None
                self._loaded = False
                self.load()

    def load(self) -> None:
        if getattr(self, "_loaded", False) and self._model is not None:
            self._ensure_device_consistency()
            return

        import torch

        start = time.perf_counter()
        self.device = resolve_device(getattr(self, "device_preference", "auto"))
        load_target = self.weights_path if self.weights_path.exists() else self.model_id

        logger.info(
            "model_load_start",
            model_key=self.key,
            model_id=self.model_id,
            weights=str(load_target),
            cache_path=str(self.weights_path),
            requested_device=self.device,
            cuda_available=torch.cuda.is_available(),
        )
        try:
            from ultralytics import SAM
        except ImportError as exc:
            raise ModelUnavailableError(
                "ultralytics is required for SAM2",
                details={"hint": "pip install ultralytics"},
            ) from exc

        try:
            self.weights_path.parent.mkdir(parents=True, exist_ok=True)
            self._model = SAM(str(load_target))
            if hasattr(self._model, "to"):
                self._model.to(self.device)
            elif hasattr(self._model, "model") and hasattr(self._model.model, "to"):
                self._model.model.to(self.device)
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(
                f"Failed to load SAM2 {self.model_id}: {exc}",
                details={
                    "model_id": self.model_id,
                    "weights": str(self.weights_path),
                    "device": self.device,
                    "next_step": f"Place {self.model_id} in MODEL_CACHE_DIR or set SAM2_WEIGHTS_PATH",
                },
            ) from exc

        self.load_duration_ms = int((time.perf_counter() - start) * 1000)
        self._loaded = True
        actual_device = self._get_model_device()

        logger.info(
            "sam2_runtime_diagnostics",
            model_id=self.model_id,
            checkpoint=str(load_target),
            cache=str(self.weights_path),
            configured_device=getattr(self, "device_preference", "auto"),
            requested_device=self.device,
            actual_model_device=actual_device,
            input_device=self.device,
            cuda_available=torch.cuda.is_available(),
            cache_device=actual_device,
            loaded_from_cache=self.weights_path.exists(),
        )

        logger.info(
            "model_load_complete",
            model_key=self.key,
            model_id=self.model_id,
            device=self.device,
            duration_ms=self.load_duration_ms,
        )

    def segment_boxes(
        self,
        image_path: Path,
        *,
        asset_id: str,
        boxes: list[BoundingBoxPercent],
        labels: list[str] | None = None,
        annotation_ids: list[str | None] | None = None,
        storage_dir: Path | None = None,
    ) -> list[NormalizedMask]:
        import torch

        if not getattr(self, "_loaded", False) or self._model is None:
            self.load()
        else:
            self._ensure_device_consistency()

        if self._model is None:
            raise ModelUnavailableError(
                f"SAM2 model {self.model_id} is not loaded or is unavailable.",
                details={
                    "model_id": self.model_id,
                    "weights": str(self.weights_path),
                    "device": self.device,
                },
            )

        with Image.open(image_path) as img:
            width, height = img.size

        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid image dimensions ({width}x{height}) for asset {asset_id}")

        if not boxes:
            return []

        # Validate box formats and convert percent boxes to xyxy pixels for SAM
        bboxes = []
        for box in boxes:
            bx = float(getattr(box, "x", 0.0))
            by = float(getattr(box, "y", 0.0))
            bw = float(getattr(box, "w", 0.0))
            bh = float(getattr(box, "h", 0.0))

            x1 = max(0.0, min(float(width), (bx / 100.0) * width))
            y1 = max(0.0, min(float(height), (by / 100.0) * height))
            x2 = max(x1 + 0.1, min(float(width), ((bx + bw) / 100.0) * width))
            y2 = max(y1 + 0.1, min(float(height), ((by + bh) / 100.0) * height))
            bboxes.append([x1, y1, x2, y2])

        actual_model_dev = self._get_model_device()
        logger.info(
            "sam2_inference_diagnostics",
            model_id=self.model_id,
            checkpoint=str(self.weights_path),
            cache=str(self.weights_path.parent),
            configured_device=getattr(self, "device_preference", "auto"),
            actual_model_device=actual_model_dev,
            input_device=self.device,
            cuda_available=torch.cuda.is_available(),
            cache_device=actual_model_dev,
            loaded_from_cache=getattr(self, "_loaded", False),
            box_count=len(bboxes),
            image_width=width,
            image_height=height,
        )

        try:
            results = self._model.predict(
                source=str(image_path),
                bboxes=bboxes,
                device=self.device,
                verbose=False,
            )
        except Exception as exc:
            logger.error(
                "sam2_segmentation_failed_exception",
                model_id=self.model_id,
                device=self.device,
                actual_model_device=actual_model_dev,
                error=str(exc),
                exc_info=True,
            )
            raise ModelUnavailableError(
                f"SAM2 segmentation failed on device {self.device}: {exc}",
                details={
                    "model_id": self.model_id,
                    "device": self.device,
                    "actual_model_device": actual_model_dev,
                    "error": str(exc),
                },
            ) from exc

        now = datetime.now(UTC)
        masks_out: list[NormalizedMask] = []
        if not results:
            return masks_out

        result = results[0]
        masks = getattr(result, "masks", None)
        if masks is None or masks.data is None:
            return masks_out

        data = masks.data.cpu().numpy()
        for i in range(min(len(data), len(boxes))):
            label = labels[i] if labels and i < len(labels) else "object"
            ann_id = annotation_ids[i] if annotation_ids and i < len(annotation_ids) else None
            mask_arr = (data[i] > 0.5).astype(np.uint8) * 255
            mask_path: str | None = None
            mask_id = str(uuid4())
            if storage_dir is not None:
                storage_dir.mkdir(parents=True, exist_ok=True)
                file_path = storage_dir / f"{mask_id}.png"
                Image.fromarray(mask_arr).save(file_path)
                mask_path = str(file_path)

            # Compact RLE-ish summary (counts of runs) for API without huge payloads
            flat = mask_arr.flatten()
            rle_counts: list[int] = []
            if flat.size:
                prev = int(flat[0] > 0)
                run = 1
                for v in flat[1:]:
                    cur = int(v > 0)
                    if cur == prev:
                        run += 1
                    else:
                        rle_counts.append(run)
                        prev = cur
                        run = 1
                rle_counts.append(run)

            from app.services.segmentation_quality import evaluate_segmentation_quality_score, validate_mask_and_calculate_metrics

            box = boxes[i]
            metrics = validate_mask_and_calculate_metrics(mask_arr, width, height, box)
            seg_quality = evaluate_segmentation_quality_score(0.90, metrics["mask_area"], metrics["bbox_area"])

            logger.info(
                "sam2_transformation_logging",
                source_width=width,
                source_height=height,
                model_input_width=data[i].shape[1] if len(data[i].shape) > 1 else width,
                model_input_height=data[i].shape[0] if len(data[i].shape) > 0 else height,
                crop_x=int((box.x / 100.0) * width),
                crop_y=int((box.y / 100.0) * height),
                scale=1.0,
                padding=0,
                mask_width=width,
                mask_height=height,
                mask_area=metrics["mask_area"],
                bbox_area=metrics["bbox_area"],
                mask_to_bbox_ratio=metrics["mask_to_bbox_ratio"],
                segmentation_quality=seg_quality,
            )

            masks_out.append(
                NormalizedMask(
                    id=mask_id,
                    asset_id=asset_id,
                    annotation_id=ann_id,
                    label=label,
                    confidence=0.9,
                    width=width,
                    height=height,
                    mask_path=mask_path,
                    mask_rle={"counts": rle_counts, "size": [height, width]},
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={
                        "engine": "ultralytics-sam2",
                        "prompt": "box",
                        "box": box.__dict__,
                        "mask_area": metrics["mask_area"],
                        "bbox_area": metrics["bbox_area"],
                        "mask_to_bbox_ratio": metrics["mask_to_bbox_ratio"],
                        "segmentation_quality": seg_quality,
                        "quality_flags": metrics["flags"],
                    },
                )
            )
        return masks_out

    def segment_interactive(
        self,
        image_path: Path,
        *,
        asset_id: str,
        boxes: list[BoundingBoxPercent] | None = None,
        points: list[list[float]] | None = None,
        point_labels: list[int] | None = None,
        label: str = "object",
        annotation_id: str | None = None,
        storage_dir: Path | None = None,
    ) -> list[NormalizedMask]:
        if not getattr(self, "_loaded", False):
            self.load()
        if self._model is None:
            raise ModelUnavailableError(
                f"SAM2 model {self.model_id} is not loaded or is unavailable.",
                details={
                    "model_id": self.model_id,
                    "weights": str(self.weights_path),
                    "device": self.device,
                },
            )

        with Image.open(image_path) as img:
            width, height = img.size

        predict_kwargs: dict[str, Any] = {
            "source": str(image_path),
            "device": self.device,
            "verbose": False,
        }

        if boxes:
            bboxes = []
            for box in boxes:
                x1 = max(0.0, min(float(width - 1), (box.x / 100.0) * width))
                y1 = max(0.0, min(float(height - 1), (box.y / 100.0) * height))
                x2 = max(x1 + 1.0, min(float(width), ((box.x + box.w) / 100.0) * width))
                y2 = max(y1 + 1.0, min(float(height), ((box.y + box.h) / 100.0) * height))
                bboxes.append([x1, y1, x2, y2])
            predict_kwargs["bboxes"] = bboxes
        elif points:
            pts = []
            for pt in points:
                px = max(0.0, min(float(width - 1), (pt[0] / 100.0) * width))
                py = max(0.0, min(float(height - 1), (pt[1] / 100.0) * height))
                pts.append([px, py])
            predict_kwargs["points"] = pts
            predict_kwargs["labels"] = point_labels or [1] * len(pts)
        else:
            return []

        results = self._model.predict(**predict_kwargs)
        now = datetime.now(UTC)
        masks_out: list[NormalizedMask] = []
        if not results:
            return masks_out

        result = results[0]
        masks = getattr(result, "masks", None)
        if masks is None or masks.data is None:
            return masks_out

        data = masks.data.cpu().numpy()
        for i in range(len(data)):
            if points and i > 0:
                break  # For point prompt, we only need the primary mask
            mask_arr = (data[i] > 0.5).astype(np.uint8) * 255
            mask_id = str(uuid4())
            mask_path = None
            if storage_dir is not None:
                storage_dir.mkdir(parents=True, exist_ok=True)
                file_path = storage_dir / f"{mask_id}.png"
                Image.fromarray(mask_arr).save(file_path)
                mask_path = str(file_path)

            flat = mask_arr.flatten()
            rle_counts: list[int] = []
            if flat.size:
                prev = int(flat[0] > 0)
                run = 1
                for v in flat[1:]:
                    cur = int(v > 0)
                    if cur == prev:
                        run += 1
                    else:
                        rle_counts.append(run)
                        prev = cur
                        run = 1
                rle_counts.append(run)

            conf_val: float | None = None
            if getattr(result, "boxes", None) is not None and getattr(result.boxes, "conf", None) is not None:
                try:
                    conf_tensor = result.boxes.conf
                    if len(conf_tensor) > i:
                        conf_val = float(conf_tensor[i].item())
                except Exception:
                    pass

            masks_out.append(
                NormalizedMask(
                    id=mask_id,
                    asset_id=asset_id,
                    annotation_id=annotation_id,
                    label=label,
                    confidence=conf_val if conf_val is not None else 0.95,
                    width=width,
                    height=height,
                    mask_path=mask_path,
                    mask_rle={"counts": rle_counts, "size": [height, width]},
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={
                        "engine": "ultralytics-sam2",
                        "prompt": "points" if points else "box",
                    },
                )
            )
        return masks_out
