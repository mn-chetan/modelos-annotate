"""Dataset intelligence workspace aggregations (map, search, health, coverage)."""

from __future__ import annotations

from typing import Any

import numpy as np
from app.db.firebase import AsyncIOMotorDatabase

from app.config import Settings
from app.db.models import MongoDoc
from app.domain.enums import ReviewStatus
from app.errors import NotFoundError, ValidationAppError
from app.recon.embeddings import embed_text, load_embedding
from app.storage.files import FileStorage
from app.context import get_current_base_prefix


class DatasetService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        storage: FileStorage,
    ) -> None:
        self.db = db
        self.settings = settings
        self.storage = storage

    async def _project(self, project_id: str) -> MongoDoc:
        row = await self.db["projects"].find_one({"id": project_id})
        if row is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        return MongoDoc(row)

    async def _recon(self, project_id: str) -> MongoDoc | None:
        row = await self.db["project_recons"].find_one({"project_id": project_id})
        return MongoDoc(row) if row else None

    async def _assets(self, project_id: str) -> list[MongoDoc]:
        cursor = self.db["assets"].find({"project_id": project_id})
        return [MongoDoc(d) async for d in cursor]

    async def map_points(self, project_id: str) -> dict[str, Any]:
        await self._project(project_id)
        assets = await self._assets(project_id)
        points: list[dict[str, Any]] = []
        missing = 0
        for row in assets:
            if row.get("map_x") is None or row.get("map_y") is None:
                missing += 1
                continue
            prefix = get_current_base_prefix()
            preview = (
                f"{prefix}/api/v1/assets/{row.id}/preview"
                if row.get("preview_path")
                else f"{prefix}/api/v1/assets/{row.id}/image"
            )
            points.append(
                {
                    "asset_id": row.id,
                    "filename": row.get("filename"),
                    "x": row.get("map_x"),
                    "y": row.get("map_y"),
                    "cluster_id": row.get("cluster_id"),
                    "review_status": row.get("review_status"),
                    "is_outlier": bool(row.get("is_outlier", False)),
                    "is_duplicate": bool(row.get("is_duplicate", False)),
                    "duplicate_of_asset_id": row.get("duplicate_of_asset_id"),
                    "mean_confidence": row.get("mean_confidence"),
                    "preview_url": preview,
                }
            )
        recon = await self._recon(project_id)
        return {
            "project_id": project_id,
            "points": points,
            "point_count": len(points),
            "assets_without_coords": missing,
            "clusters": (recon.get("clusters") if recon else []) or [],
            "projection": ((recon.get("stats") or {}).get("projection") if recon else None),
        }

    async def search(
        self,
        project_id: str,
        *,
        query: str,
        limit: int = 24,
        neighbor_count: int = 5,
    ) -> dict[str, Any]:
        await self._project(project_id)
        q = (query or "").strip()
        if not q:
            raise ValidationAppError("Search query is required")
        limit = max(1, min(int(limit), 100))
        neighbor_count = max(0, min(int(neighbor_count), 12))

        assets = await self._assets(project_id)
        force_fake = self.settings.skip_model_load or not self.settings.embedding_enabled
        query_vec = embed_text(q, settings=self.settings, force_fake=force_fake)

        scored: list[tuple[float, MongoDoc, np.ndarray]] = []
        for row in assets:
            emb_path = row.get("embedding_path")
            if not emb_path:
                continue
            vec = load_embedding(self.storage.resolve(emb_path))
            if vec is None:
                continue
            # Align dims for fake/real mismatches
            a = query_vec
            b = vec.astype(np.float32)
            if a.shape[0] != b.shape[0]:
                d = min(a.shape[0], b.shape[0])
                a = a[:d]
                b = b[:d]
                a = a / max(float(np.linalg.norm(a)), 1e-8)
                b = b / max(float(np.linalg.norm(b)), 1e-8)
            score = float(np.dot(a, b))
            scored.append((score, row, b))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:limit]

        # Precompute neighbor graph among embedded assets (by embedding cosine)
        results: list[dict[str, Any]] = []
        for score, row, vec in top:
            neighbors: list[dict[str, Any]] = []
            if neighbor_count and scored:
                nbrs = sorted(
                    (
                        (float(np.dot(vec, other_vec)), other)
                        for s, other, other_vec in scored
                        if other.id != row.id
                    ),
                    key=lambda t: t[0],
                    reverse=True,
                )[:neighbor_count]
                neighbors = [
                    {"asset_id": other.id, "score": round(ns, 4), "filename": other.get("filename")}
                    for ns, other in nbrs
                ]
            prefix = get_current_base_prefix()
            preview = (
                f"{prefix}/api/v1/assets/{row.id}/preview"
                if row.get("preview_path")
                else f"{prefix}/api/v1/assets/{row.id}/image"
            )
            results.append(
                {
                    "asset_id": row.id,
                    "filename": row.get("filename"),
                    "score": round(score, 4),
                    "cluster_id": row.get("cluster_id"),
                    "review_status": row.get("review_status"),
                    "preview_url": preview,
                    "neighbors": neighbors,
                }
            )

        return {
            "project_id": project_id,
            "query": q,
            "results": results,
            "result_count": len(results),
            "note": "Scores are similarity-ranked closest visual matches, not calibrated confidence.",
        }

    async def health(self, project_id: str) -> dict[str, Any]:
        await self._project(project_id)
        recon = await self._recon(project_id)
        signals: list[dict[str, Any]] = []
        if recon and isinstance(recon.get("stats"), dict):
            signals = list(recon.get("stats", {}).get("quality_signals") or [])
        return {
            "project_id": project_id,
            "signals": signals,
            "signal_count": len(signals),
            "recon_status": recon.get("status") if recon else "absent",
        }

    async def coverage(self, project_id: str) -> dict[str, Any]:
        await self._project(project_id)
        recon = await self._recon(project_id)
        assets = await self._assets(project_id)
        total = len(assets) or 1
        clusters = list((recon.get("clusters") if recon else []) or [])

        # "reviewed" for coverage = approved or flagged (human disposition)
        disposition = {ReviewStatus.APPROVED.value, ReviewStatus.FLAGGED.value}
        open_statuses = {ReviewStatus.PENDING.value, ReviewStatus.REVIEW.value}

        by_cluster: dict[int | None, list[MongoDoc]] = {}
        for a in assets:
            by_cluster.setdefault(a.get("cluster_id"), []).append(a)

        cluster_rows: list[dict[str, Any]] = []
        summaries: list[str] = []
        for c in clusters:
            cid = c.get("cluster_id")
            members = by_cluster.get(cid, [])
            if not members and c.get("member_asset_ids"):
                member_set = set(c["member_asset_ids"])
                members = [a for a in assets if a.id in member_set]
            size = len(members) or int(c.get("size") or 0)
            reviewed = sum(1 for a in members if a.get("review_status") in disposition)
            flagged = sum(1 for a in members if a.get("review_status") == ReviewStatus.FLAGGED.value)
            pending = sum(1 for a in members if a.get("review_status") in open_statuses)
            confs = [a.get("mean_confidence") for a in members if a.get("mean_confidence") is not None]
            avg_conf = float(sum(confs) / len(confs)) if confs else None

            # Label distribution from annotations on cluster members
            label_counts: dict[str, int] = {}
            if members:
                member_ids = [a.id for a in members]
                agg = self.db["annotations"].aggregate([
                    {"$match": {"asset_id": {"$in": member_ids}}},
                    {"$group": {"_id": "$label", "count": {"$sum": 1}}},
                ])
                async for item in agg:
                    if item.get("_id"):
                        label_counts[str(item["_id"])] = int(item["count"])

            share = size / total
            reviewed_share = (reviewed / size) if size else 0.0
            row = {
                "cluster_id": cid,
                "size": size,
                "dataset_share": round(share, 4),
                "reviewed_count": reviewed,
                "reviewed_proportion": round(reviewed_share, 4),
                "pending_count": pending,
                "flagged_count": flagged,
                "flagged_rate": round((flagged / size) if size else 0.0, 4),
                "avg_detector_confidence": round(avg_conf, 4) if avg_conf is not None else None,
                "label_distribution": label_counts,
                "is_rare": bool(c.get("is_rare")),
                "medoid_asset_id": c.get("medoid_asset_id"),
                "member_asset_ids": [a.id for a in members] or list(c.get("member_asset_ids") or []),
            }
            cluster_rows.append(row)

            if share >= 0.08 and reviewed_share <= 0.15 and size >= 2:
                summaries.append(
                    f"Cluster {cid} represents {share:.0%} of the dataset "
                    f"but only {reviewed_share:.0%} has been reviewed."
                )
            elif c.get("is_rare") and pending:
                summaries.append(
                    f"Rare cluster {cid} still has {pending} image"
                    f"{'s' if pending != 1 else ''} needing attention."
                )

        if not summaries and cluster_rows:
            under = min(cluster_rows, key=lambda r: r["reviewed_proportion"])
            if under["size"] >= 2 and under["reviewed_proportion"] < 0.5:
                summaries.append(
                    f"Cluster {under['cluster_id']} is least covered "
                    f"({under['reviewed_proportion']:.0%} reviewed)."
                )

        overall_reviewed = sum(1 for a in assets if a.get("review_status") in disposition)
        return {
            "project_id": project_id,
            "asset_count": len(assets),
            "reviewed_count": overall_reviewed,
            "reviewed_proportion": round(overall_reviewed / total, 4),
            "clusters": cluster_rows,
            "summaries": summaries,
        }

