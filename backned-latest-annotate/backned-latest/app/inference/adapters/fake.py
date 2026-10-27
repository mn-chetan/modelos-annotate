"""Test-only fake adapters. Never selectable via production runtime config."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw

from app.inference.contracts import (
    BoundingBoxPercent,
    LabelSuggestion,
    ModelCapability,
    ModelKey,
    NormalizedClassification,
    NormalizedDetection,
    NormalizedMask,
)
from app.inference.device import clamp_box
from app.logging import get_logger

logger = get_logger(__name__)


def _filter_valid_labels(raw_labels: list[str] | None) -> list[str]:
    if not raw_labels:
        return []
    from app.inference.ontology_map import is_invalid_workflow_label
    return [
        lbl.strip() for lbl in raw_labels
        if lbl and str(lbl).strip() and not is_invalid_workflow_label(str(lbl).strip())
    ]


class FakeYoloAdapter:
    key = ModelKey.YOLO26.value
    capabilities = [ModelCapability.DETECTION]

    def __init__(self, model_id: str = "yolo26n.pt", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded: bool = False

    def load(self) -> None:
        self._loaded = True

    def predict(
        self,
        image_path: Path,
        *,
        asset_id: str,
        labels: list[str] | None = None,
        **kwargs: Any,
    ) -> list[NormalizedDetection]:
        if getattr(self, "_loaded", False):
            logger.info(
                "model_reuse",
                model_key=self.key,
                registry_id=getattr(self, "registry_id", "unknown"),
            )
        else:
            self.load()

        with Image.open(image_path) as img:
            width, height = img.size
        valid_labels = _filter_valid_labels(labels)
        target_labels = valid_labels if valid_labels else ["car", "person", "traffic light"]
        now = datetime.now(UTC)
        detections = []
        for idx, lbl in enumerate(target_labels[:4]):
            detections.append(
                NormalizedDetection(
                    id=str(uuid4()),
                    asset_id=asset_id,
                    label=lbl,
                    class_id=idx,
                    bbox=clamp_box(10.0 + idx * 15.0, 10.0 + idx * 10.0, 25.0, 30.0),
                    confidence=0.88 - idx * 0.05,
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={
                        "engine": "fake",
                        "image_width": width,
                        "image_height": height,
                        "raw_label": lbl,
                    },
                )
            )
        return detections


class FakeDinoAdapter:
    key = ModelKey.DINO.value
    capabilities = [ModelCapability.OPEN_VOCAB_DETECTION]

    def __init__(
        self, model_id: str = "IDEA-Research/grounding-dino-tiny", device: str = "cpu"
    ) -> None:
        self.model_id = model_id
        self.device = device
        self._loaded: bool = False

    def load(self) -> None:
        self._loaded = True

    def predict(
        self,
        image_path: Path,
        *,
        asset_id: str,
        labels: list[str] | None = None,
        **kwargs: Any,
    ) -> list[NormalizedDetection]:
        if getattr(self, "_loaded", False):
            logger.info(
                "model_reuse",
                model_key=self.key,
                registry_id=getattr(self, "registry_id", "unknown"),
            )
        else:
            self.load()

        with Image.open(image_path) as img:
            width, height = img.size
        valid_labels = _filter_valid_labels(labels)
        target_labels = valid_labels if valid_labels else ["road barrier", "traffic sign"]
        now = datetime.now(UTC)
        detections = []
        for idx, lbl in enumerate(target_labels[:4]):
            detections.append(
                NormalizedDetection(
                    id=str(uuid4()),
                    asset_id=asset_id,
                    label=lbl,
                    class_id=None,
                    bbox=clamp_box(20.0 + idx * 15.0, 20.0 + idx * 10.0, 20.0, 20.0),
                    confidence=0.82 - idx * 0.04,
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={
                        "engine": "fake",
                        "image_width": width,
                        "image_height": height,
                        "prompt_labels": target_labels,
                        "raw_label": lbl,
                    },
                )
            )
        return detections


class FakeFlorenceAdapter:
    key = ModelKey.FLORENCE.value
    capabilities = [ModelCapability.CAPTION, ModelCapability.LABEL_ASSIST]

    def __init__(
        self, model_id: str = "microsoft/Florence-2-base", device: str = "cpu"
    ) -> None:
        self.model_id = model_id
        self.device = device
        self._loaded: bool = False

    def load(self) -> None:
        self._loaded = True

    def assist(
        self,
        image_path: Path | None,
        *,
        asset_id: str | None = None,
        goal: str = "",
        labels: list[str] | None = None,
        strategy: str = "generic",
    ) -> LabelSuggestion:
        if getattr(self, "_loaded", False):
            logger.info(
                "model_reuse",
                model_key=self.key,
                registry_id=getattr(self, "registry_id", "unknown"),
            )
        else:
            self.load()

        suggested = labels[:] if labels else ["person", "vehicle"]
        return LabelSuggestion(
            labels=suggested,
            caption="fake caption of scene",
            rationale=f"Fake Florence assist for strategy={strategy}",
            model_id=self.model_id,
            model_key=self.key,
            inferred_at=datetime.now(UTC),
            provenance={"engine": "fake", "goal": goal, "asset_id": asset_id},
        )


class FakeSam2Adapter:
    key = ModelKey.SAM2.value
    capabilities = [ModelCapability.SEGMENTATION]

    def __init__(self, model_id: str = "sam2.1_t.pt", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded: bool = False

    def load(self) -> None:
        self._loaded = True

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
        if getattr(self, "_loaded", False):
            logger.info(
                "model_reuse",
                model_key=self.key,
                registry_id=getattr(self, "registry_id", "unknown"),
            )
        else:
            self.load()

        with Image.open(image_path) as img:
            width, height = img.size
        now = datetime.now(UTC)
        masks: list[NormalizedMask] = []
        for i, box in enumerate(boxes):
            label = labels[i] if labels and i < len(labels) else "object"
            ann_id = annotation_ids[i] if annotation_ids and i < len(annotation_ids) else None
            mask_id = str(uuid4())
            mask_path: str | None = None
            # Deterministic filled-rect mask from the prompt box (local/fake path).
            x1 = max(0, int((box.x / 100.0) * width))
            y1 = max(0, int((box.y / 100.0) * height))
            x2 = min(width, int(((box.x + box.w) / 100.0) * width))
            y2 = min(height, int(((box.y + box.h) / 100.0) * height))
            mask_arr = Image.new("L", (width, height), 0)
            ImageDraw.Draw(mask_arr).rectangle((x1, y1, max(x1, x2 - 1), max(y1, y2 - 1)), fill=255)
            if storage_dir is not None:
                storage_dir.mkdir(parents=True, exist_ok=True)
                file_path = storage_dir / f"{mask_id}.png"
                mask_arr.save(file_path)
                mask_path = str(file_path)
            flat = list(mask_arr.get_flattened_data() if hasattr(mask_arr, "get_flattened_data") else mask_arr.getdata())
            rle_counts: list[int] = []
            if flat:
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
            masks.append(
                NormalizedMask(
                    id=mask_id,
                    asset_id=asset_id,
                    annotation_id=ann_id,
                    label=label,
                    confidence=0.88,
                    width=width,
                    height=height,
                    mask_path=mask_path,
                    mask_rle={
                        "counts": rle_counts,
                        "size": [height, width],
                        "box": {"x": box.x, "y": box.y, "w": box.w, "h": box.h},
                    },
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={"engine": "fake"},
                )
            )
        return masks


class FakeClipAdapter:
    key = ModelKey.CLIP.value
    capabilities = [ModelCapability.CLASSIFICATION]

    def __init__(self, model_id: str = "openai/clip-vit-base-patch32", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._loaded: bool = False

    def load(self) -> None:
        self._loaded = True

    def classify_regions(
        self,
        image_path: Path,
        *,
        asset_id: str,
        regions: list[tuple[str | None, BoundingBoxPercent]],
        text_labels: list[str],
    ) -> list[NormalizedClassification]:
        if not text_labels:
            from app.errors import ValidationAppError

            raise ValidationAppError("text_labels must not be empty", details={"asset_id": asset_id})
        if getattr(self, "_loaded", False):
            logger.info("model_reuse", model_key=self.key, registry_id=getattr(self, "registry_id", "unknown"))
        else:
            self.load()

        now = datetime.now(UTC)
        results: list[NormalizedClassification] = []
        for annotation_id, _region in regions:
            # Deterministic ranking: first label wins with a fixed, plausible score.
            candidates = [
                {"label": lbl, "score": round(0.9 - 0.1 * i, 2)} for i, lbl in enumerate(text_labels)
            ]
            results.append(
                NormalizedClassification(
                    id=str(uuid4()),
                    asset_id=asset_id,
                    annotation_id=annotation_id,
                    label=text_labels[0],
                    confidence=candidates[0]["score"],
                    taxonomy_path=None,
                    attributes={"candidates": candidates},
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={"engine": "fake", "text_labels": text_labels},
                )
            )
        return results

