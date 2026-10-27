"""Dataset Reconnaissance orchestration service."""

from __future__ import annotations

import asyncio
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from app.db.firebase import AsyncIOMotorDatabase

from app.config import Settings
from app.db.models import MongoDoc
from app.domain.enums import AssetStatus, PlanStatus, ProjectStatus, ReconStatus, ReviewStatus
from app.domain.ontology_policy import (
    apply_recommendation_to_ontology,
    build_deterministic_recommendations,
    bump_revision,
    ensure_concept_ids,
    merge_nonstructural_into_approved,
    merge_recommendations,
    new_concept_id,
    normalize_evidence_fields,
    ontology_is_human_approved,
    rejected_fingerprints,
)
from app.errors import ModelUnavailableError, NotFoundError, ValidationAppError
from app.logging import get_logger
from app.recon.embeddings import embed_image_path, save_embedding
from app.recon.ontology import OntologyProposal, ProposedLabel
from app.recon.profiling import AssetProfile, dataset_stats, mark_duplicates
from app.recon.projection import project_embeddings_2d, projection_summary
from app.recon.quality import analyze_image_quality, build_quality_signals
from app.recon.structure import analyze_structure
from app.recon.validation import validate_labels
from app.services.images import ALLOWED_EXTENSIONS, decode_and_validate_image
from app.storage.files import FileStorage, normalize_filename

logger = get_logger(__name__)

_recon_tasks: dict[str, asyncio.Task[None]] = {}


async def shutdown_recon_tasks() -> None:
    """Cancel and await reconnaissance tasks before application resources close."""
    tasks = [task for task in _recon_tasks.values() if not task.done()]
    if tasks:
        logger.info("recon_tasks_cancel_started", active_tasks=len(tasks))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("recon_tasks_cancel_complete", active_tasks=len(tasks))
    _recon_tasks.clear()


class ReconService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        storage: FileStorage,
        agent_client: Any,
        db_factory: Callable[[], AsyncIOMotorDatabase] | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.storage = storage
        self.agent_client = agent_client
        self.db_factory = db_factory

    async def get_or_404(self, project_id: str) -> MongoDoc:
        row_doc = await self.db["project_recons"].find_one({"project_id": project_id})
        if row_doc is None:
            raise NotFoundError("Reconnaissance not found", details={"project_id": project_id})
        return MongoDoc(row_doc)

    async def get_status(self, project_id: str) -> dict[str, Any]:
        row_doc = await self.db["project_recons"].find_one({"project_id": project_id})
        if row_doc is None:
            return {
                "project_id": project_id,
                "status": "absent",
                "phase": "not_started",
                "error_message": "",
                "stats": {},
                "clusters": [],
                "sample_asset_ids": [],
                "proposed_labels": [],
                "clarifying_questions": [],
                "decisions": {},
                "finished_at": None,
            }
        return self._out(MongoDoc(row_doc))

    async def start(self, project_id: str) -> dict[str, Any]:
        project = await self.db["projects"].find_one({"id": project_id})
        if project is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        assets_cursor = self.db["assets"].find({"project_id": project_id})
        assets = [MongoDoc(d) async for d in assets_cursor]
        if not assets:
            raise ValidationAppError("Upload images before starting dataset reconnaissance")

        recon_doc = await self.db["project_recons"].find_one({"project_id": project_id})
        now = datetime.now(UTC)
        if recon_doc is None:
            recon_id = str(uuid.uuid4())
            row = MongoDoc({
                "id": recon_id,
                "project_id": project_id,
                "status": ReconStatus.RUNNING.value,
                "phase": "analyzing_dataset",
                "error_message": "",
                "finished_at": None,
                "created_at": now,
                "updated_at": now,
            })
            await self.db["project_recons"].insert_one(dict(row))
        else:
            row = MongoDoc(recon_doc)
            updates = {
                "status": ReconStatus.RUNNING.value,
                "phase": "analyzing_dataset",
                "error_message": "",
                "finished_at": None,
                "updated_at": now,
            }
            await self.db["project_recons"].update_one({"id": row.id}, {"$set": updates})
            row.update(updates)

        if self.db_factory is None:
            await self._run(project_id)
            return await self.get_status(project_id)

        existing = _recon_tasks.get(project_id)
        if existing and not existing.done():
            return await self.get_status(project_id)

        factory = self.db_factory
        settings = self.settings
        storage = self.storage
        client = self.agent_client

        async def _bg() -> None:
            db_instance = factory()
            svc = ReconService(db_instance, settings, storage, client, factory)
            await svc._run(project_id)

        _recon_tasks[project_id] = asyncio.create_task(_bg())
        return await self.get_status(project_id)

    async def apply_labels(
        self,
        project_id: str,
        labels: list[dict[str, Any]] | list[str],
    ) -> dict[str, Any]:
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        project = MongoDoc(project_doc)

        recon_doc = await self.db["project_recons"].find_one({"project_id": project_id})
        now = datetime.now(UTC)
        if recon_doc is None:
            recon_id = str(uuid.uuid4())
            recon = MongoDoc({
                "id": recon_id,
                "project_id": project_id,
                "status": ReconStatus.SUCCEEDED.value,
                "created_at": now,
                "updated_at": now,
            })
            await self.db["project_recons"].insert_one(dict(recon))
        else:
            recon = MongoDoc(recon_doc)

        rich: list[dict[str, Any]] = []
        flat: list[str] = []
        seen: set[str] = set()
        # Preserve existing rich fields when PATCH sends a partial label object
        existing_by_id: dict[str, dict[str, Any]] = {}
        existing_by_name: dict[str, dict[str, Any]] = {}
        for prev in ensure_concept_ids(list(project.get("label_ontology") or [])):
            if isinstance(prev, dict) and prev.get("name"):
                existing_by_name[str(prev["name"]).casefold()] = dict(prev)
                if prev.get("id"):
                    existing_by_id[str(prev["id"])] = dict(prev)
            elif isinstance(prev, str) and prev.strip():
                existing_by_name[prev.strip().casefold()] = {
                    "id": new_concept_id(),
                    "name": prev.strip(),
                    "definition": "",
                    "evidence_asset_ids": [],
                    "hard_negative_asset_ids": [],
                }

        id_renames: list[tuple[str, str, str]] = []  # (old_name, new_name, concept_id)

        for item in labels:
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    continue
                key = name.casefold()
                if key in seen:
                    raise ValidationAppError(
                        "Duplicate label names are not allowed",
                        details={"label": name},
                    )
                seen.add(key)
                flat.append(name)
                prior = existing_by_name.get(key, {})
                prior_approved = prior.get("approved") is True if isinstance(prior, dict) else False
                entry = normalize_evidence_fields(
                    {
                        **prior,
                        "id": prior.get("id") or new_concept_id(),
                        "name": name,
                        "definition": prior.get("definition") or "",
                        "evidence_asset_ids": list(prior.get("evidence_asset_ids") or []),
                        "hard_negative_asset_ids": list(prior.get("hard_negative_asset_ids") or []),
                        "approved": prior_approved,
                    }
                )
                rich.append(entry)
            else:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                key = name.casefold()
                if key in seen:
                    raise ValidationAppError(
                        "Duplicate label names are not allowed",
                        details={"label": name},
                    )
                seen.add(key)
                flat.append(name)
                prior_entry: dict[str, Any] = {}
                incoming_id = str(item.get("id") or "").strip()
                if incoming_id and incoming_id in existing_by_id:
                    prior_entry = existing_by_id[incoming_id]
                    old_name = str(prior_entry.get("name") or "")
                    if old_name and old_name != name:
                        id_renames.append((old_name, name, incoming_id))
                else:
                    prior_entry = existing_by_name.get(key, {})
                entry = {**prior_entry, **dict(item)}
                entry["name"] = name
                entry["id"] = prior_entry.get("id") or incoming_id or new_concept_id()
                for field in (
                    "definition",
                    "includes",
                    "excludes",
                    "aliases",
                    "relations",
                    "evidence_asset_ids",
                    "hard_negative_asset_ids",
                    "evidence_state",
                    "prevalence_estimate",
                    "validation",
                    "kind",
                    "id",
                ):
                    if field not in item and field in prior_entry:
                        entry[field] = prior_entry[field]
                incoming_approved = item.get("approved") if isinstance(item, dict) else None
                prior_approved = prior_entry.get("approved") is True if isinstance(prior_entry, dict) else False
                entry["approved"] = incoming_approved if incoming_approved is not None else prior_approved
                if "source" not in entry:
                    entry["source"] = prior_entry.get("source") or "recon"
                rich.append(normalize_evidence_fields(entry))

        old_labels = list(project.get("labels") or [])
        # Prefer id-stable renames; fall back to cardinality heuristics.
        rename_pairs: list[tuple[str, str]] = [(a, b) for a, b, _ in id_renames]
        if not rename_pairs:
            removed = [n for n in old_labels if n not in flat]
            added = [n for n in flat if n not in old_labels]
            if removed and len(removed) == len(added):
                if len(old_labels) == len(flat):
                    for old_name, new_name in zip(old_labels, flat, strict=True):
                        if old_name != new_name and old_name in removed and new_name in added:
                            rename_pairs.append((old_name, new_name))
                if not rename_pairs:
                    rename_pairs = list(zip(removed, added, strict=True))
        if rename_pairs:
            asset_ids_cursor = self.db["assets"].find({"project_id": project_id}, {"id": 1})
            asset_ids = [d.get("id") async for d in asset_ids_cursor]
            if asset_ids:
                for old_name, new_name in rename_pairs:
                    await self.db["annotations"].update_many(
                        {"asset_id": {"$in": asset_ids}, "label": old_name},
                        {"$set": {"label": new_name}}
                    )

        bump_revision(
            project,
            actor="human",
            kind="apply_labels",
            summary=f"Human applied ontology policy ({len(flat)} concepts).",
            concept_ids=[str(x.get("id")) for x in rich if x.get("id")],
        )
        # Refresh recommendations against the approved policy.
        rejected = rejected_fingerprints(project.get("ontology_recommendations"))
        fresh = build_deterministic_recommendations(rich, rejected_fingerprints=rejected)
        merged_recs = merge_recommendations(
            project.get("ontology_recommendations"),
            fresh,
        )

        await self.db["projects"].update_one(
            {"id": project_id},
            {"$set": {
                "labels": flat,
                "label_ontology": rich,
                "ontology_recommendations": merged_recs,
                "revision": project.get("revision"),
                "revision_history": project.get("revision_history"),
                "updated_at": now,
            }}
        )

        await self.db["project_recons"].update_one(
            {"id": recon.id},
            {"$set": {"proposed_labels": rich, "updated_at": now}}
        )

        logger.info("labels_saved", project_id=project_id, labels=len(flat))
        logger.info("ontology_save", project_id=project_id, labels=len(flat))

        # Build / update plan for approval
        plan_doc = await self.db["project_plans"].find_one({"project_id": project_id})
        recon_stats = recon.get("stats") or {}
        summary_text = recon_stats.get("summary") if isinstance(recon_stats, dict) else None
        if not summary_text:
            summary_text = f"Suggested labels from dataset reconnaissance ({len(flat)} labels)."
        workflow = [
            {"key": "yolo26", "purpose": "Primary object detection", "required": True},
            {"key": "dino", "purpose": "Open-vocab coverage", "required": False},
        ]
        questions = recon.get("clarifying_questions")
        decisions = recon.get("decisions") or {}
        p_status = PlanStatus.AWAITING_CLARIFICATION.value if (questions and not decisions) else PlanStatus.PENDING_APPROVAL.value

        if plan_doc is None:
            plan_id = str(uuid.uuid4())
            plan = MongoDoc({
                "id": plan_id,
                "project_id": project_id,
                "taxonomy": flat,
                "summary": summary_text,
                "workflow": workflow,
                "status": p_status,
                "clarifications": dict(decisions),
                "created_at": now,
                "updated_at": now,
            })
            await self.db["project_plans"].insert_one(dict(plan))
        else:
            plan = MongoDoc(plan_doc)
            updates = {
                "taxonomy": flat,
                "summary": summary_text,
                "status": p_status,
                "clarifications": dict(decisions),
                "updated_at": now,
            }
            if not plan.get("workflow"):
                updates["workflow"] = workflow
            await self.db["project_plans"].update_one({"id": plan.id}, {"$set": updates})

        return await self.get_status(project_id)

    async def decide_recommendation(
        self,
        project_id: str,
        recommendation_id: str,
        *,
        accept: bool,
    ) -> dict[str, Any]:
        """Accept or reject an ontology recommendation (structural changes only on accept)."""
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        project = MongoDoc(project_doc)

        recs = list(project.get("ontology_recommendations") or [])
        idx = next((i for i, r in enumerate(recs) if isinstance(r, dict) and r.get("id") == recommendation_id), None)
        if idx is None:
            raise NotFoundError(
                "Recommendation not found",
                details={"recommendation_id": recommendation_id},
            )
        rec = dict(recs[idx])
        if rec.get("status") != "pending":
            raise ValidationAppError(
                "Recommendation already decided",
                details={"status": rec.get("status")},
            )
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        if accept:
            ontology = ensure_concept_ids(list(project.get("label_ontology") or []))
            # Capture rename before apply for annotation remap
            old_by_id = {str(x.get("id")): str(x.get("name")) for x in ontology if x.get("id")}
            updated = apply_recommendation_to_ontology(ontology, rec)
            new_by_id = {str(x.get("id")): str(x.get("name")) for x in updated if x.get("id")}
            rename_pairs = [
                (old_by_id[cid], new_by_id[cid])
                for cid in (rec.get("concept_ids") or [])
                if cid in old_by_id and cid in new_by_id and old_by_id[cid] != new_by_id[cid]
            ]
            if rename_pairs:
                asset_ids_cursor = self.db["assets"].find({"project_id": project_id}, {"id": 1})
                asset_ids = [d.get("id") async for d in asset_ids_cursor]
                for old_name, new_name in rename_pairs:
                    await self.db["annotations"].update_many(
                        {"asset_id": {"$in": asset_ids}, "label": old_name},
                        {"$set": {"label": new_name}}
                    )
            for entry in updated:
                entry["approved"] = True
            rec["status"] = "accepted"
            rec["decided_at"] = now
            recs[idx] = rec
            bump_revision(
                project,
                actor="recommendation",
                kind=str(rec.get("type") or "recommendation"),
                summary=f"Accepted recommendation: {rec.get('type')} — {rec.get('rationale', '')[:120]}",
                concept_ids=[str(x) for x in (rec.get("concept_ids") or [])],
            )
            await self.db["projects"].update_one(
                {"id": project_id},
                {"$set": {
                    "label_ontology": updated,
                    "labels": [str(x.get("name")) for x in updated if x.get("name")],
                    "ontology_recommendations": recs,
                    "revision": project.get("revision"),
                    "revision_history": project.get("revision_history"),
                    "updated_at": now_dt,
                }}
            )
        else:
            rec["status"] = "rejected"
            rec["decided_at"] = now
            recs[idx] = rec
            bump_revision(
                project,
                actor="human",
                kind="reject_recommendation",
                summary=f"Rejected recommendation: {rec.get('type')}",
                concept_ids=[str(x) for x in (rec.get("concept_ids") or [])],
            )
            await self.db["projects"].update_one(
                {"id": project_id},
                {"$set": {
                    "ontology_recommendations": recs,
                    "revision": project.get("revision"),
                    "revision_history": project.get("revision_history"),
                    "updated_at": now_dt,
                }}
            )

        from app.services.projects import ProjectService
        return await ProjectService(self.db, self.settings, self.storage).get(project_id)

    async def apply_decisions(self, project_id: str, answers: dict[str, str]) -> dict[str, Any]:
        recon = await self.get_or_404(project_id)
        merged = dict(recon.get("decisions") or {})
        merged.update(answers)
        now = datetime.now(UTC)

        updates: dict[str, Any] = {"decisions": merged, "updated_at": now}
        if recon.get("status") == ReconStatus.AWAITING_DECISION.value:
            updates["status"] = ReconStatus.SUCCEEDED.value
            updates["phase"] = "preparing_suggested_labels"

        await self.db["project_recons"].update_one({"id": recon.id}, {"$set": updates})

        plan_doc = await self.db["project_plans"].find_one({"project_id": project_id})
        if plan_doc is not None:
            await self.db["project_plans"].update_one(
                {"id": plan_doc.get("id")},
                {"$set": {
                    "clarifications": merged,
                    "status": PlanStatus.PENDING_APPROVAL.value,
                    "updated_at": now,
                }}
            )
        return await self.get_status(project_id)

    async def _run(self, project_id: str) -> None:
        try:
            await self._run_inner(project_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("recon_failed", project_id=project_id)
            await self.db["project_recons"].update_one(
                {"project_id": project_id},
                {"$set": {
                    "status": ReconStatus.FAILED.value,
                    "phase": "failed",
                    "error_message": str(exc),
                    "finished_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }}
            )

    async def _run_inner(self, project_id: str) -> None:
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            return
        project = MongoDoc(project_doc)

        recon_doc = await self.db["project_recons"].find_one({"project_id": project_id})
        if recon_doc is None:
            return
        row = MongoDoc(recon_doc)

        assets_cursor = self.db["assets"].find({"project_id": project_id})
        assets = [MongoDoc(d) async for d in assets_cursor]

        # Expand any uploaded ZIP archives into image AssetRows (idempotent)
        await self._expand_zip_archives(project_id, assets)

        # Re-fetch assets to include any newly created image assets from ZIPs
        assets_cursor = self.db["assets"].find({"project_id": project_id})
        assets = [MongoDoc(d) async for d in assets_cursor]

        # Phase 1: profiling / duplicates
        now = datetime.now(UTC)
        await self.db["project_recons"].update_one(
            {"id": row.id},
            {"$set": {"phase": "analyzing_dataset", "updated_at": now}}
        )

        profiles: list[AssetProfile] = []
        for asset in assets:
            profiles.append(
                AssetProfile(
                    asset_id=asset.id,
                    filename=asset.get("filename"),
                    content_type=asset.get("content_type"),
                    format=asset.get("image_format"),
                    width=asset.get("width"),
                    height=asset.get("height"),
                    aspect_ratio=asset.get("aspect_ratio"),
                    orientation=asset.get("orientation") or 1,
                    byte_size=asset.get("byte_size"),
                    content_hash=asset.get("content_hash"),
                    perceptual_hash=asset.get("perceptual_hash"),
                    decode_error=asset.get("decode_error"),
                )
            )
        profiles = mark_duplicates(profiles)
        by_id = {p.asset_id: p for p in profiles}
        for asset in assets:
            p = by_id[asset.id]
            is_dup = 1 if p.is_duplicate else 0
            dup_of = p.duplicate_of_asset_id
            await self.db["assets"].update_one(
                {"id": asset.id},
                {"$set": {"is_duplicate": is_dup, "duplicate_of_asset_id": dup_of}}
            )
            asset["is_duplicate"] = is_dup
            asset["duplicate_of_asset_id"] = dup_of
        stats = dataset_stats(profiles)
        await self.db["project_recons"].update_one(
            {"id": row.id},
            {"$set": {"stats": stats, "updated_at": datetime.now(UTC)}}
        )

        # Phase 2: embeddings
        await self.db["project_recons"].update_one(
            {"id": row.id},
            {"$set": {"phase": "finding_visual_groups", "updated_at": datetime.now(UTC)}}
        )

        force_fake = self.settings.skip_model_load or not self.settings.embedding_enabled
        vectors = []
        embed_ids: list[str] = []
        embedding_paths: dict[str, Path] = {}
        image_paths: dict[str, Path] = {}
        modality = project.get("modality") or "image"

        import numpy as np

        for asset in assets:
            if asset.get("is_duplicate"):
                continue

            path = self.storage.resolve(asset.get("storage_path"))
            vec = None

            if modality == "image":
                if not asset.get("image_format"):
                    continue
                image_paths[asset.id] = path
                vec = embed_image_path(path, settings=self.settings, force_fake=force_fake)
            elif modality == "video":
                # Video: extract middle frame as preview and run embedding
                import cv2
                cap = cv2.VideoCapture(str(path))
                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    await self.db["assets"].update_one(
                        {"id": asset.id},
                        {"$set": {"width": width, "height": height}}
                    )

                    middle_idx = max(0, frame_count // 2)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, middle_idx)
                    ret, frame = cap.read()
                    if ret:
                        preview_path = self.storage.asset_dir(project_id, asset.id) / "preview.jpg"
                        preview_path.parent.mkdir(parents=True, exist_ok=True)
                        cv2.imwrite(str(preview_path), frame)
                        rel_prev = self.storage.relative_path(preview_path)
                        await self.db["assets"].update_one(
                            {"id": asset.id},
                            {"$set": {"preview_path": rel_prev}}
                        )
                        image_paths[asset.id] = preview_path
                        vec = embed_image_path(preview_path, settings=self.settings, force_fake=force_fake)
                    cap.release()
                if vec is None:
                    vec = np.zeros(32, dtype=np.float32)
            elif modality in {"text", "document"}:
                text_snippet = ""
                try:
                    text_snippet = path.read_text(encoding="utf-8", errors="ignore")[:2000]
                except Exception:
                    text_snippet = asset.get("filename") or ""

                from app.inference.adapters.multimodal_experts import QwenEmbeddingAdapter
                adapter = QwenEmbeddingAdapter()
                vec = adapter.embed_text(text_snippet)

            if vec is not None:
                emb_dir = self.storage.asset_dir(project_id, asset.id)
                emb_path = emb_dir / "embedding.npy"
                save_embedding(vec, emb_path)
                rel = self.storage.relative_path(emb_path)
                await self.db["assets"].update_one(
                    {"id": asset.id},
                    {"$set": {"embedding_path": rel}}
                )
                embedding_paths[asset.id] = emb_path
                vectors.append(vec)
                embed_ids.append(asset.id)

        matrix = np.stack(vectors) if vectors else np.zeros((0, 32), dtype=np.float32)
        structure = analyze_structure(
            embed_ids,
            matrix,
            max_sample=self.settings.recon_max_sample,
            outlier_quota=self.settings.recon_outlier_quota,
        )
        label_map = {
            aid: structure["labels"][i]
            for i, aid in enumerate(embed_ids)
            if i < len(structure["labels"])
        }
        outliers = set(structure.get("outliers") or [])
        coords = project_embeddings_2d(embed_ids, matrix) if embed_ids else {}
        # Place exact duplicates near their canonical asset
        for asset in assets:
            updates: dict[str, Any] = {}
            if asset.id in label_map:
                updates["cluster_id"] = int(label_map[asset.id])
            updates["is_outlier"] = 1 if asset.id in outliers else 0
            if asset.id in coords:
                updates["map_x"], updates["map_y"] = coords[asset.id]
            elif asset.get("is_duplicate") and asset.get("duplicate_of_asset_id") in coords:
                cx, cy = coords[asset.get("duplicate_of_asset_id")]
                jitter = (abs(hash(asset.id)) % 1000) / 10000.0
                updates["map_x"] = cx + 0.02 + jitter * 0.01
                updates["map_y"] = cy + 0.02 + jitter * 0.01
            else:
                updates["map_x"] = None
                updates["map_y"] = None

            if updates:
                await self.db["assets"].update_one({"id": asset.id}, {"$set": updates})

        clusters_val = structure.get("clusters") or []
        sample_ids_val = structure.get("sample_asset_ids") or []
        row["clusters"] = clusters_val
        row["sample_asset_ids"] = sample_ids_val

        # Cheap quality proxies (Pillow) for dataset health
        per_quality: dict[str, dict[str, Any]] = {}
        for asset in assets:
            if asset.get("decode_error"):
                continue
            if modality != "image":
                per_quality[asset.id] = {
                    "blurriness": 0.0,
                    "contrast": 1.0,
                    "brightness": 0.5,
                    "noise": 0.0,
                }
                continue
            path = self.storage.resolve(asset.get("storage_path"))
            per_quality[asset.id] = analyze_image_quality(
                path,
                width=asset.get("width"),
                height=asset.get("height"),
                aspect_ratio=asset.get("aspect_ratio"),
            )
        quality_signals = build_quality_signals(
            profiles=list(stats.get("profiles") or []),
            per_asset_quality=per_quality,
            outlier_ids=list(structure.get("outliers") or []),
            clusters=list(clusters_val),
        )
        stats = {
            **stats,
            "projection": projection_summary(coords),
            "quality_signals": quality_signals,
            "per_asset_quality": per_quality,
        }
        await self.db["project_recons"].update_one(
            {"id": row.id},
            {"$set": {
                "clusters": clusters_val,
                "sample_asset_ids": sample_ids_val,
                "stats": stats,
                "updated_at": datetime.now(UTC),
            }}
        )

        # Phase 3: ontology proposal
        await self.db["project_recons"].update_one(
            {"id": row.id},
            {"$set": {"phase": "preparing_suggested_labels", "updated_at": datetime.now(UTC)}}
        )

        sample_meta = []
        for aid in sample_ids_val:
            asset = next((a for a in assets if a.id == aid), None)
            if asset is None:
                continue
            sample_meta.append(
                {
                    "asset_id": aid,
                    "filename": asset.get("filename"),
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "cluster_id": asset.get("cluster_id"),
                    "is_outlier": bool(asset.get("is_outlier")),
                    "format": asset.get("image_format"),
                }
            )

        recon_context = {
            "project_name": project.get("name"),
            "goal": project.get("goal") or None,
            "task_type": project.get("task_type"),
            "modality": modality,
            "stats": {
                k: v
                for k, v in stats.items()
                if k != "profiles"
            },
            "clusters": clusters_val,
            "sample_images": sample_meta,
            "outliers": structure.get("outliers") or [],
        }

        agent_images = []
        images_sent = 0
        if self.settings.agent_send_images and not force_fake and not self.settings.skip_model_load and modality in {"image", "video"}:
            from app.agent.multimodal import load_agent_images, select_agent_image_ids

            selected_ids = select_agent_image_ids(
                recon_context,
                max_images=min(self.settings.agent_max_images, self.settings.recon_max_sample),
            )
            agent_images = load_agent_images(selected_ids, image_paths)
            images_sent = len(agent_images)
            logger.info(
                "recon_agent_images_prepared",
                project_id=project_id,
                selected=len(selected_ids),
                loaded=images_sent,
            )

        client_to_use = self.agent_client
        if not getattr(self.agent_client, "available", True):
            reason = getattr(self.agent_client, "reason", "unknown")
            logger.error("vertex_agent_unavailable_in_recon", project_id=project_id, reason=reason)
            raise ModelUnavailableError(
                f"Vertex AI agent is unavailable: {reason}",
                details={"project_id": project_id, "reason": reason, "auth": "ADC"},
            )

        propose = getattr(client_to_use, "propose_ontology", None)
        proposal = None
        usage = None
        try:
            if callable(propose):
                try:
                    proposal, usage = propose(recon_context=recon_context, images=agent_images)
                except TypeError:
                    proposal, usage = propose(recon_context=recon_context)
                images_sent = max(images_sent, int(getattr(usage, "images_sent", 0) or 0))
            else:
                labels_hint: list[str] = []
                result, usage = client_to_use.intake(
                    name=project.get("name"),
                    goal=project.get("goal") or "Discover labels from dataset structure",
                    task_type=project.get("task_type"),
                    strategy=project.get("label_strategy"),
                    labels=labels_hint,
                )
                proposal = OntologyProposal(
                    summary=result.summary,
                    proposed_labels=[
                        ProposedLabel(name=n, definition=f"Suggested label: {n}")
                        for n in result.proposed_labels
                    ],
                    needs_decision=result.needs_clarification,
                    clarifying_questions=result.clarifying_questions,
                    recommended_models=result.recommended_models,
                    risks=result.risks,
                    review_policy_notes=result.review_policy_notes,
                    label_strategy=result.label_strategy,
                )
        except Exception as exc:
            logger.error(
                "ontology_suggestion_generation_failed",
                project_id=project_id,
                error=str(exc),
            )
            raise

        if modality in {"image", "video"}:
            validated = validate_labels(
                proposal.proposed_labels,
                asset_ids=embed_ids,
                embedding_paths=embedding_paths,
                image_paths=image_paths,
                settings=self.settings,
                force_fake=force_fake,
            )
            proposal.proposed_labels = validated

        # Persist agent usage if possible
        try:
            from app.agent.pricing import PRICING_VERSION, estimate_cost_usd
            from app.domain.enums import AgentRequestKind

            tokens_in = getattr(usage, "tokens_in", 0) or 0
            tokens_out = getattr(usage, "tokens_out", 0) or 0
            model_id = getattr(usage, "model_id", "") or ""
            cost = estimate_cost_usd(tokens_in=tokens_in, tokens_out=tokens_out)
            req_id = str(uuid.uuid4())
            await self.db["agent_requests"].insert_one({
                "id": req_id,
                "project_id": project_id,
                "kind": AgentRequestKind.ONTOLOGY.value,
                "model_id": model_id,
                "request_context": {
                    "recon": True,
                    "images_sent": images_sent > 0,
                    "image_count": images_sent,
                },
                "response_payload": proposal.model_dump(),
                "clarifying_questions": [q.model_dump() for q in proposal.clarifying_questions],
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd_estimate": cost,
                "pricing_version": PRICING_VERSION,
                "created_at": datetime.now(UTC),
            })
            await self.db["usage_events"].insert_one({
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "kind": "llm",
                "model_id": model_id,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost,
                "created_at": datetime.now(UTC),
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("recon_usage_persist_failed", error=str(exc))

        proposed_rich = ensure_concept_ids(
            [
                normalize_evidence_fields(
                    {
                        **lab.model_dump(),
                        "source": "recon",
                        "approved": False,
                    }
                )
                for lab in proposal.proposed_labels
            ]
        )

        plan_doc = await self.db["project_plans"].find_one({"project_id": project_id})
        plan_approved = bool(plan_doc and plan_doc.get("status") == PlanStatus.APPROVED.value)
        human_approved = ontology_is_human_approved(
            list(project.get("label_ontology") or []),
            plan_approved=plan_approved,
        )

        if human_approved:
            # Preserve human-controlled structure; store proposal for comparison only.
            approved = ensure_concept_ids(list(project.get("label_ontology") or []))
            updated_ont = merge_nonstructural_into_approved(approved, proposed_rich)
            labels_val = [str(x.get("name")) for x in updated_ont if x.get("name")]
            rejected = rejected_fingerprints(project.get("ontology_recommendations"))
            fresh = build_deterministic_recommendations(
                updated_ont,
                rejected_fingerprints=rejected,
            )
            # Also surface structural diffs as recommendations (add concept).
            approved_names = {str(x.get("name", "")).casefold() for x in approved}
            for prop in proposed_rich:
                pname = str(prop.get("name") or "").strip()
                if not pname or pname.casefold() in approved_names:
                    continue
                from app.domain.ontology_policy import recommendation_fingerprint

                proposal_body = {
                    "type": "new_concept",
                    "name": pname,
                    "definition": prop.get("definition") or "",
                    "includes": prop.get("includes") or "",
                    "excludes": prop.get("excludes") or "",
                    "aliases": list(prop.get("aliases") or []),
                }
                fp = recommendation_fingerprint(
                    rec_type="new_concept",
                    concept_ids=[],
                    proposal=proposal_body,
                )
                if fp not in rejected:
                    fresh.append(
                        {
                            "id": new_concept_id(),
                            "type": "new_concept",
                            "concept_ids": [],
                            "proposal": proposal_body,
                            "rationale": (
                                f"Recon suggests adding '{pname}' based on dataset evidence; "
                                "structure stays unchanged until you accept."
                            ),
                            "evidence_asset_ids": list(prop.get("evidence_asset_ids") or [])[:4],
                            "impact": "Would add a new concept to the approved ontology.",
                            "status": "pending",
                            "fingerprint": fp,
                            "created_at": datetime.now(UTC).isoformat(),
                            "decided_at": None,
                        }
                    )
            merged_recs = merge_recommendations(
                project.get("ontology_recommendations"),
                fresh,
            )
            await self.db["projects"].update_one(
                {"id": project_id},
                {"$set": {
                    "label_ontology": updated_ont,
                    "labels": labels_val,
                    "ontology_recommendations": merged_recs,
                    "updated_at": datetime.now(UTC),
                }}
            )
            project["label_ontology"] = updated_ont
            project["labels"] = labels_val
        else:
            labels_val = [lab.name for lab in proposal.proposed_labels]
            rejected = rejected_fingerprints(project.get("ontology_recommendations"))
            fresh = build_deterministic_recommendations(
                proposed_rich,
                rejected_fingerprints=rejected,
            )
            merged_recs = merge_recommendations(
                project.get("ontology_recommendations"),
                fresh,
            )
            proj_updates: dict[str, Any] = {
                "labels": labels_val,
                "label_ontology": proposed_rich,
                "ontology_recommendations": merged_recs,
                "updated_at": datetime.now(UTC),
            }
            if proposal.label_strategy:
                proj_updates["label_strategy"] = proposal.label_strategy
            await self.db["projects"].update_one({"id": project_id}, {"$set": proj_updates})
            project["labels"] = labels_val

        from app.agent.multimodal import filter_workflow_steps

        raw_workflow = [m.model_dump() for m in proposal.recommended_models] or [
            {"key": "yolo26", "purpose": "Primary object detection", "required": True},
            {"key": "dino", "purpose": "Open-vocab coverage", "required": False},
        ]
        wf = filter_workflow_steps(
            raw_workflow,
            florence_enabled=self.settings.florence_enabled,
            sam2_enabled=self.settings.sam2_enabled,
            task_type=project.get("task_type"),
        )
        if not wf:
            wf = [
                {"key": "yolo26", "purpose": "Primary object detection", "required": True},
                {"key": "dino", "purpose": "Open-vocab coverage", "required": False},
            ]
        from app.inference.ontology_map import build_ontology_index
        from app.inference.routing import ensure_detection_workflow

        ont_index = build_ontology_index(
            list(project.get("labels") or []),
            ontology=list(project.get("label_ontology") or []),
        )
        wf = ensure_detection_workflow(
            wf,
            ont_index,
            dino_enabled=self.settings.dino_enabled,
            yolo_enabled=self.settings.yolo26_enabled,
        )
        if project.get("task_type") == "segmentation" and not any(
            (step.get("key") if isinstance(step, dict) else None) == "sam2"
            for step in wf
        ):
            wf = list(wf) + [{"key": "sam2", "purpose": "Mask refinement", "required": True}]

        p_status = (
            PlanStatus.AWAITING_CLARIFICATION.value
            if (proposal.needs_decision and proposal.clarifying_questions)
            else PlanStatus.PENDING_APPROVAL.value
        )
        r_status = (
            ReconStatus.AWAITING_DECISION.value
            if (proposal.needs_decision and proposal.clarifying_questions)
            else ReconStatus.SUCCEEDED.value
        )
        r_phase = "decision_needed" if (proposal.needs_decision and proposal.clarifying_questions) else "preparing_suggested_labels"

        plan_data = {
            "project_id": project_id,
            "summary": proposal.summary,
            "taxonomy": project.get("labels"),
            "label_strategy": project.get("label_strategy"),
            "workflow": wf,
            "risks": proposal.risks,
            "rationale": proposal.review_policy_notes,
            "agent_model_id": getattr(usage, "model_id", ""),
            "review_policy": {
                "auto_approve_threshold": 0.95,
                "sample_rate": 0.1,
                "notes": proposal.review_policy_notes,
            },
            "status": p_status,
            "updated_at": datetime.now(UTC),
        }
        if plan_doc is None:
            plan_data["id"] = str(uuid.uuid4())
            plan_data["created_at"] = datetime.now(UTC)
            await self.db["project_plans"].insert_one(plan_data)
        else:
            await self.db["project_plans"].update_one({"id": plan_doc.get("id")}, {"$set": plan_data})

        new_recon_stats = {
            **stats,
            "summary": proposal.summary,
            "risks": proposal.risks,
            "review_policy_notes": proposal.review_policy_notes,
            "profiles": stats.get("profiles"),
        }
        await self.db["project_recons"].update_one(
            {"id": row.id},
            {"$set": {
                "proposed_labels": proposed_rich,
                "clarifying_questions": [q.model_dump() for q in proposal.clarifying_questions],
                "stats": new_recon_stats,
                "status": r_status,
                "phase": r_phase,
                "finished_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }}
        )

        await self.db["projects"].update_one(
            {"id": project_id},
            {"$set": {"status": ProjectStatus.READY.value, "updated_at": datetime.now(UTC)}}
        )
        logger.info(
            "recon_complete",
            project_id=project_id,
            labels=len(proposal.proposed_labels),
            status=r_status,
        )

    def _out(self, row: MongoDoc) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "project_id": row.get("project_id"),
            "status": row.get("status"),
            "phase": row.get("phase"),
            "error_message": row.get("error_message"),
            "stats": {
                k: v
                for k, v in (row.get("stats") or {}).items()
                if k not in {"profiles", "per_asset_quality"}
            },
            "clusters": row.get("clusters") or [],
            "sample_asset_ids": row.get("sample_asset_ids") or [],
            "proposed_labels": row.get("proposed_labels") or [],
            "clarifying_questions": row.get("clarifying_questions") or [],
            "decisions": row.get("decisions") or {},
            "finished_at": row.get("finished_at"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def _expand_zip_archives(self, project_id: str, assets: list[MongoDoc]) -> None:
        """Safely expand ZIP assets into image AssetRows. Idempotent via marker file."""
        for asset in assets:
            fname = str(asset.get("filename") or "")
            if not fname.lower().endswith(".zip"):
                continue
            try:
                marker = self.storage.asset_dir(project_id, asset.id) / ".expanded"
            except Exception:
                marker = None
            if marker is not None and marker.exists():
                continue
            try:
                zpath = self.storage.resolve(asset.get("storage_path"))
                with zipfile.ZipFile(zpath, "r") as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        inner_name = info.filename
                        safe_name = normalize_filename(inner_name)
                        suffix = "." + safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
                        if suffix not in ALLOWED_EXTENSIONS:
                            logger.info("zip_skip_unsupported_file", asset_id=asset.id, filename=fname, child=inner_name)
                            continue
                        try:
                            data = zf.read(info.filename)
                        except Exception as exc:  # noqa: BLE001
                            logger.info("zip_read_failed", asset_id=asset.id, filename=fname, child=inner_name, error=str(exc))
                            continue
                        if len(data) == 0 or len(data) > int(self.settings.max_image_upload_mb * 1024 * 1024):
                            logger.info("zip_skip_size", asset_id=asset.id, filename=fname, child=inner_name, size=len(data))
                            continue
                        try:
                            decoded = decode_and_validate_image(
                                data,
                                filename=safe_name,
                                content_type=None,
                                max_bytes=int(self.settings.max_image_upload_mb * 1024 * 1024),
                                allowed_types=self.settings.allowed_content_types,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.info("zip_skip_invalid_image", asset_id=asset.id, filename=fname, child=inner_name, reason=str(exc))
                            continue

                        now = datetime.now(UTC)
                        new_asset_id = str(uuid.uuid4())
                        new_asset = MongoDoc({
                            "id": new_asset_id,
                            "project_id": project_id,
                            "filename": safe_name,
                            "content_type": decoded.content_type,
                            "width": decoded.width,
                            "height": decoded.height,
                            "storage_path": "",
                            "byte_size": len(decoded.data),
                            "status": AssetStatus.UPLOADED.value,
                            "review_status": ReviewStatus.PENDING.value,
                            "content_hash": decoded.content_hash,
                            "perceptual_hash": decoded.perceptual_hash,
                            "aspect_ratio": decoded.aspect_ratio,
                            "orientation": decoded.orientation,
                            "image_format": decoded.format,
                            "created_at": now,
                            "updated_at": now,
                        })
                        path = self.storage.write_bytes(project_id, new_asset_id, safe_name, decoded.data)
                        new_asset["storage_path"] = self.storage.relative_path(path)
                        try:
                            from app.services.images import write_jpeg_preview
                            preview_path = self.storage.asset_dir(project_id, new_asset_id) / "preview.jpg"
                            write_jpeg_preview(decoded.data, preview_path)
                            new_asset["preview_path"] = self.storage.relative_path(preview_path)
                        except Exception:
                            pass
                        await self.db["assets"].insert_one(dict(new_asset))
            except zipfile.BadZipFile:
                logger.warning("zip_expand_failed", asset_id=asset.id, filename=fname, reason="bad_zip")
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("zip_expand_failed", asset_id=asset.id, filename=fname, reason=str(exc))
                continue
            try:
                if marker is not None:
                    self.storage.write_bytes(project_id, asset.id, ".expanded", b"1")
            except Exception:
                pass
