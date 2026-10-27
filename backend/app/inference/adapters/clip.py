"""CLIP adapter: zero-shot region/attribute classification via image-text similarity."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.errors import ModelUnavailableError, ValidationAppError
from app.inference.contracts import (
    BoundingBoxPercent,
    ModelCapability,
    ModelKey,
    NormalizedClassification,
)
from app.inference.device import resolve_device
from app.logging import get_logger

logger = get_logger(__name__)


def _crop_region(image: Any, region: BoundingBoxPercent) -> Any:
    width, height = image.size
    x0 = max(0, min(width, round(region.x / 100 * width)))
    y0 = max(0, min(height, round(region.y / 100 * height)))
    x1 = max(x0 + 1, min(width, round((region.x + region.w) / 100 * width)))
    y1 = max(y0 + 1, min(height, round((region.y + region.h) / 100 * height)))
    return image.crop((x0, y0, x1, y1))


class ClipAdapter:
    key = ModelKey.CLIP.value
    capabilities = [ModelCapability.CLASSIFICATION]

    def __init__(
        self,
        *,
        model_id: str = "openai/clip-vit-base-patch32",
        device_preference: str = "auto",
        cache_dir: Path | None = None,
    ) -> None:
        self.model_id = model_id
        self.device = resolve_device(device_preference)
        self.cache_dir = cache_dir
        self._model: Any | None = None
        self._processor: Any | None = None
        self.load_duration_ms: int | None = None
        self._loaded: bool = False

    def load(self) -> None:
        if getattr(self, "_loaded", False):
            return
        start = time.perf_counter()
        logger.info("model_load_start", model_key=self.key, model_id=self.model_id, device=self.device)
        try:
            from transformers import CLIPModel, CLIPProcessor
        except ImportError as exc:
            raise ModelUnavailableError(
                "transformers is required for CLIP",
                details={"hint": "uv pip install transformers"},
            ) from exc

        try:
            kwargs: dict[str, Any] = {}
            if self.cache_dir is not None:
                kwargs["cache_dir"] = str(self.cache_dir)
            self._processor = CLIPProcessor.from_pretrained(self.model_id, **kwargs)
            try:
                self._model = CLIPModel.from_pretrained(self.model_id, use_safetensors=True, **kwargs)
            except Exception:
                self._model = CLIPModel.from_pretrained(self.model_id, **kwargs)
            self._model.to(self.device)
            self._model.eval()
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(
                f"Failed to load CLIP {self.model_id}: {exc}",
                details={"model_id": self.model_id, "device": self.device},
            ) from exc

        self.load_duration_ms = int((time.perf_counter() - start) * 1000)
        self._loaded = True
        logger.info(
            "model_load_complete",
            model_key=self.key,
            model_id=self.model_id,
            device=self.device,
            duration_ms=self.load_duration_ms,
        )

    def classify_regions(
        self,
        image_path: Path,
        *,
        asset_id: str,
        regions: list[tuple[str | None, BoundingBoxPercent]],
        text_labels: list[str],
    ) -> list[NormalizedClassification]:
        """Scores each region against `text_labels`, returning ranked multi-label results."""
        if not text_labels:
            raise ValidationAppError("text_labels must not be empty", details={"asset_id": asset_id})

        if getattr(self, "_loaded", False):
            logger.info("model_reuse", model_key=self.key, registry_id=getattr(self, "registry_id", "unknown"))
        else:
            self.load()
        if self._model is None or self._processor is None:
            raise ModelUnavailableError(
                f"CLIP model {self.model_id} is not loaded or is unavailable.",
                details={
                    "model_id": self.model_id,
                    "device": self.device,
                },
            )

        import torch
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        crops = [_crop_region(image, region) for _, region in regions]

        inputs = self._processor(
            text=text_labels, images=crops, return_tensors="pt", padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model(**inputs)
            # Independent per-label sigmoid scores (not softmax) so multiple
            # labels can score highly for the same region — required for
            # multi-label / attribute tagging rather than single-class choice.
            probs = torch.sigmoid(outputs.logits_per_image).cpu().tolist()

        now = datetime.now(UTC)
        results: list[NormalizedClassification] = []
        for (annotation_id, _region), scores in zip(regions, probs, strict=True):
            ranked = sorted(zip(text_labels, scores, strict=True), key=lambda p: p[1], reverse=True)
            best_label, best_score = ranked[0]
            results.append(
                NormalizedClassification(
                    id=str(uuid4()),
                    asset_id=asset_id,
                    annotation_id=annotation_id,
                    label=best_label,
                    confidence=float(best_score),
                    taxonomy_path=None,
                    attributes={"candidates": [{"label": lbl, "score": float(s)} for lbl, s in ranked]},
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={"engine": "clip", "text_labels": text_labels},
                )
            )
        return results
