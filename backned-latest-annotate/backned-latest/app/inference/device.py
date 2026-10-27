"""Device resolution and geometry helpers."""

from __future__ import annotations

from typing import Any
from app.inference.contracts import BoundingBoxPercent
from app.logging import get_logger

logger = get_logger(__name__)
_accelerator_logged = False


def get_accelerator_diagnostics(preference: str = "auto") -> dict[str, Any]:
    cuda_avail = False
    cuda_count = 0
    cuda_ver = None
    mps_avail = False
    try:
        import torch

        cuda_avail = bool(torch.cuda.is_available())
        cuda_count = torch.cuda.device_count() if hasattr(torch.cuda, "device_count") else 0
        cuda_ver = getattr(torch.version, "cuda", None)
        mps_avail = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    except Exception:
        pass

    resolved = preference
    reason = f"Using configured preference: {preference}"
    if preference == "auto":
        if cuda_avail:
            resolved = "cuda"
            reason = f"CUDA GPU detected ({cuda_count} devices, CUDA {cuda_ver})"
        elif mps_avail:
            resolved = "mps"
            reason = "Apple Silicon MPS detected"
        else:
            resolved = "cpu"
            reason = "No CUDA GPU or MPS accelerator available in PyTorch runtime; falling back to CPU"

    return {
        "requested_device": preference,
        "resolved_device": resolved,
        "cuda_available": cuda_avail,
        "cuda_device_count": cuda_count,
        "cuda_version": cuda_ver,
        "mps_available": mps_avail,
        "reason": reason,
    }


def resolve_device(preference: str) -> str:
    global _accelerator_logged
    diag = get_accelerator_diagnostics(preference)
    if not _accelerator_logged:
        _accelerator_logged = True
        logger.info("accelerator_diagnostics", **diag)
    return diag["resolved_device"]


def clamp_box(x: float, y: float, w: float, h: float) -> BoundingBoxPercent:
    x = max(0.0, min(100.0, x))
    y = max(0.0, min(100.0, y))
    w = max(0.0, min(100.0 - x, w))
    h = max(0.0, min(100.0 - y, h))
    return BoundingBoxPercent(x=x, y=y, w=w, h=h)
