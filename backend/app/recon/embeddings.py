"""Local visual embeddings for dataset structure (not user-visible vendors)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)

_model: Any = None
_processor: Any = None
_model_id_loaded: str | None = None


def _load_clip(model_id: str) -> tuple[Any, Any]:
    global _model, _processor, _model_id_loaded
    if _model is not None and _model_id_loaded == model_id:
        return _model, _processor
    from transformers import CLIPModel, CLIPProcessor

    logger.info("loading_embedding_model", model_id=model_id)
    _processor = CLIPProcessor.from_pretrained(model_id)
    _model = CLIPModel.from_pretrained(model_id)
    _model.eval()
    _model_id_loaded = model_id
    return _model, _processor


def embed_image_path(
    path: Path,
    *,
    settings: Settings,
    force_fake: bool = False,
) -> np.ndarray:
    """Return L2-normalized embedding vector."""
    if force_fake or settings.skip_model_load or not settings.embedding_enabled:
        # Deterministic pseudo-embedding from path bytes for tests / CPU doubles
        rng = np.random.default_rng(abs(hash(path.name)) % (2**32))
        vec = rng.standard_normal(32).astype(np.float32)
        vec /= max(float(np.linalg.norm(vec)), 1e-8)
        return vec

    import torch

    model, processor = _load_clip(settings.embedding_model_id)
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img) or img
        img = img.convert("RGB")
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():
        feats = model.get_image_features(**inputs)
        vec = feats[0].cpu().numpy().astype(np.float32)
    vec /= max(float(np.linalg.norm(vec)), 1e-8)
    return vec


def embed_text(
    text: str,
    *,
    settings: Settings,
    force_fake: bool = False,
    dim: int = 32,
) -> np.ndarray:
    """Return L2-normalized text embedding aligned with image embeddings."""
    query = " ".join((text or "").strip().lower().split())
    if force_fake or settings.skip_model_load or not settings.embedding_enabled:
        # Deterministic vector from normalized query tokens (stable for tests)
        seed = abs(hash(query or "empty")) % (2**32)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(dim).astype(np.float32)
        # Mix in per-token influence so related phrases stay somewhat near
        for token in query.split():
            t_rng = np.random.default_rng(abs(hash(token)) % (2**32))
            vec += 0.35 * t_rng.standard_normal(dim).astype(np.float32)
        vec /= max(float(np.linalg.norm(vec)), 1e-8)
        return vec

    import torch

    model, processor = _load_clip(settings.embedding_model_id)
    inputs = processor(text=[query or "image"], return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        feats = model.get_text_features(**inputs)
        vec = feats[0].cpu().numpy().astype(np.float32)
    vec /= max(float(np.linalg.norm(vec)), 1e-8)
    return vec


def save_embedding(vec: np.ndarray, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.save(dest, vec)
    return dest


def load_embedding(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    return np.load(path).astype(np.float32)
