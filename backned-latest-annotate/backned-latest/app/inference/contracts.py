"""Normalized multi-model inference contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4


class ModelKey(StrEnum):
    YOLO26 = "yolo26"
    FASTER_RCNN = "faster_rcnn"
    FLORENCE = "florence"
    DINO = "dino"
    SAM2 = "sam2"
    CLIP = "clip"
    TRACKER = "tracker"
    GLINER = "gliner"
    QWEN3_EMBEDDING = "qwen3_embedding"
    QWEN3_RERANKER = "qwen3_reranker"
    PADDLEOCR = "paddleocr"


class ModelCapability(StrEnum):
    DETECTION = "detection"
    OPEN_VOCAB_DETECTION = "open_vocab_detection"
    SEGMENTATION = "segmentation"
    CAPTION = "caption"
    LABEL_ASSIST = "label_assist"
    CLASSIFICATION = "classification"
    TRACKING = "tracking"
    NER = "ner"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    OCR = "ocr"


class ModelAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    LOADING = "loading"
    NOT_LOADED = "not_loaded"


@dataclass(frozen=True)
class BoundingBoxPercent:
    """Bounding box in percent of natural image dimensions (0–100).

    Coordinate system:
        Origin at top-left of the image.
        x, y = top-left corner.
        w, h = width and height.
    """

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class NormalizedDetection:
    id: str
    asset_id: str

    # Ontology-normalized label.
    label: str

    # Original model class ID, when available.
    class_id: int | None

    bbox: BoundingBoxPercent

    # IMPORTANT:
    # This is ONLY the original model confidence.
    # It must never be replaced by IoU, risk, verification,
    # model agreement, or a merged quality score.
    confidence: float

    model_id: str
    model_key: str
    inferred_at: datetime

    # Preserve raw model evidence and provenance.
    provenance: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return str(uuid4())


@dataclass(frozen=True)
class NormalizedMask:
    id: str
    asset_id: str
    annotation_id: str | None
    label: str
    confidence: float | None
    width: int
    height: int
    mask_path: str | None
    mask_rle: dict[str, Any] | None
    model_id: str
    model_key: str
    inferred_at: datetime
    provenance: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return str(uuid4())


@dataclass(frozen=True)
class LabelSuggestion:
    labels: list[str]
    caption: str | None
    rationale: str
    model_id: str
    model_key: str
    inferred_at: datetime
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedClassification:
    """Zero-shot label/attribute scores for one region (box), possibly multi-label."""

    id: str
    asset_id: str
    annotation_id: str | None

    # Best-scoring label; also present (with scores) in `attributes.candidates`.
    label: str
    confidence: float

    # Dot-separated taxonomy path this label resolves to, e.g. "vehicle.car.sedan".
    taxonomy_path: str | None

    # Additional per-label scores and free-form attributes (e.g. color, material).
    attributes: dict[str, Any]

    model_id: str
    model_key: str
    inferred_at: datetime
    provenance: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return str(uuid4())


@dataclass
class ModelStatus:
    key: str
    model_id: str
    capabilities: list[str]
    availability: str
    device: str
    loaded: bool
    load_duration_ms: int | None = None
    error: str | None = None
    purpose: str = ""


class DetectorAdapter(Protocol):
    key: str
    model_id: str
    device: str
    capabilities: list[ModelCapability]

    def load(self) -> None:
        ...

    def predict(
        self,
        image_path: Path,
        *,
        asset_id: str,
        labels: list[str] | None = None,
    ) -> list[NormalizedDetection]:
        ...


class SegmenterAdapter(Protocol):
    key: str
    model_id: str
    device: str
    capabilities: list[ModelCapability]

    def load(self) -> None:
        ...

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
        ...


class VisionLanguageAdapter(Protocol):
    key: str
    model_id: str
    device: str
    capabilities: list[ModelCapability]

    def load(self) -> None:
        ...

    def assist(
        self,
        image_path: Path | None,
        *,
        asset_id: str | None = None,
        goal: str = "",
        labels: list[str] | None = None,
        strategy: str = "generic",
    ) -> LabelSuggestion:
        ...