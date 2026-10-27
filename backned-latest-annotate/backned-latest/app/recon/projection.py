"""Deterministic 2D PCA projection for dataset map exploration."""

from __future__ import annotations

from typing import Any

import numpy as np


def project_embeddings_2d(
    asset_ids: list[str],
    vectors: np.ndarray,
) -> dict[str, tuple[float, float]]:
    """Project embedding vectors to 2D via centered PCA (SVD).

    Returns a map of asset_id -> (x, y) in roughly [-1, 1].
    Deterministic for a given input matrix. Exploration aid only.
    """
    n = len(asset_ids)
    if n == 0:
        return {}
    if vectors.ndim != 2 or vectors.shape[0] != n:
        raise ValueError("vectors must be (n, d) aligned with asset_ids")

    if n == 1:
        return {asset_ids[0]: (0.0, 0.0)}

    x = vectors.astype(np.float64)
    x = x - x.mean(axis=0, keepdims=True)
    # SVD: X = U S Vt; first two right singular vectors for scores
    try:
        _u, s, vt = np.linalg.svd(x, full_matrices=False)
    except np.linalg.LinAlgError:
        rng = np.random.default_rng(0)
        coords = rng.standard_normal((n, 2))
        coords -= coords.mean(axis=0)
        scale = float(np.abs(coords).max()) or 1.0
        coords /= scale
        return {aid: (float(coords[i, 0]), float(coords[i, 1])) for i, aid in enumerate(asset_ids)}

    k = min(2, vt.shape[0], x.shape[1])
    components = vt[:k].T  # (d, k)
    scores = x @ components  # (n, k)
    if k == 1:
        scores = np.column_stack([scores[:, 0], np.zeros(n)])

    # Stabilize sign so first non-zero loading is positive
    for j in range(2):
        col = scores[:, j]
        if col.size and float(col[np.argmax(np.abs(col))]) < 0:
            scores[:, j] *= -1.0

    scale = float(np.abs(scores).max()) or 1.0
    scores = scores / scale
    return {aid: (float(scores[i, 0]), float(scores[i, 1])) for i, aid in enumerate(asset_ids)}


def projection_summary(coords: dict[str, tuple[float, float]]) -> dict[str, Any]:
    return {
        "method": "pca",
        "point_count": len(coords),
        "bounds": {
            "x_min": min((c[0] for c in coords.values()), default=0.0),
            "x_max": max((c[0] for c in coords.values()), default=0.0),
            "y_min": min((c[1] for c in coords.values()), default=0.0),
            "y_max": max((c[1] for c in coords.values()), default=0.0),
        },
    }
