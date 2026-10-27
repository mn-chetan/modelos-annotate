"""Embedding clustering, medoids, outliers, and diversity-aware sampling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class ClusterInfo:
    cluster_id: int
    size: int
    medoid_asset_id: str
    member_asset_ids: list[str]
    is_rare: bool = False


def _kmeans(vectors: np.ndarray, k: int, *, seed: int = 0, iters: int = 25) -> np.ndarray:
    n = vectors.shape[0]
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)
    centroids = vectors[rng.choice(n, size=k, replace=False)].copy()
    labels = np.zeros(n, dtype=np.int32)
    for _ in range(iters):
        dists = ((vectors[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        labels = dists.argmin(axis=1).astype(np.int32)
        for i in range(k):
            members = vectors[labels == i]
            if len(members):
                centroids[i] = members.mean(axis=0)
    return labels


def choose_k(n: int) -> int:
    if n <= 1:
        return 1
    if n <= 8:
        return min(3, n)
    if n <= 40:
        return min(6, n)
    return min(12, max(4, int(np.sqrt(n))))


def analyze_structure(
    asset_ids: list[str],
    vectors: np.ndarray,
    *,
    max_sample: int = 24,
    outlier_quota: int = 4,
) -> dict[str, Any]:
    n = len(asset_ids)
    if n == 0:
        return {
            "clusters": [],
            "outliers": [],
            "sample_asset_ids": [],
            "labels": [],
            "distances_to_centroid": {},
        }
    if vectors.ndim != 2 or vectors.shape[0] != n:
        raise ValueError("vectors must be (n, d) aligned with asset_ids")

    k = choose_k(n)
    labels = _kmeans(vectors, k)
    clusters: list[ClusterInfo] = []
    distances: dict[str, float] = {}

    for cid in range(k):
        idxs = np.where(labels == cid)[0]
        if len(idxs) == 0:
            continue
        members = vectors[idxs]
        centroid = members.mean(axis=0)
        d = np.linalg.norm(members - centroid, axis=1)
        medoid_local = int(d.argmin())
        medoid_idx = int(idxs[medoid_local])
        member_ids = [asset_ids[i] for i in idxs.tolist()]
        for local_i, global_i in enumerate(idxs.tolist()):
            distances[asset_ids[global_i]] = float(d[local_i])
        clusters.append(
            ClusterInfo(
                cluster_id=cid,
                size=len(member_ids),
                medoid_asset_id=asset_ids[medoid_idx],
                member_asset_ids=member_ids,
                is_rare=len(member_ids) <= max(1, n // (k * 3)),
            )
        )

    # outliers: top distance within each cluster, then global
    outlier_ids: list[str] = []
    for c in clusters:
        ranked = sorted(
            ((distances[aid], aid) for aid in c.member_asset_ids),
            reverse=True,
        )
        if ranked and ranked[0][0] > 0:
            # take farthest if above median * 1.5 within cluster
            vals = [distances[aid] for aid in c.member_asset_ids]
            med = float(np.median(vals))
            for dist, aid in ranked[:2]:
                if dist >= med * 1.4 and aid not in outlier_ids:
                    outlier_ids.append(aid)

    outlier_ids = outlier_ids[:outlier_quota]

    # Diversity-aware sample: medoids first, then rare clusters, then outliers
    sample: list[str] = []
    for c in sorted(clusters, key=lambda c: (-c.is_rare, -c.size)):
        if c.medoid_asset_id not in sample:
            sample.append(c.medoid_asset_id)
        if len(sample) >= max_sample - outlier_quota:
            break
    for aid in outlier_ids:
        if aid not in sample and len(sample) < max_sample:
            sample.append(aid)
    # fill remaining slots from underrepresented clusters
    for c in clusters:
        for aid in c.member_asset_ids:
            if aid not in sample and len(sample) < max_sample:
                sample.append(aid)
            if len(sample) >= max_sample:
                break

    return {
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "medoid_asset_id": c.medoid_asset_id,
                "member_asset_ids": c.member_asset_ids,
                "is_rare": c.is_rare,
            }
            for c in clusters
        ],
        "outliers": outlier_ids,
        "sample_asset_ids": sample,
        "labels": labels.tolist(),
        "distances_to_centroid": distances,
    }
