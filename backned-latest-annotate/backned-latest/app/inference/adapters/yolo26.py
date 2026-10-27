"""Ultralytics YOLOv26 dynamic detection adapter.

The adapter executes the strategy selected by the routing/planning layer.

Supported execution modes:
    - full_image
    - high_resolution
    - tiled
    - high_resolution_tiled

Important semantic rules:
    - model confidence is always the original YOLO confidence
    - confidence is never boosted after agreement/merging
    - tiled detections are converted back to original-image coordinates
    - confidence threshold is configurable per execution plan
    - the global/default threshold is preserved for backward compatibility
    - low-confidence candidates are not silently re-labelled
    - SAM2/DINO/Florence responsibilities remain outside this adapter
"""

from __future__ import annotations

import math
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

ALLOWED_MODEL_PREFIX = "yolo26"

# Improve small-object recall without lowering the configured confidence:
# use a larger inference canvas and retain enough candidates for dense scenes.
DEFAULT_INFERENCE_SIZE = 1280
NMS_IOU_THRESHOLD = 0.70
MAX_DETECTIONS = 1000

DEFAULT_COCO_CLASSES: dict[int, str] = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane", 5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench", 14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack", 25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
    30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite", 34: "baseball bat", 35: "baseball glove", 36: "skateboard", 37: "surfboard", 38: "tennis racket",
    39: "bottle", 40: "wine glass", 41: "cup", 42: "fork", 43: "knife", 44: "spoon", 45: "bowl", 46: "banana", 47: "apple", 48: "sandwich", 49: "orange",
    50: "broccoli", 51: "carrot", 52: "hot dog", 53: "pizza", 54: "donut", 55: "cake", 56: "chair", 57: "couch", 58: "potted plant", 59: "bed",
    60: "dining table", 61: "toilet", 62: "tv", 63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard", 67: "cell phone", 68: "microwave", 69: "oven",
    70: "toaster", 71: "sink", 72: "refrigerator", 73: "book", 74: "clock", 75: "vase", 76: "scissors", 77: "teddy bear", 78: "hair drier", 79: "toothbrush"
}

# YOLO is the closed-vocabulary detector.
#
# These are the project-supported object classes.
# Ontology validation still happens downstream.
YOLO_SUPPORTED_LABELS = frozenset(
    set(DEFAULT_COCO_CLASSES.values())
)


class Yolo26Adapter:
    key = ModelKey.YOLO26.value
    capabilities = [ModelCapability.DETECTION]

    def __init__(
        self,
        settings_or_model_id: Any = None,
        *,
        model_id: str | None = None,
        weights_path: Path | None = None,
        device_preference: str = "auto",
        confidence_threshold: float = 0.20,
    ) -> None:
        if settings_or_model_id is not None and not isinstance(settings_or_model_id, str):
            # Positional settings object passed
            settings = settings_or_model_id
            model_id = getattr(settings, "yolo26_model_id", "yolo26n.pt")
            weights_path = getattr(settings, "yolo26_weights_path", None) or (getattr(settings, "model_cache_dir", Path("model_cache")) / model_id)
            device_preference = getattr(settings, "device", "auto")
            confidence_threshold = getattr(settings, "yolo_confidence_threshold", 0.20)
        elif isinstance(settings_or_model_id, str):
            model_id = settings_or_model_id

        model_id = model_id or "yolo26n.pt"
        weights_path = weights_path or Path(model_id)

        if (
            not model_id.startswith(ALLOWED_MODEL_PREFIX)
            or not model_id.endswith(".pt")
        ):
            raise ModelUnavailableError(
                (
                    "Only YOLOv26 weights "
                    "(yolo26*.pt) are supported; "
                    f"refused {model_id!r}"
                ),
                details={
                    "model_id": model_id,
                },
            )

        self.model_id = model_id
        self.weights_path = Path(weights_path) if weights_path else Path(model_id)
        self.confidence_threshold = confidence_threshold
        self.device = resolve_device(device_preference)

        self._model: Any | None = None
        self.load_duration_ms: int | None = None
        self._loaded: bool = False
        self.names: dict[int, str] = dict(DEFAULT_COCO_CLASSES)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        if getattr(self, "_loaded", False):
            return

        start = time.perf_counter()

        logger.info(
            "model_load_start",
            model_key=self.key,
            model_id=self.model_id,
            weights=str(self.weights_path),
            device=self.device,
        )

        load_target: str | Path

        if not self.weights_path.is_file():
            load_target = self.model_id

            logger.warning(
                "model_weights_missing_will_download",
                path=str(self.weights_path),
                model_id=self.model_id,
            )
        else:
            load_target = self.weights_path

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ModelUnavailableError(
                (
                    "ultralytics is not installed. "
                    "Install backend dependencies to run inference."
                ),
                details={
                    "hint": "pip install -e '.[dev]'",
                },
            ) from exc

        try:
            self.weights_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            model = YOLO(
                str(load_target)
            )

            # Warm-up.
            import numpy as np

            dummy = np.zeros(
                (64, 64, 3),
                dtype=np.uint8,
            )

            model.predict(
                dummy,
                device=self.device,
                verbose=False,
            )

            self._model = model
            model_names = getattr(model, "names", {}) or {}
            if isinstance(model_names, dict):
                self.names = {int(key): str(value) for key, value in model_names.items()}
            elif isinstance(model_names, (list, tuple)):
                self.names = {index: str(value) for index, value in enumerate(model_names)}
            logger.info(
                "model_capabilities_discovered",
                model="yolo26",
                capabilities=["detection"],
                vocabulary_source="runtime_model",
                vocabulary_size=len(model_names),
                model_name=self.model_id,
            )

        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(
                (
                    f"Failed to load YOLOv26 model "
                    f"{self.model_id}: {exc}"
                ),
                details={
                    "model_id": self.model_id,
                    "weights": str(
                        self.weights_path
                    ),
                    "device": self.device,
                    "next_step": (
                        f"Place {self.model_id} in "
                        "MODEL_CACHE_DIR or set "
                        "YOLO26_WEIGHTS_PATH"
                    ),
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

    # ------------------------------------------------------------------
    # Public prediction entry point
    # ------------------------------------------------------------------

    def predict(
        self,
        image_path: Path,
        *,
        asset_id: str,
        labels: list[str] | None = None,

        # --------------------------------------------------------------
        # Dynamic execution controls.
        #
        # Existing callers can omit all of these and retain the old
        # full-image behavior.
        # --------------------------------------------------------------
        strategy: str = "full_image",
        image_size: int | None = None,
        tile_rows: int = 1,
        tile_cols: int = 1,
        tile_overlap: float = 0.0,

        # Optional per-plan confidence threshold.
        #
        # This is NOT automatically lowered.
        confidence_threshold: float | None = None,

        # Optional planner metadata for provenance/audit.
        plan_source: str = "default",
        plan_reason: str = "",
        **kwargs: Any,
    ) -> list[NormalizedDetection]:
        """Run YOLO according to the selected execution strategy.

        Dynamic flow:

            full_image
                ↓
            high_resolution
                ↓
            tiled
                ↓
            high_resolution_tiled

        The agent/router decides which strategy is appropriate.
        """

        if getattr(self, "_loaded", False):
            logger.info(
                "model_reuse",
                model_key=self.key,
                registry_id=getattr(self, "registry_id", "unknown"),
            )
        else:
            self.load()

        if self._model is None:
            raise ModelUnavailableError(
                f"YOLOv26 model {self.model_id} is not loaded or is unavailable.",
                details={
                    "model_id": self.model_id,
                    "weights": str(self.weights_path),
                    "device": self.device,
                },
            )

        if not image_path.exists():
            raise ModelUnavailableError(
                f"Image not found: {image_path}",
                details={
                    "image_path": str(image_path),
                },
            )

        with Image.open(image_path) as img:
            width, height = img.size

        if width <= 0 or height <= 0:
            return []

        effective_confidence = self._resolve_confidence(
            confidence_threshold
        )

        if isinstance(image_size, (list, tuple)):
            image_size = int(image_size[0]) if image_size else None
        elif image_size is not None:
            try:
                image_size = int(image_size)
            except (ValueError, TypeError):
                image_size = None

        if isinstance(tile_rows, (list, tuple)):
            tile_rows = int(tile_rows[0]) if tile_rows else 1
        else:
            try:
                tile_rows = int(tile_rows)
            except (ValueError, TypeError):
                tile_rows = 1

        if isinstance(tile_cols, (list, tuple)):
            tile_cols = int(tile_cols[0]) if tile_cols else 1
        else:
            try:
                tile_cols = int(tile_cols)
            except (ValueError, TypeError):
                tile_cols = 1

        if isinstance(tile_overlap, (list, tuple)):
            tile_overlap = float(tile_overlap[0]) if tile_overlap else 0.0
        else:
            try:
                tile_overlap = float(tile_overlap)
            except (ValueError, TypeError):
                tile_overlap = 0.0

        normalized_strategy = (
            strategy or "full_image"
        ).strip().lower()

        configured_image_size = image_size or (
            1024 if normalized_strategy == "tiled" else DEFAULT_INFERENCE_SIZE
        )
        resize_scale = min(
            configured_image_size / width,
            configured_image_size / height,
        )
        resized_width = round(width * resize_scale)
        resized_height = round(height * resize_scale)
        pad_x = (configured_image_size - resized_width) / 2.0
        pad_y = (configured_image_size - resized_height) / 2.0
        logger.info(
            "yolo_image_resolution_diagnostic",
            asset_id=asset_id,
            image_name=image_path.name,
            source_width=width,
            source_height=height,
            decoded_width=width,
            decoded_height=height,
            model_input_width=configured_image_size,
            model_input_height=configured_image_size,
            configured_image_size=configured_image_size,
            resize_scale=resize_scale,
            pad_x=pad_x,
            pad_y=pad_y,
            tile_count=(max(1, tile_rows) * max(1, tile_cols)) if "tiled" in normalized_strategy else 1,
            coordinate_note="YOLO returns boxes scaled to the supplied source/tile; adapter restores tile boxes to original pixels before percent normalization",
        )

        if normalized_strategy == "full_image":
            effective_image_size = image_size or DEFAULT_INFERENCE_SIZE
            detections = self._predict_full_image(
                image_path=image_path,
                asset_id=asset_id,
                image_width=width,
                image_height=height,
                labels=labels,
                confidence_threshold=(
                    effective_confidence
                ),
                image_size=effective_image_size,
                plan_source=plan_source,
                plan_reason=plan_reason,
            )

        elif normalized_strategy == "high_resolution":
            effective_image_size = image_size or 1280
            detections = self._predict_full_image(
                image_path=image_path,
                asset_id=asset_id,
                image_width=width,
                image_height=height,
                labels=labels,
                confidence_threshold=(
                    effective_confidence
                ),
                image_size=effective_image_size,
                plan_source=plan_source,
                plan_reason=plan_reason,
            )

        elif normalized_strategy == "video_tracking":
            # Video frames are already extracted and bounded by the video
            # sampler. Run one normal prediction on the selected frame while
            # preserving the planner's strategy in provenance.
            effective_image_size = image_size or DEFAULT_INFERENCE_SIZE
            detections = self._predict_full_image(
                image_path=image_path,
                asset_id=asset_id,
                image_width=width,
                image_height=height,
                labels=labels,
                confidence_threshold=effective_confidence,
                image_size=effective_image_size,
                plan_source=plan_source,
                plan_reason=plan_reason,
            )

        elif normalized_strategy == "tiled":
            effective_image_size = image_size or 1024
            detections = self._predict_tiled(
                image_path=image_path,
                asset_id=asset_id,
                image_width=width,
                image_height=height,
                labels=labels,
                confidence_threshold=(
                    effective_confidence
                ),
                image_size=effective_image_size,
                tile_rows=max(
                    1,
                    tile_rows,
                ),
                tile_cols=max(
                    1,
                    tile_cols,
                ),
                tile_overlap=tile_overlap,
                plan_source=plan_source,
                plan_reason=plan_reason,
            )

        elif (
            normalized_strategy
            == "high_resolution_tiled"
        ):
            effective_image_size = image_size or 1280
            detections = self._predict_tiled(
                image_path=image_path,
                asset_id=asset_id,
                image_width=width,
                image_height=height,
                labels=labels,
                confidence_threshold=(
                    effective_confidence
                ),
                image_size=effective_image_size,
                tile_rows=max(
                    1,
                    tile_rows,
                ),
                tile_cols=max(
                    1,
                    tile_cols,
                ),
                tile_overlap=tile_overlap,
                plan_source=plan_source,
                plan_reason=plan_reason,
            )

        else:
            logger.warning(
                "unknown_yolo_execution_strategy",
                strategy=normalized_strategy,
                fallback="full_image",
            )

            effective_image_size = image_size or 640
            detections = self._predict_full_image(
                image_path=image_path,
                asset_id=asset_id,
                image_width=width,
                image_height=height,
                labels=labels,
                confidence_threshold=(
                    effective_confidence
                ),
                image_size=effective_image_size,
                plan_source=plan_source,
                plan_reason=plan_reason,
            )

        logger.info(
            "yolo_prediction_complete",
            asset_id=asset_id,
            strategy=normalized_strategy,
            image_width=width,
            image_height=height,
            detections=len(detections),
            confidence_threshold=(
                effective_confidence
            ),
            image_size=effective_image_size,
            tile_rows=tile_rows,
            tile_cols=tile_cols,
            tile_overlap=tile_overlap,
            plan_source=plan_source,
        )

        return detections

    # ------------------------------------------------------------------
    # Confidence handling
    # ------------------------------------------------------------------

    def _resolve_confidence(
        self,
        requested: float | None,
    ) -> float:
        """Resolve the execution threshold safely.

        This function does NOT automatically lower confidence.

        Planner-provided values are bounded to [0.05, 0.95] to prevent
        accidental pathological configuration.
        """

        value = (
            self.confidence_threshold
            if requested is None
            else requested
        )

        if not math.isfinite(value):
            value = self.confidence_threshold

        return max(
            0.05,
            min(
                0.95,
                value,
            ),
        )

    # ------------------------------------------------------------------
    # Full-image inference
    # ------------------------------------------------------------------

    def _predict_full_image(
        self,
        *,
        image_path: Path,
        asset_id: str,
        image_width: int,
        image_height: int,
        labels: list[str] | None,
        confidence_threshold: float,
        image_size: int | None,
        plan_source: str,
        plan_reason: str,
    ) -> list[NormalizedDetection]:
        """Run normal/full-image YOLO inference."""

        effective_image_size = image_size or DEFAULT_INFERENCE_SIZE

        # pyrefly: ignore [missing-attribute]
        results = self._model.predict(
            source=str(image_path),
            conf=confidence_threshold,
            device=self.device,
            imgsz=effective_image_size,
            iou=NMS_IOU_THRESHOLD,
            max_det=MAX_DETECTIONS,
            agnostic_nms=False,
            verbose=False,
        )

        if not results:
            return []

        result = results[0]

        return self._normalize_result(
            result=result,
            asset_id=asset_id,
            image_width=image_width,
            image_height=image_height,
            offset_x=0.0,
            offset_y=0.0,
            source_width=image_width,
            source_height=image_height,
            tile_id=None,
            strategy=(
                "high_resolution"
                if image_size
                else "full_image"
            ),
            labels=labels,
            confidence_threshold=(
                confidence_threshold
            ),
            plan_source=plan_source,
            plan_reason=plan_reason,
        )

    # ------------------------------------------------------------------
    # Tiled inference
    # ------------------------------------------------------------------

    def _predict_tiled(
        self,
        *,
        image_path: Path,
        asset_id: str,
        image_width: int,
        image_height: int,
        labels: list[str] | None,
        confidence_threshold: float,
        image_size: int,
        tile_rows: int,
        tile_cols: int,
        tile_overlap: float,
        plan_source: str,
        plan_reason: str,
    ) -> list[NormalizedDetection]:
        """Run tiled inference and restore global coordinates.

        Tiling is useful for dense/aerial scenes and small objects.

        Each tile detection is converted:

            tile coordinates
                    ↓
            original image coordinates
                    ↓
            normalized 0-100 percent coordinates

        Cross-tile duplicate merging happens downstream in merge.py.
        """

        if isinstance(image_size, (list, tuple)):
            image_size = int(image_size[0]) if image_size else 1024
        else:
            try:
                image_size = int(image_size)
            except (ValueError, TypeError):
                image_size = 1024

        overlap = max(
            0.0,
            min(
                0.75,
                tile_overlap,
            ),
        )

        tiles = self._build_tiles(
            image_width=image_width,
            image_height=image_height,
            rows=tile_rows,
            cols=tile_cols,
            overlap=overlap,
        )

        if not tiles:
            return []

        logger.info(
            "yolo_tiled_inference_start",
            asset_id=asset_id,
            image_width=image_width,
            image_height=image_height,
            tile_rows=tile_rows,
            tile_cols=tile_cols,
            tile_count=len(tiles),
            overlap=overlap,
            image_size=image_size,
            confidence_threshold=(
                confidence_threshold
            ),
            plan_source=plan_source,
        )

        all_detections: list[
            NormalizedDetection
        ] = []

        with Image.open(image_path) as original:
            rgb = original.convert("RGB")

            for tile_index, tile in enumerate(
                tiles
            ):
                x1, y1, x2, y2 = tile

                tile_image = rgb.crop(
                    (
                        x1,
                        y1,
                        x2,
                        y2,
                    )
                )

                tile_width = x2 - x1
                tile_height = y2 - y1

                if (
                    tile_width <= 0
                    or tile_height <= 0
                ):
                    continue

                tile_scale = min(image_size / tile_width, image_size / tile_height)
                tile_resized_width = round(tile_width * tile_scale)
                tile_resized_height = round(tile_height * tile_scale)
                logger.info(
                    "yolo_tile_resolution_diagnostic",
                    asset_id=asset_id,
                    image_name=image_path.name,
                    tile_id=tile_index,
                    original_image_width=image_width,
                    original_image_height=image_height,
                    tile_source_width=tile_width,
                    tile_source_height=tile_height,
                    model_input_width=image_size,
                    model_input_height=image_size,
                    configured_image_size=image_size,
                    resize_scale=tile_scale,
                    pad_x=(image_size - tile_resized_width) / 2.0,
                    pad_y=(image_size - tile_resized_height) / 2.0,
                )

                try:
                    # pyrefly: ignore [missing-attribute]
                    results = self._model.predict(
                        source=tile_image,
                        conf=confidence_threshold,
                        device=self.device,
                        imgsz=image_size,
                        iou=NMS_IOU_THRESHOLD,
                        max_det=MAX_DETECTIONS,
                        agnostic_nms=False,
                        verbose=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "yolo_tile_inference_failed",
                        asset_id=asset_id,
                        tile_index=tile_index,
                        tile=tile,
                        error=str(exc),
                    )
                    continue

                if not results:
                    continue

                result = results[0]

                tile_detections = (
                    self._normalize_result(
                        result=result,
                        asset_id=asset_id,
                        image_width=image_width,
                        image_height=image_height,
                        offset_x=float(x1),
                        offset_y=float(y1),
                        source_width=tile_width,
                        source_height=tile_height,
                        tile_id=tile_index,
                        strategy=(
                            "high_resolution_tiled"
                            if image_size
                            else "tiled"
                        ),
                        labels=labels,
                        confidence_threshold=(
                            confidence_threshold
                        ),
                        plan_source=plan_source,
                        plan_reason=plan_reason,
                    )
                )

                all_detections.extend(
                    tile_detections
                )

        logger.info(
            "yolo_tiled_inference_complete",
            asset_id=asset_id,
            tile_count=len(tiles),
            raw_tile_detections=len(
                all_detections
            ),
            plan_source=plan_source,
        )

        return all_detections

    # ------------------------------------------------------------------
    # Tile generation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tiles(
        *,
        image_width: int,
        image_height: int,
        rows: int,
        cols: int,
        overlap: float,
    ) -> list[
        tuple[int, int, int, int]
    ]:
        """Create deterministic overlapping image tiles.

        The final tiles always reach the right/bottom image boundaries.

        Returned coordinates are:

            x1, y1, x2, y2

        in ORIGINAL IMAGE PIXELS.
        """

        rows = max(1, rows)
        cols = max(1, cols)

        if rows == 1 and cols == 1:
            return [
                (
                    0,
                    0,
                    image_width,
                    image_height,
                )
            ]

        overlap = max(
            0.0,
            min(
                0.75,
                overlap,
            ),
        )

        # Choose a tile size that allows the requested number of tiles
        # while accounting for overlap.
        tile_width = math.ceil(
            image_width
            / (
                cols
                - (
                    cols - 1
                )
                * overlap
            )
        )

        tile_height = math.ceil(
            image_height
            / (
                rows
                - (
                    rows - 1
                )
                * overlap
            )
        )

        tile_width = min(
            image_width,
            max(1, tile_width),
        )

        tile_height = min(
            image_height,
            max(1, tile_height),
        )

        step_x = max(
            1,
            round(
                tile_width
                * (
                    1.0
                    - overlap
                )
            ),
        )

        step_y = max(
            1,
            round(
                tile_height
                * (
                    1.0
                    - overlap
                )
            ),
        )

        def starts(
            length: int,
            tile: int,
            step: int,
            count: int,
        ) -> list[int]:
            if count <= 1:
                return [0]

            values: list[int] = []

            for index in range(count):
                start = index * step

                if (
                    start + tile
                    > length
                ):
                    start = max(
                        0,
                        length - tile,
                    )

                if start not in values:
                    values.append(
                        start
                    )

            # Guarantee boundary coverage.
            last = max(
                0,
                length - tile,
            )

            if last not in values:
                values.append(last)

            return values

        xs = starts(
            image_width,
            tile_width,
            step_x,
            cols,
        )

        ys = starts(
            image_height,
            tile_height,
            step_y,
            rows,
        )

        result: list[
            tuple[int, int, int, int]
        ] = []

        for y in ys:
            for x in xs:
                x2 = min(
                    image_width,
                    x + tile_width,
                )

                y2 = min(
                    image_height,
                    y + tile_height,
                )

                result.append(
                    (
                        x,
                        y,
                        x2,
                        y2,
                    )
                )

        return result

    # ------------------------------------------------------------------
    # Result normalization
    # ------------------------------------------------------------------

    def _normalize_result(
        self,
        *,
        result: Any,
        asset_id: str,
        image_width: int,
        image_height: int,
        offset_x: float,
        offset_y: float,
        source_width: int,
        source_height: int,
        tile_id: int | None,
        strategy: str,
        labels: list[str] | None,
        confidence_threshold: float,
        plan_source: str,
        plan_reason: str,
    ) -> list[NormalizedDetection]:
        """Convert YOLO output to normalized detections.

        For tiled inference:

            tile x/y
                ↓
            + tile offset
                ↓
            original image x/y
                ↓
            percent-of-natural-image coordinates
        """

        boxes = getattr(
            result,
            "boxes",
            None,
        )

        if boxes is None:
            return []

        names = (
            getattr(
                result,
                "names",
                None,
            )
            or {}
        )

        xyxy = (
            boxes.xyxy
            .cpu()
            .numpy()
        )

        confs = (
            boxes.conf
            .cpu()
            .numpy()
        )

        clss = (
            boxes.cls
            .cpu()
            .numpy()
            .astype(int)
        )

        logger.info(
            "yolo_detection_diagnostic",
            asset_id=asset_id,
            tile_id=tile_id,
            stage="raw_model_output",
            raw_count=len(xyxy),
            confidence_min=round(float(confs.min()), 4) if len(confs) else None,
            confidence_mean=round(float(confs.mean()), 4) if len(confs) else None,
            confidence_max=round(float(confs.max()), 4) if len(confs) else None,
        )

        allowed_labels = None
        label_mapper = None

        if labels:
            from app.inference.ontology_map import build_ontology_index, map_raw_label
            ont_idx = build_ontology_index(labels)
            label_mapper = lambda value: map_raw_label(value, ont_idx)
            allowed_labels = {
                label.strip().casefold()
                for label in labels
                if label.strip()
            }

        def class_name(class_id: int) -> str:
            if isinstance(names, dict):
                raw_name = names.get(class_id, names.get(str(class_id), f"class_{class_id}"))
            elif isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
                raw_name = names[class_id]
            else:
                raw_name = f"class_{class_id}"
            return str(raw_name).strip()

        def reject_detection(
            *,
            raw_label: str,
            normalized_label: str | None,
            class_id: int,
            confidence: float,
            raw_box: list[float],
            restored_box: list[float] | None,
            reason: str,
        ) -> None:
            logger.warning(
                "yolo_tile_detection_rejected",
                asset_id=asset_id,
                tile_id=tile_id,
                raw_label=raw_label,
                normalized_label=normalized_label,
                class_id=class_id,
                confidence=confidence,
                effective_threshold=confidence_threshold,
                requested_labels=labels or [],
                raw_box=raw_box,
                restored_box=restored_box,
                rejection_reason=reason,
            )

        now = datetime.now(UTC)

        detections: list[
            NormalizedDetection
        ] = []
        thresholded_count = 0
        mapped_count = 0

        for i in range(
            len(xyxy)
        ):
            tile_x1, tile_y1, tile_x2, tile_y2 = (
                xyxy[i]
            )

            confidence = float(
                confs[i]
            )

            class_id = int(
                clss[i]
            )

            raw_label = class_name(class_id)
            normalized_label = None
            if label_mapper is not None:
                mapped = label_mapper(raw_label)
                normalized_label = mapped.canonical_label if mapped.accepted else None

            # ----------------------------------------------------------
            # Optional label filter.
            #
            # IMPORTANT:
            # Do not perform semantic fuzzy matching here.
            # Ontology mapping remains downstream.
            # ----------------------------------------------------------
            if confidence < confidence_threshold:
                reject_detection(
                    raw_label=raw_label,
                    normalized_label=normalized_label,
                    class_id=class_id,
                    confidence=confidence,
                    raw_box=[float(tile_x1), float(tile_y1), float(tile_x2), float(tile_y2)],
                    restored_box=None,
                    reason="confidence_below_effective_threshold",
                )
                continue

            thresholded_count += 1

            label_matches = (
                allowed_labels is None
                or raw_label.casefold() in allowed_labels
                or (normalized_label is not None and normalized_label.casefold() in allowed_labels)
            )
            if not label_matches:
                reject_detection(
                    raw_label=raw_label,
                    normalized_label=normalized_label,
                    class_id=class_id,
                    confidence=confidence,
                    raw_box=[float(tile_x1), float(tile_y1), float(tile_x2), float(tile_y2)],
                    restored_box=None,
                    reason="requested_label_mismatch",
                )
                continue

            mapped_count += 1

            # ----------------------------------------------------------
            # Convert tile coordinates to original-image coordinates.
            # ----------------------------------------------------------

            # Ultralytics normally returns coordinates in the source tile
            # space.  Some transports return model-input coordinates instead;
            # detect that representation and restore it before adding the
            # tile offset.  Never scale coordinates that are already tile-local.
            raw_x2 = float(tile_x2)
            raw_y2 = float(tile_y2)
            coordinate_scale_x = 1.0
            coordinate_scale_y = 1.0
            orig_shape = getattr(result, "orig_shape", None)
            result_height = result_width = None
            if isinstance(orig_shape, (tuple, list)) and len(orig_shape) >= 2:
                result_height = float(orig_shape[0])
                result_width = float(orig_shape[1])
            if (
                result_width
                and result_height
                and (
                    abs(result_width - float(source_width)) > 1.0
                    or abs(result_height - float(source_height)) > 1.0
                )
            ):
                coordinate_scale_x = float(source_width) / result_width
                coordinate_scale_y = float(source_height) / result_height

            local_x1 = float(tile_x1) * coordinate_scale_x
            local_y1 = float(tile_y1) * coordinate_scale_y
            local_x2 = float(tile_x2) * coordinate_scale_x
            local_y2 = float(tile_y2) * coordinate_scale_y

            global_x1 = local_x1 + offset_x

            global_y1 = (
                local_y1 + offset_y
            )

            global_x2 = (
                local_x2 + offset_x
            )

            global_y2 = (
                local_y2 + offset_y
            )

            # Clamp against ORIGINAL image dimensions.
            global_x1 = max(
                0.0,
                min(
                    global_x1,
                    float(image_width),
                ),
            )

            global_y1 = max(
                0.0,
                min(
                    global_y1,
                    float(image_height),
                ),
            )

            global_x2 = max(
                0.0,
                min(
                    global_x2,
                    float(image_width),
                ),
            )

            global_y2 = max(
                0.0,
                min(
                    global_y2,
                    float(image_height),
                ),
            )

            global_width = max(
                0.0,
                global_x2 - global_x1,
            )

            global_height = max(
                0.0,
                global_y2 - global_y1,
            )

            restored_box = [global_x1, global_y1, global_x2, global_y2]

            # Ignore degenerate boxes.
            if (
                global_width <= 0.0
                or global_height <= 0.0
            ):
                reject_detection(
                    raw_label=raw_label,
                    normalized_label=normalized_label,
                    class_id=class_id,
                    confidence=confidence,
                    raw_box=[float(tile_x1), float(tile_y1), float(tile_x2), float(tile_y2)],
                    restored_box=restored_box,
                    reason="invalid_or_degenerate_restored_box",
                )
                continue

            # The old minimum of 0.05% is retained for compatibility.
            #
            # We do NOT increase this threshold because doing so can
            # remove legitimate tiny aerial vehicles.
            if (
                (
                    global_width
                    / image_width
                )
                * 100.0
                < 0.05
            ):
                reject_detection(
                    raw_label=raw_label,
                    normalized_label=normalized_label,
                    class_id=class_id,
                    confidence=confidence,
                    raw_box=[float(tile_x1), float(tile_y1), float(tile_x2), float(tile_y2)],
                    restored_box=restored_box,
                    reason="restored_box_width_below_minimum",
                )
                continue

            if (
                (
                    global_height
                    / image_height
                )
                * 100.0
                < 0.05
            ):
                reject_detection(
                    raw_label=raw_label,
                    normalized_label=normalized_label,
                    class_id=class_id,
                    confidence=confidence,
                    raw_box=[float(tile_x1), float(tile_y1), float(tile_x2), float(tile_y2)],
                    restored_box=restored_box,
                    reason="restored_box_height_below_minimum",
                )
                continue

            bbox = clamp_box(
                (
                    global_x1
                    / image_width
                )
                * 100.0,
                (
                    global_y1
                    / image_height
                )
                * 100.0,
                (
                    global_width
                    / image_width
                )
                * 100.0,
                (
                    global_height
                    / image_height
                )
                * 100.0,
            )

            provenance = {
                "engine": "ultralytics",
                "coordinate_system": (
                    "percent_of_natural_image"
                ),
                "image_width": image_width,
                "image_height": image_height,

                # Original YOLO coordinates.
                "raw_xyxy": [
                    float(tile_x1),
                    float(tile_y1),
                    float(tile_x2),
                    float(tile_y2),
                ],

                # Restored global coordinates.
                "global_xyxy": [
                    global_x1,
                    global_y1,
                    global_x2,
                    global_y2,
                ],

                "raw_label": raw_label,
                "raw_model_label": raw_label,
                "raw_class_id": class_id,

                # IMPORTANT:
                # This is exactly the YOLO model confidence.
                "raw_model_confidence": confidence,

                "confidence_semantics": (
                    "original_model_confidence_only"
                ),

                "model_key": self.key,
                "model_id": self.model_id,

                "execution": {
                    "strategy": strategy,
                    "image_size": image_size_for_provenance(
                        result
                    ),
                    "confidence_threshold": (
                        confidence_threshold
                    ),
                    "plan_source": plan_source,
                    "plan_reason": plan_reason,
                },

                "tile": (
                    {
                        "tile_id": tile_id,
                        "offset_x": offset_x,
                        "offset_y": offset_y,
                        "source_width": source_width,
                        "source_height": source_height,
                    }
                    if tile_id is not None
                    else None
                ),
            }

            if i == 0:
                logger.info(
                    "yolo_coordinate_restoration_sample",
                    asset_id=asset_id,
                    image_name=getattr(result, "path", None) or "",
                    tile_id=tile_id,
                    model_coordinates=[float(tile_x1), float(tile_y1), float(tile_x2), float(tile_y2)],
                    restored_coordinates=[global_x1, global_y1, global_x2, global_y2],
                    original_image_dimensions={"width": image_width, "height": image_height},
                    coordinates_in_bounds=(
                        0.0 <= global_x1 <= image_width
                        and 0.0 <= global_y1 <= image_height
                        and 0.0 <= global_x2 <= image_width
                        and 0.0 <= global_y2 <= image_height
                    ),
                )

            detections.append(
                NormalizedDetection(
                    id=str(uuid4()),
                    asset_id=asset_id,
                    label=raw_label,
                    class_id=class_id,
                    bbox=bbox,

                    # NEVER modify this value.
                    confidence=confidence,

                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance=provenance,
                )
            )

        by_label: dict[str, int] = {}
        for detection in detections:
            by_label[detection.label] = by_label.get(detection.label, 0) + 1
        logger.info(
            "yolo_detection_diagnostic",
            asset_id=asset_id,
            tile_id=tile_id,
            stage="normalized_filtered",
            filtered_count=len(detections),
            detections_by_class=by_label,
            confidence_min=round(min((d.confidence for d in detections), default=0.0), 4) if detections else None,
            confidence_mean=round(sum(d.confidence for d in detections) / len(detections), 4) if detections else None,
            confidence_max=round(max((d.confidence for d in detections), default=0.0), 4) if detections else None,
        )
        logger.info(
            "yolo_stage_counts",
            asset_id=asset_id,
            yolo_raw_count=len(xyxy),
            yolo_thresholded_count=thresholded_count,
            yolo_mapped_count=mapped_count,
            yolo_final_count=len(detections),
        )
        return detections


def image_size_for_provenance(
    result: Any,
) -> int | list[int] | None:
    """Extract the actual inference shape when available.

    Ultralytics result metadata differs between versions, so this helper
    is deliberately defensive.
    """

    speed = getattr(
        result,
        "speed",
        None,
    )

    if isinstance(speed, dict):
        # No reliable imgsz is exposed here across all versions.
        _ = speed

    return None


# Backward-compatible class alias for unit tests
Yolo26DetectorAdapter = Yolo26Adapter
