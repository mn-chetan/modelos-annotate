"""Cheap local image quality proxies for dataset health signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps

# Thresholds tuned for local exploration (not scientific QA scores)
SMALL_MIN_SIDE = 96
SMALL_PIXELS = 20_000
EXTREME_ASPECT_LOW = 0.28
EXTREME_ASPECT_HIGH = 3.6
BLUR_LAPLACIAN_MAX = 18.0
UNDEREXPOSE_MEAN = 38.0
OVEREXPOSE_MEAN = 225.0


def _load_rgb(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img) or img
            return img.convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def laplacian_variance(gray: Image.Image) -> float:
    """Approximate focus via variance of a Laplacian-like high-pass."""
    edges = gray.filter(ImageFilter.FIND_EDGES)
    arr = np.asarray(edges, dtype=np.float32)
    return float(arr.var())


def mean_luma(rgb: Image.Image) -> float:
    gray = rgb.convert("L")
    arr = np.asarray(gray, dtype=np.float32)
    return float(arr.mean()) if arr.size else 128.0


def analyze_image_quality(
    path: Path,
    *,
    width: int,
    height: int,
    aspect_ratio: float | None,
) -> dict[str, Any]:
    """Return boolean flags and raw proxies for one image."""
    flags: dict[str, Any] = {
        "unusually_small": False,
        "extreme_aspect": False,
        "likely_blur": False,
        "underexposed": False,
        "overexposed": False,
        "blur_var": None,
        "mean_luma": None,
    }
    w, h = int(width or 0), int(height or 0)
    if w > 0 and h > 0:
        flags["unusually_small"] = min(w, h) < SMALL_MIN_SIDE or (w * h) < SMALL_PIXELS
        ar = aspect_ratio if aspect_ratio and aspect_ratio > 0 else (w / h if h else 1.0)
        flags["extreme_aspect"] = ar < EXTREME_ASPECT_LOW or ar > EXTREME_ASPECT_HIGH

    rgb = _load_rgb(path)
    if rgb is None:
        return flags

    # Downscale for speed
    sample = rgb.copy()
    sample.thumbnail((256, 256), Image.Resampling.BILINEAR)
    gray = sample.convert("L")
    blur_var = laplacian_variance(gray)
    luma = mean_luma(sample)
    flags["blur_var"] = blur_var
    flags["mean_luma"] = luma
    flags["likely_blur"] = blur_var < BLUR_LAPLACIAN_MAX
    flags["underexposed"] = luma < UNDEREXPOSE_MEAN
    flags["overexposed"] = luma > OVEREXPOSE_MEAN
    return flags


def build_quality_signals(
    *,
    profiles: list[dict[str, Any]],
    per_asset_quality: dict[str, dict[str, Any]],
    outlier_ids: list[str],
    clusters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate actionable health signals (counts + asset ids + copy)."""
    exact_dups = [p["asset_id"] for p in profiles if p.get("is_duplicate")]
    near_dups: list[str] = []
    for p in profiles:
        if p.get("near_duplicate_of"):
            near_dups.append(p["asset_id"])
    decode_errs = [p["asset_id"] for p in profiles if p.get("decode_error")]

    small = [aid for aid, q in per_asset_quality.items() if q.get("unusually_small")]
    extreme = [aid for aid, q in per_asset_quality.items() if q.get("extreme_aspect")]
    blur = [aid for aid, q in per_asset_quality.items() if q.get("likely_blur")]
    under = [aid for aid, q in per_asset_quality.items() if q.get("underexposed")]
    over = [aid for aid, q in per_asset_quality.items() if q.get("overexposed")]
    rare_members: list[str] = []
    for c in clusters:
        if c.get("is_rare"):
            rare_members.extend(c.get("member_asset_ids") or [])

    def _sig(
        key: str,
        title: str,
        asset_ids: list[str],
        action_label: str = "Review images",
    ) -> dict[str, Any] | None:
        ids = list(dict.fromkeys(asset_ids))
        if not ids:
            return None
        return {
            "key": key,
            "title": title,
            "count": len(ids),
            "asset_ids": ids,
            "action_label": action_label,
        }

    signals: list[dict[str, Any]] = []
    for item in [
        _sig(
            "exact_duplicates",
            f"{len(exact_dups)} exact duplicate image{'s' if len(exact_dups) != 1 else ''} found",
            exact_dups,
            "Review duplicates",
        ),
        _sig(
            "near_duplicates",
            f"{len(near_dups)} image{'s' if len(near_dups) != 1 else ''} look nearly identical",
            near_dups,
            "Review near duplicates",
        ),
        _sig(
            "decode_errors",
            f"{len(decode_errs)} image{'s' if len(decode_errs) != 1 else ''} failed to decode cleanly",
            decode_errs,
            "Inspect failed images",
        ),
        _sig(
            "unusually_small",
            f"{len(small)} image{'s' if len(small) != 1 else ''} may be too small to annotate reliably",
            small,
        ),
        _sig(
            "extreme_aspect",
            f"{len(extreme)} image{'s' if len(extreme) != 1 else ''} have extreme aspect ratios",
            extreme,
        ),
        _sig(
            "likely_blur",
            f"{len(blur)} image{'s' if len(blur) != 1 else ''} may be too blurred to annotate reliably",
            blur,
        ),
        _sig(
            "underexposed",
            f"{len(under)} image{'s' if len(under) != 1 else ''} look underexposed",
            under,
        ),
        _sig(
            "overexposed",
            f"{len(over)} image{'s' if len(over) != 1 else ''} look overexposed",
            over,
        ),
        _sig(
            "embedding_outliers",
            f"{len(outlier_ids)} visual outlier{'s' if len(outlier_ids) != 1 else ''} stand apart from nearby groups",
            outlier_ids,
            "Review outliers",
        ),
        _sig(
            "rare_clusters",
            f"{len(rare_members)} image{'s' if len(rare_members) != 1 else ''} sit in rare visual groups",
            rare_members,
            "Review rare groups",
        ),
    ]:
        if item is not None:
            signals.append(item)
    return signals
