"""Model registry and inference runtime boundary."""

from __future__ import annotations

import os
import hashlib
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from app.config import Settings
from app.domain.enums import GeometryType
from app.errors import ModelUnavailableError
from app.inference.adapters.dino import GroundingDinoAdapter
from app.inference.adapters.clip import ClipAdapter
from app.inference.adapters.fake import (
    FakeClipAdapter,
    FakeDinoAdapter,
    FakeFlorenceAdapter,
    FakeSam2Adapter,
    FakeYoloAdapter,
)
from app.inference.adapters.faster_rcnn import FasterRCNNAdapter
from app.inference.adapters.florence import FlorenceAdapter
from app.inference.adapters.sam2 import Sam2Adapter
from app.inference.adapters.yolo26 import Yolo26Adapter
from app.inference.adapters.multimodal_experts import (
    TrackerAdapter,
    GlinerAdapter,
    QwenEmbeddingAdapter,
    QwenRerankerAdapter,
    PaddleOcrAdapter,
)
from app.inference.contracts import (
    ModelAvailability,
    ModelKey,
    ModelStatus,
    NormalizedClassification,
    NormalizedDetection,
)
from app.inference.thresholds import resolve_confidence_threshold
from app.logging import get_logger

logger = get_logger(__name__)


class ModelRegistry:
    """Owns local model lifecycle. Adapters are loaded once and reused."""

    def __init__(self) -> None:
        import uuid
        self.registry_id = str(uuid.uuid4())
        self._adapters: dict[str, Any] = {}
        self._errors: dict[str, str] = {}
        self._enabled: dict[str, bool] = {}
        self._locks: dict[str, threading.Lock] = {}
        # A loaded model object is shared by concurrent batch items.  Loading
        # was already protected, but inference was not; several adapters (and
        # Ultralytics' predictor state in particular) are not re-entrant.
        self._inference_locks: dict[str, threading.Lock] = {}
        # These are the configured vision runtimes required by annotation
        # batches.  Keep initialization sequential: several of these models
        # are CPU/GPU-memory heavy and concurrent startup can cause OOM or
        # thread starvation.  Utility models remain lazy as before.
        self._eager_keys: tuple[str, ...] = (
            ModelKey.YOLO26.value,
            ModelKey.FASTER_RCNN.value,
            ModelKey.DINO.value,
            ModelKey.FLORENCE.value,
            ModelKey.SAM2.value,
            ModelKey.CLIP.value,
        )
        self._purposes: dict[str, str] = {
            ModelKey.YOLO26.value: "Primary closed-set object detection",
            ModelKey.FASTER_RCNN.value: "Secondary accuracy-oriented object detection",
            ModelKey.DINO.value: "Open-vocabulary complementary detection",
            ModelKey.FLORENCE.value: "Vision-language captions and label assistance",
            ModelKey.SAM2.value: "Mask segmentation from boxes/points",
            ModelKey.CLIP.value: "Zero-shot region/attribute classification",
            ModelKey.TRACKER.value: "Object tracking and temporal persistence",
            ModelKey.GLINER.value: "Named Entity Recognition and classification",
            ModelKey.QWEN3_EMBEDDING.value: "Semantic text embedding generation",
            ModelKey.QWEN3_RERANKER.value: "Semantic candidate reranking",
            ModelKey.PADDLEOCR.value: "Document structure layout OCR",
        }

    @staticmethod
    def _get_rss_mb() -> float:
        try:
            import psutil
            return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    @staticmethod
    def _detect_model_source(adapter: Any) -> tuple[str, str | None]:
        weights = getattr(adapter, "weights_path", None)
        if weights:
            p = Path(weights)
            return ("local", str(p)) if p.exists() else ("download_or_cache", str(p))
        cache_dir = getattr(adapter, "cache_dir", None)
        if cache_dir:
            return "huggingface_cache", str(cache_dir)
        model_id = getattr(adapter, "model_id", "")
        if "/" in str(model_id):
            return "huggingface_hub", str(model_id)
        return "local_or_builtin", str(model_id)

    def register(self, key: str, adapter: Any, *, enabled: bool = True) -> None:
        self._adapters[key] = adapter
        self._enabled[key] = enabled
        if hasattr(self, "registry_id"):
            adapter.registry_id = self.registry_id

    def get(self, key: str) -> Any:
        if key not in self._adapters:
            raise ModelUnavailableError(
                f"Unknown model {key!r}",
                details={"model_key": key},
            )
        if not self._enabled.get(key, False):
            raise ModelUnavailableError(
                f"Model {key} is disabled",
                details={"model_key": key, "availability": ModelAvailability.DISABLED.value},
            )
        if key in self._errors:
            raise ModelUnavailableError(
                self._errors[key],
                details={"model_key": key, "availability": ModelAvailability.UNAVAILABLE.value},
            )
        return self._adapters[key]

    def try_load(self, key: str) -> bool:
        if not self._enabled.get(key, False):
            return False
        if key in self._errors:
            return False
        adapter = self._adapters.get(key)
        if adapter is None:
            return False

        lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            was_loaded = bool(getattr(adapter, "_loaded", False) or getattr(adapter, "_model", None) is not None)
            if was_loaded:
                logger.info(
                    "model_runtime_reuse_check",
                    model_key=key,
                    registry_id=self.registry_id,
                    process_id=os.getpid(),
                    reused=True,
                )
                return True

            rss_before = self._get_rss_mb()
            source, source_path = self._detect_model_source(adapter)
            device = getattr(adapter, "device", getattr(adapter, "device_preference", "unknown"))
            logger.info(
                "model_load_start",
                model_key=key,
                model_id=getattr(adapter, "model_id", key),
                device=device,
                model_source=source,
                model_path=source_path,
                rss_before_mb=round(rss_before, 2),
            )
            logger.info(
                "model_startup_load_started",
                model_key=key,
                device=device,
                initialization_phase="startup",
            )

            start = time.perf_counter()
            try:
                adapter.load()
                duration_ms = int((time.perf_counter() - start) * 1000)
                rss_after = self._get_rss_mb()
                rss_delta = rss_after - rss_before
                setattr(adapter, "load_duration_ms", duration_ms)
                logger.info(
                    "model_load_complete",
                    model_key=key,
                    model_id=getattr(adapter, "model_id", key),
                    duration_ms=duration_ms,
                    rss_before_mb=round(rss_before, 2),
                    rss_after_mb=round(rss_after, 2),
                    rss_delta_mb=round(rss_delta, 2),
                )
                logger.info(
                    "model_startup_load_completed",
                    model_key=key,
                    device=device,
                    duration_ms=duration_ms,
                    initialization_phase="startup",
                )
                logger.info(
                    "model_runtime_reuse_check",
                    model_key=key,
                    registry_id=self.registry_id,
                    process_id=os.getpid(),
                    reused=False,
                )
                self._errors.pop(key, None)
                return True
            except Exception as exc:  # noqa: BLE001
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.error(
                    "model_load_failed",
                    model_key=key,
                    model_id=getattr(adapter, "model_id", key),
                    duration_ms=duration_ms,
                    exception_type=type(exc).__name__,
                    exception_repr=repr(exc),
                    error=str(exc),
                    traceback=traceback.format_exc(),
                )
                logger.error(
                    "model_startup_load_failed",
                    model_key=key,
                    device=device,
                    duration_ms=duration_ms,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                    traceback=traceback.format_exc(),
                    initialization_phase="startup",
                )
                self._errors[key] = str(exc)
                return False

    def load_eager(self) -> None:
        """Load configured annotation vision models once, in a bounded order."""
        for key in self._eager_keys:
            if self._enabled.get(key, False):
                self.try_load(key)

    def load_enabled(self) -> None:
        """Eagerly load all enabled models (when explicit pre-warming is required)."""
        for key, enabled in self._enabled.items():
            if enabled:
                self.try_load(key)

    def status(self) -> list[ModelStatus]:
        statuses: list[ModelStatus] = []
        for key, adapter in self._adapters.items():
            enabled = self._enabled.get(key, False)
            loaded = getattr(adapter, "_model", None) is not None or (
                # fakes have no _model; treat load() as no-op success when enabled
                enabled and key not in self._errors and getattr(adapter, "device", None) is not None
            )
            # Prefer explicit loaded flag
            if hasattr(adapter, "_model"):
                loaded = adapter._model is not None
            elif key.startswith("fake") or type(adapter).__name__.startswith("Fake"):
                loaded = enabled and key not in self._errors

            if not enabled:
                availability = ModelAvailability.DISABLED.value
            elif key in self._errors:
                availability = ModelAvailability.UNAVAILABLE.value
            elif loaded:
                availability = ModelAvailability.AVAILABLE.value
            else:
                availability = ModelAvailability.NOT_LOADED.value

            caps = [c.value if hasattr(c, "value") else str(c) for c in adapter.capabilities]
            statuses.append(
                ModelStatus(
                    key=key,
                    model_id=adapter.model_id,
                    capabilities=caps,
                    availability=availability,
                    device=getattr(adapter, "device", "unknown"),
                    loaded=bool(loaded and availability == ModelAvailability.AVAILABLE.value),
                    load_duration_ms=getattr(adapter, "load_duration_ms", None),
                    error=self._errors.get(key),
                    purpose=self._purposes.get(key, ""),
                )
            )
        return statuses

    def get_runtime_capabilities(self) -> list[dict[str, Any]]:
        """Return runtime capability snapshots for all registered models."""
        results: list[dict[str, Any]] = []
        for status in self.status():
            adapter = self._adapters.get(status.key)
            vocab: list[str] = []
            if adapter:
                names_attr = getattr(adapter, "names", None) or (
                    getattr(adapter._model, "names", None) if hasattr(adapter, "_model") else None
                )
                if isinstance(names_attr, dict):
                    vocab = [str(v) for v in names_attr.values()]
                elif isinstance(names_attr, (list, tuple)):
                    vocab = [str(v) for v in names_attr]

            if not vocab and status.key in (ModelKey.YOLO26.value, ModelKey.FASTER_RCNN.value):
                from app.inference.adapters.yolo26 import DEFAULT_COCO_CLASSES
                vocab = list(DEFAULT_COCO_CLASSES.values())

            geo_types = [GeometryType.BOX.value]
            if "segmentation" in status.capabilities or status.key == ModelKey.SAM2.value:
                geo_types = [GeometryType.POLYGON.value, "mask"]
            elif "classification" in status.capabilities or status.key == ModelKey.CLIP.value:
                geo_types = [GeometryType.CLASSIFICATION.value]

            results.append({
                "model_key": status.key,
                "model_id": status.model_id,
                "available": status.availability in (ModelAvailability.AVAILABLE.value, ModelAvailability.NOT_LOADED.value),
                "loaded": status.loaded,
                "capabilities": status.capabilities,
                "vocabulary": vocab,
                "is_open_vocabulary": ModelKey.DINO.value == status.key
                or ModelKey.SAM2.value == status.key
                or ModelKey.CLIP.value == status.key
                or ModelKey.FLORENCE.value == status.key,
                "geometry_types": geo_types,
                "purpose": status.purpose,
            })
        return results

    def predict_detections(
        self,
        key: str,
        image_path: Path,
        *,
        asset_id: str,
        labels: list[str] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> list[NormalizedDetection]:
        adapter = self.get(key)
        if not self.try_load(key):
            raise ModelUnavailableError(
                self._errors.get(key, f"Model {key} unavailable"),
                details={"model_key": key},
            )
        options = dict(execution_options or {})
        requested_threshold = options.get("confidence_threshold")
        configured_default = float(getattr(adapter, "confidence_threshold", 0.25))
        threshold = resolve_confidence_threshold(
            key,
            requested_threshold,
            configured_default,
        )
        logger.info(
            "model_threshold_resolution",
            requested_threshold=threshold["requested_threshold"],
            effective_threshold=threshold["effective_threshold"],
            threshold_source=threshold["threshold_source"],
            threshold_clamped=threshold["threshold_clamped"],
            clamp_reason=threshold["clamp_reason"],
            model=key,
            strategy=options.get("strategy", "full_image"),
            asset_id=asset_id,
            execution_id=options.get("execution_id"),
        )
        try:
            image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
        except OSError:
            image_hash = None
        inference_lock = self._inference_locks.setdefault(key, threading.Lock())
        with inference_lock:
            logger.info(
                "model_input_identity",
                execution_id=options.get("execution_id"),
                model_key=key,
                asset_id=asset_id,
                image_path=str(image_path),
                image_name=image_path.name,
                image_sha256=image_hash,
                labels=labels or [],
            )
            if key == ModelKey.YOLO26.value:
                yolo_options = dict(options)
                yolo_options.pop("confidence_threshold", None)
                detections = cast(
                    list[NormalizedDetection],
                    adapter.predict(
                        image_path,
                        asset_id=asset_id,
                        labels=labels,
                        confidence_threshold=threshold["effective_threshold"],
                        **yolo_options,
                    ),
                )
            elif key in {ModelKey.FASTER_RCNN.value, ModelKey.DINO.value}:
                adapter_options = {
                    "confidence_threshold": threshold["effective_threshold"],
                }
                detections = cast(
                    list[NormalizedDetection],
                    adapter.predict(
                        image_path,
                        asset_id=asset_id,
                        labels=labels,
                        **adapter_options,
                    ),
                )
            else:
                detections = cast(
                    list[NormalizedDetection],
                    adapter.predict(image_path, asset_id=asset_id, labels=labels),
                )

        execution_id = options.get("execution_id")
        foreign = [
            det for det in detections
            if str(getattr(det, "asset_id", "") or "") != str(asset_id)
        ]
        if foreign:
            logger.error(
                "execution_result_identity_mismatch",
                current_asset_id=asset_id,
                result_asset_ids=list({str(getattr(det, "asset_id", "") or "") for det in foreign}),
                current_execution_id=execution_id,
                result_execution_ids=list({str((getattr(det, "provenance", {}) or {}).get("execution_id") or "") for det in foreign}),
                model=key,
                job_id=options.get("job_id"),
                job_item_id=options.get("job_item_id"),
            )
            raise RuntimeError(
                f"Model {key} returned {len(foreign)} detection(s) for a different asset; "
                f"expected asset_id={asset_id!r}"
            )

        if execution_id:
            rebound: list[NormalizedDetection] = []
            for det in detections:
                provenance = dict(getattr(det, "provenance", {}) or {})
                result_execution_id = provenance.get("execution_id")
                if result_execution_id and str(result_execution_id) != str(execution_id):
                    logger.error(
                        "execution_result_identity_mismatch",
                        current_asset_id=asset_id,
                        result_asset_id=getattr(det, "asset_id", None),
                        current_execution_id=execution_id,
                        result_execution_id=result_execution_id,
                        model=key,
                        job_id=options.get("job_id"),
                        job_item_id=options.get("job_item_id"),
                    )
                    raise RuntimeError(
                        f"Model {key} returned a result for execution_id={result_execution_id!r}; "
                        f"expected execution_id={execution_id!r}"
                    )
                provenance["execution_id"] = str(execution_id)
                rebound.append(replace(det, provenance=provenance))
            detections = rebound
        logger.info(
            "model_result_identity",
            execution_id=options.get("execution_id"),
            model_key=key,
            asset_id=asset_id,
            image_path=str(image_path),
            image_sha256=image_hash,
            detection_count=len(detections),
            boxes=[
                (
                    getattr(det, "bbox").model_dump()
                    if hasattr(getattr(det, "bbox", None), "model_dump")
                    else list(getattr(det, "bbox", ()))
                    if isinstance(getattr(det, "bbox", None), (list, tuple))
                    else str(getattr(det, "bbox", None))
                )
                for det in detections[:5]
            ],
            confidences=[getattr(det, "confidence", None) for det in detections[:5]],
        )
        from app.inference.detection_quality import log_detection_score_trace
        log_detection_score_trace(
            "image_detection_score_trace",
            detections,
            stage="raw_model",
            asset_id=asset_id,
            execution_id=execution_id,
            model_key=key,
            effective_threshold=threshold["effective_threshold"],
            score_semantics="native_model_confidence",
        )
        return detections

    def classify_regions(
        self,
        key: str,
        image_path: Path,
        *,
        asset_id: str,
        regions: list[tuple[str | None, Any]],
        text_labels: list[str],
    ) -> list[NormalizedClassification]:
        adapter = self.get(key)
        if not self.try_load(key):
            raise ModelUnavailableError(
                self._errors.get(key, f"Model {key} unavailable"),
                details={"model_key": key},
            )
        inference_lock = self._inference_locks.setdefault(key, threading.Lock())
        with inference_lock:
            return cast(
                list[NormalizedClassification],
                adapter.classify_regions(
                    image_path, asset_id=asset_id, regions=regions, text_labels=text_labels
                ),
            )


class InferenceRuntime:
    """Dedicated inference boundary used by the batch worker and API."""

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry
        import os
        logger.info(
            "inference_runtime_created",
            registry_id=registry.registry_id,
            process_id=os.getpid(),
            enabled_models=[key for key, enabled in registry._enabled.items() if enabled],
        )

    def model_statuses(self) -> list[ModelStatus]:
        return self.registry.status()

    def load_eager(self) -> None:
        self.registry.load_eager()

    def load_enabled(self) -> None:
        self.registry.load_enabled()

    def detect(
        self,
        model_key: str,
        image_path: Path,
        *,
        asset_id: str,
        labels: list[str] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> list[NormalizedDetection]:
        return self.registry.predict_detections(
            model_key,
            image_path,
            asset_id=asset_id,
            labels=labels,
            execution_options=execution_options,
        )

    def classify(
        self,
        model_key: str,
        image_path: Path,
        *,
        asset_id: str,
        regions: list[tuple[str | None, Any]],
        text_labels: list[str],
    ) -> list[NormalizedClassification]:
        return self.registry.classify_regions(
            model_key, image_path, asset_id=asset_id, regions=regions, text_labels=text_labels
        )


_runtime: InferenceRuntime | None = None


def get_runtime() -> InferenceRuntime:
    if _runtime is None:
        raise ModelUnavailableError("Inference runtime not initialized")
    return _runtime


def set_runtime(runtime: InferenceRuntime | None) -> None:
    global _runtime
    _runtime = runtime


def create_registry_from_settings(
    settings: Settings,
    *,
    force_fake: bool = False,
) -> ModelRegistry:
    """Build registry. Fake adapters are opt-in for tests only."""
    registry = ModelRegistry()
    use_fake = (
        force_fake
        or getattr(settings, "force_fake", False)
        or os.getenv("FORCE_FAKE", "").lower() in ("1", "true", "yes")
        or os.getenv("USE_MOCK_MODELS", "").lower() in ("1", "true", "yes")
    )

    if use_fake:
        yolo_enabled = settings.yolo26_enabled or use_fake
        faster_rcnn_enabled = settings.faster_rcnn_enabled or use_fake
        dino_enabled = settings.dino_enabled or use_fake
        florence_enabled = settings.florence_enabled or use_fake
        sam2_enabled = settings.sam2_enabled or use_fake
        clip_enabled = settings.clip_enabled or use_fake

        registry.register(
            ModelKey.YOLO26.value,
            FakeYoloAdapter(model_id=settings.yolo26_model_id),
            enabled=yolo_enabled,
        )
        fake_rcnn = FakeYoloAdapter(model_id=settings.faster_rcnn_model_id)
        fake_rcnn.key = ModelKey.FASTER_RCNN.value
        registry.register(
            ModelKey.FASTER_RCNN.value,
            fake_rcnn,
            enabled=faster_rcnn_enabled,
        )
        registry.register(
            ModelKey.DINO.value,
            FakeDinoAdapter(model_id=settings.dino_model_id),
            enabled=dino_enabled,
        )
        registry.register(
            ModelKey.FLORENCE.value,
            FakeFlorenceAdapter(model_id=settings.florence_model_id),
            enabled=florence_enabled,
        )
        registry.register(
            ModelKey.SAM2.value,
            FakeSam2Adapter(model_id=settings.sam2_model_id),
            enabled=sam2_enabled,
        )
        registry.register(
            ModelKey.CLIP.value,
            FakeClipAdapter(model_id=settings.clip_model_id),
            enabled=clip_enabled,
        )
        registry.register(
            ModelKey.TRACKER.value,
            TrackerAdapter(model_id="tracker_fake"),
            enabled=True,
        )
        registry.register(
            ModelKey.GLINER.value,
            GlinerAdapter(model_id="gliner_fake"),
            enabled=True,
        )
        registry.register(
            ModelKey.QWEN3_EMBEDDING.value,
            QwenEmbeddingAdapter(model_id="qwen3_embedding_fake"),
            enabled=True,
        )
        registry.register(
            ModelKey.QWEN3_RERANKER.value,
            QwenRerankerAdapter(model_id="qwen3_reranker_fake"),
            enabled=True,
        )
        registry.register(
            ModelKey.PADDLEOCR.value,
            PaddleOcrAdapter(model_id="paddleocr_fake"),
            enabled=True,
        )
        return registry

    # Real adapters — DINO/Florence/SAM2 registered in later milestones;
    # for now register YOLO for real and stubs that report unavailable until wired.
    yolo = Yolo26Adapter(
        model_id=settings.yolo26_model_id,
        weights_path=settings.resolve_yolo26_weights(),
        device_preference=settings.device,
        confidence_threshold=settings.yolo_confidence_threshold,
    )
    registry.register(ModelKey.YOLO26.value, yolo, enabled=settings.yolo26_enabled)

    faster_rcnn = FasterRCNNAdapter(
        model_id=settings.faster_rcnn_model_id,
        device_preference=settings.device,
        confidence_threshold=settings.faster_rcnn_confidence_threshold,
    )
    registry.register(
        ModelKey.FASTER_RCNN.value,
        faster_rcnn,
        enabled=settings.faster_rcnn_enabled,
    )

    dino = GroundingDinoAdapter(
        model_id=settings.dino_model_id,
        device_preference=settings.device,
        confidence_threshold=settings.dino_confidence_threshold,
        box_threshold=settings.dino_box_threshold,
        text_threshold=settings.dino_text_threshold,
        nms_threshold=settings.dino_nms_threshold,
        cache_dir=settings.model_cache_dir,
    )
    registry.register(ModelKey.DINO.value, dino, enabled=settings.dino_enabled)

    florence = FlorenceAdapter(
        model_id=settings.florence_model_id,
        device_preference=settings.device,
        cache_dir=settings.model_cache_dir,
    )
    registry.register(ModelKey.FLORENCE.value, florence, enabled=settings.florence_enabled)

    sam2 = Sam2Adapter(
        model_id=settings.sam2_model_id,
        weights_path=settings.resolve_sam2_weights(),
        device_preference=settings.device,
    )
    registry.register(ModelKey.SAM2.value, sam2, enabled=settings.sam2_enabled)

    clip = ClipAdapter(
        model_id=settings.clip_model_id,
        device_preference=settings.device,
        cache_dir=settings.model_cache_dir,
    )
    registry.register(ModelKey.CLIP.value, clip, enabled=settings.clip_enabled)

    tracker = TrackerAdapter(model_id="bytetrack_expert")
    registry.register(ModelKey.TRACKER.value, tracker, enabled=True)

    gliner = GlinerAdapter(model_id="gliner2_ner_expert")
    registry.register(ModelKey.GLINER.value, gliner, enabled=True)

    qwen_emb = QwenEmbeddingAdapter(model_id="qwen3_embedding_expert")
    registry.register(ModelKey.QWEN3_EMBEDDING.value, qwen_emb, enabled=True)

    qwen_rr = QwenRerankerAdapter(model_id="qwen3_reranker_expert")
    registry.register(ModelKey.QWEN3_RERANKER.value, qwen_rr, enabled=True)

    paddleocr = PaddleOcrAdapter(model_id="paddleocr_vl_layout_expert")
    registry.register(ModelKey.PADDLEOCR.value, paddleocr, enabled=True)

    return registry


# Keep for type checkers / accidental imports
class _UnavailableAdapter:  # pragma: no cover
    pass
