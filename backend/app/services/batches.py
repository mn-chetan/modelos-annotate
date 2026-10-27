"""Batch creation, progress, and job item lifecycle backed by MongoDB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
import traceback

from app.api.schemas import BatchCreate
from app.config import Settings
from app.db.models import MongoDoc, to_mongo_doc, to_mongo_docs, get_database, _uuid, _utcnow
from app.domain.enums import AssetStatus, BatchStatus, JobItemStatus, PlanStatus, ProjectStatus
from app.errors import NotFoundError, ValidationAppError
from app.logging import get_logger

logger = get_logger(__name__)


def resolve_execution_context(project: Any) -> tuple[str, str]:
    """Resolve the persisted project modality and task for batch authorization."""
    read = project.get if isinstance(project, dict) else lambda key, default=None: getattr(project, key, default)
    raw_modality = str(read("modality", "") or read("media_format", "") or "").strip().lower()
    raw_task = str(read("task_type", "") or "").strip()
    if not raw_task:
        annotation_types = read("annotation_types", []) or []
        raw_task = str(annotation_types[0] if isinstance(annotation_types, list) and annotation_types else "")

    normalized_task = raw_task.upper().replace(" ", "_")
    text_tasks = {
        "NER", "ENTITY_EXTRACTION", "SENTIMENT", "SENTIMENT_ANALYSIS",
        "TEXT_CLASSIFICATION", "RELATION_EXTRACTION", "DRUG_MATCHING",
    }
    if raw_modality in {"text", "document"} or normalized_task in text_tasks:
        from app.agent.capability_registry import ModelCapabilityRegistry
        task, _ = ModelCapabilityRegistry().resolve_text_task(raw_task or "NER")
        return "text", task

    if raw_modality not in {"image", "video", "audio"}:
        if normalized_task in {"VIDEO", "VIDEO_TRACKING", "ACTION_RECOGNITION"}:
            raw_modality = "video"
        else:
            raw_modality = "image"
    return raw_modality, normalized_task or "OBJECT_DETECTION"


def resolve_asset_execution_modality(asset: Any, fallback: str = "image") -> str:
    """Resolve modality from persisted asset metadata before project fallback."""
    read = asset.get if isinstance(asset, dict) else lambda key, default=None: getattr(asset, key, default)
    for key in ("modality", "media_type", "asset_type", "content_type", "file_type", "mime_type"):
        value = str(read(key, "") or "").strip().lower()
        if value.startswith("text/") or value in {
            "text", "document", "application/json", "application/xml", "application/ld+json",
        }:
            return "text"
        if value.startswith("image/") or value == "image":
            return "image"
        if value.startswith("video/") or value == "video":
            return "video"
        if value.startswith("audio/") or value == "audio":
            return "audio"

    filename = str(read("filename", "") or read("original_filename", "") or "").lower()
    suffix = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if suffix in {"txt", "md", "csv", "json", "xml", "log", "yaml", "yml", "tsv", "html"}:
        return "text"
    if suffix in {"mp4", "avi", "mov", "mkv", "webm", "m4v", "flv", "wmv"}:
        return "video"
    if suffix in {"jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif", "gif"}:
        return "image"
    return fallback


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def _item_out(row: Any, model_runs: list[Any] | None = None) -> dict[str, Any]:
    doc = to_mongo_doc(row) or MongoDoc()
    runs = to_mongo_docs(model_runs or [])
    return {
        "id": doc.get("id", ""),
        "batch_id": doc.get("batch_id", ""),
        "asset_id": doc.get("asset_id", ""),
        "status": doc.get("status", JobItemStatus.QUEUED.value),
        "attempt": doc.get("attempt", 0),
        "error_message": doc.get("error_message", ""),
        "detection_count": doc.get("detection_count", 0),
        "duration_ms": doc.get("duration_ms"),
        "started_at": doc.get("started_at"),
        "finished_at": doc.get("finished_at"),
        "model_runs": [
            {
                "id": r.id,
                "model_key": r.get("model_key", ""),
                "model_id": r.get("model_id", ""),
                "status": r.get("status", ""),
                "purpose": r.get("purpose", ""),
                "error_message": r.get("error_message", ""),
                "detection_count": r.get("detection_count", 0),
                "mask_count": r.get("mask_count", 0),
                "duration_ms": r.get("duration_ms"),
                "started_at": r.get("started_at"),
                "finished_at": r.get("finished_at"),
            }
            for r in runs
            if r.get("job_item_id") == doc.get("id")
        ],
    }


def _batch_out(
    row: Any,
    *,
    include_items: bool = True,
    items_list: list[Any] | None = None,
    model_runs: list[Any] | None = None,
) -> dict[str, Any]:
    doc = to_mongo_doc(row) or MongoDoc()
    items = to_mongo_docs(items_list or doc.get("items") or [])
    runs = to_mongo_docs(model_runs or [])
    total = doc.get("total", 0)
    completed = doc.get("completed", 0)
    failed = doc.get("failed", 0)
    running = doc.get("running", 0)
    review = doc.get("review", 0)
    processed = completed + failed + review
    progress_pct = round((processed / total * 100.0), 1) if total > 0 else 0.0

    created_at = doc.get("created_at")
    started_at = doc.get("started_at")
    finished_at = doc.get("finished_at")
    processing_time_ms = None
    if started_at:
        end_time = finished_at or _utcnow()
        if hasattr(started_at, "timestamp") and hasattr(end_time, "timestamp"):
            processing_time_ms = max(0, int((end_time.timestamp() - started_at.timestamp()) * 1000))

    avg_latency = round(processing_time_ms / processed, 2) if (processing_time_ms is not None and processed > 0) else None

    status = doc.get("status", BatchStatus.QUEUED.value)
    if failed > 0 and completed > 0 and status not in (BatchStatus.SUCCEEDED.value, BatchStatus.RUNNING.value):
        status = "partially_failed"

    return {
        "id": doc.get("id", ""),
        "batch_id": doc.get("id", ""),
        "project_id": doc.get("project_id", ""),
        "status": status,
        "idempotency_key": doc.get("idempotency_key"),
        "total": total,
        "completed": completed,
        "successful": completed,
        "failed": failed,
        "review": review,
        "running": running,
        "processed": processed,
        "progress_percentage": progress_pct,
        "processing_time_ms": processing_time_ms,
        "avg_latency_per_image_ms": avg_latency,
        "model_id": doc.get("model_id", ""),
        "workflow": doc.get("workflow", []),
        "metrics": doc.get("metrics", {}),
        "error_summary": doc.get("error_summary", ""),
        "items": (
            [_item_out(i, runs) for i in items]
            if include_items
            else []
        ),
        "created_at": created_at,
        "updated_at": doc.get("updated_at"),
        "started_at": started_at,
        "finished_at": finished_at,
    }


class BatchService:
    def __init__(self, db: Any, settings: Settings) -> None:
        if hasattr(db, "batches"):
            self.db = db
        elif hasattr(db, "db"):
            self.db = db.db
        elif callable(db):
            self.db = db()
        else:
            self.db = get_database()
        self.settings = settings

    async def find_active_compatible(
        self,
        project_id: str,
        modality: str,
        task: str,
    ) -> Any | None:
        candidates = await self.db.batches.find({
            "project_id": project_id,
            "status": {"$in": [BatchStatus.QUEUED.value, BatchStatus.RUNNING.value, "processing"]},
        }).sort("created_at", 1).to_list(length=100000)
        for batch in candidates:
            stored_modality = str(batch.get("execution_modality") or "").lower()
            stored_task = str(batch.get("execution_task") or "").upper()
            if stored_modality and stored_task:
                if stored_modality == modality and stored_task == task.upper():
                    return batch
                logger.warning(
                    "batch_execution_reuse_rejected",
                    project_id=project_id,
                    batch_id=batch.get("id"),
                    requested_modality=modality,
                    batch_modality=stored_modality,
                    requested_task=task,
                    batch_task=stored_task,
                    reason="execution_context_mismatch",
                )
                continue

            project = await self.db.projects.find_one({"id": project_id})
            if not project:
                continue
            batch_modality, batch_task = resolve_execution_context(project)
            asset_ids = [str(value) for value in (batch.get("asset_ids") or [])]
            assets = await self.db.assets.find({
                "project_id": project_id,
                "id": {"$in": asset_ids},
            }).to_list(length=100000) if asset_ids else []
            compatible = (
                batch_modality == modality
                and batch_task.upper() == task.upper()
                and len(assets) == len(set(asset_ids))
                and all(resolve_asset_execution_modality(asset, modality) == modality for asset in assets)
            )
            if compatible:
                return batch
            logger.warning(
                "batch_execution_reuse_rejected",
                project_id=project_id,
                batch_id=batch.get("id"),
                requested_modality=modality,
                batch_modality=batch_modality,
                requested_task=task,
                batch_task=batch_task,
                reason="legacy_batch_assets_or_project_context_mismatch",
            )
        return None

    async def terminal_asset_ids(
        self,
        project_id: str,
        asset_ids: list[str],
        *,
        explicit_ai_annotation_trigger: bool = False,
    ) -> set[str]:
        """Return assets with a successful latest terminal execution.

        Failed/cancelled terminal items are historical attempts, not proof that
        the asset was successfully processed. Explicit AI annotation requests
        may retry HUMAN_REVIEW items and terminal items with zero persisted
        annotations, while successful annotated assets remain idempotently
        skipped.
        """
        requested = {str(asset_id) for asset_id in asset_ids if asset_id}
        if not requested:
            return set()
        rows = await self.db.job_items.find({"asset_id": {"$in": list(requested)}}).to_list(length=100000)
        successful_terminal = {
            JobItemStatus.SUCCEEDED.value,
            JobItemStatus.HUMAN_REVIEW.value,
            "completed",
        }
        candidate_rows = [row for row in rows if str(row.get("asset_id")) in requested and row.get("batch_id")]
        batch_ids = {str(row.get("batch_id")) for row in candidate_rows}
        if not batch_ids:
            return set()
        batches = await self.db.batches.find({"id": {"$in": list(batch_ids)}, "project_id": project_id}).to_list(length=100000)
        valid_batch_ids = {str(batch.get("id")) for batch in batches}
        scoped_rows = [row for row in candidate_rows if str(row.get("batch_id")) in valid_batch_ids]

        def execution_time(row: Any) -> datetime:
            return (
                _as_utc(row.get("finished_at"))
                or _as_utc(row.get("updated_at"))
                or _as_utc(row.get("created_at"))
                or datetime.min.replace(tzinfo=UTC)
            )

        latest_by_asset: dict[str, Any] = {}
        for row in scoped_rows:
            asset_id = str(row.get("asset_id"))
            previous = latest_by_asset.get(asset_id)
            if previous is None or execution_time(row) >= execution_time(previous):
                latest_by_asset[asset_id] = row

        persisted_annotation_counts: dict[str, int] = {}
        annotations_collection = getattr(self.db, "annotations", None)
        if annotations_collection is not None:
            for asset_id in latest_by_asset:
                persisted_annotation_counts[asset_id] = await annotations_collection.count_documents({"asset_id": asset_id})

        processed: set[str] = set()
        for asset_id in requested:
            latest = latest_by_asset.get(asset_id)
            status = latest.get("status") if latest else None
            successful = bool(latest and status in successful_terminal)
            annotation_count = persisted_annotation_counts.get(asset_id, 0)
            explicitly_reprocessable = bool(
                explicit_ai_annotation_trigger
                and successful
                and (
                    status == JobItemStatus.HUMAN_REVIEW.value
                    or annotation_count == 0
                )
            )
            if successful and not explicitly_reprocessable:
                processed.add(asset_id)
            logger.info(
                "asset_processing_eligibility",
                asset_id=asset_id,
                has_terminal_job=latest is not None,
                latest_job_item_id=str(latest.get("id")) if latest else None,
                latest_job_status=status,
                latest_job_result_status=(latest or {}).get("result_status"),
                batch_id=str(latest.get("batch_id")) if latest else None,
                persisted_annotation_count_for_asset=annotation_count,
                processing_successful=successful,
                processing_failed=bool(latest and status in {JobItemStatus.FAILED.value, JobItemStatus.CANCELLED.value, "failed_final"}),
                explicit_ai_annotation_trigger=explicit_ai_annotation_trigger,
                explicitly_reprocessable=explicitly_reprocessable,
                eligible=not successful or explicitly_reprocessable,
                skip_reason=(
                    "explicit_reprocess_human_review_or_zero_annotations"
                    if explicitly_reprocessable
                    else "successfully_processed_with_persisted_annotations"
                    if successful
                    else "previous_processing_failed_or_incomplete"
                    if latest
                    else "no_terminal_execution"
                ),
            )
        return processed

    async def create(
        self,
        project_id: str,
        payload: BatchCreate,
        *,
        batch_creation_source: str = "direct_batch_api",
        explicit_ai_annotation_trigger: bool = False,
        caller_context: str | None = None,
    ) -> dict[str, Any]:
        requested_count = len(payload.asset_ids) if payload.asset_ids is not None else None
        if not explicit_ai_annotation_trigger:
            logger.error(
                "batch_creation_rejected_missing_explicit_trigger",
                batch_creation_source=batch_creation_source,
                trigger_type="automatic_or_unclassified",
                endpoint=None,
                request_id=caller_context,
                project_id=project_id,
                asset_count=requested_count,
                explicit_ai_annotation_trigger=False,
                caller_module=__name__,
                caller_function="create",
            )
            from app.errors import ValidationAppError
            raise ValidationAppError(
                "AI annotation batch creation requires an explicit trigger"
            )
        logger.info(
            "batch_creation_request",
            project_id=project_id,
            asset_count=requested_count,
            requested_count=requested_count,
            batch_creation_source=batch_creation_source,
            explicit_ai_annotation_trigger=explicit_ai_annotation_trigger,
            caller_context=caller_context,
        )
        try:
            return await self._create(
                project_id,
                payload,
                batch_creation_source=batch_creation_source,
                explicit_ai_annotation_trigger=explicit_ai_annotation_trigger,
                caller_context=caller_context,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "batch_creation_failed",
                project_id=project_id,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise

    async def _create(
        self,
        project_id: str,
        payload: BatchCreate,
        *,
        batch_creation_source: str,
        explicit_ai_annotation_trigger: bool,
        caller_context: str | None,
    ) -> dict[str, Any]:
        database_id = getattr(self.db, "database_id", "engenii-annotate-native")
        logger.info(
            "BATCH_CREATE_START",
            project_id=project_id,
            asset_count=len(payload.asset_ids) if payload.asset_ids is not None else 0,
            database_id=database_id,
        )
        project = await self.db.projects.find_one({"id": project_id})
        if not project:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        execution_modality, execution_task = resolve_execution_context(project)

        from app.services.projects import _get_ontology_status, ProjectService
        ontology = list(project.get("label_ontology") or [])
        labels = list(project.get("labels") or [])
        is_text_classification = str(project.get("task_type") or "").strip().upper() == "TEXT_CLASSIFICATION"

        def ontology_is_approved() -> bool:
            if str(project.get("ontology_status") or "").lower() != "approved":
                return False
            if is_text_classification and not ontology:
                return True
            return _get_ontology_status(ontology, labels) == "approved"

        if not ontology_is_approved():
            from app.storage.files import FileStorage
            storage_instance = getattr(self, "storage", None) or FileStorage(self.settings.storage_dir)
            svc = ProjectService(self.db, self.settings, storage_instance)
            await svc.approve_ontology(project_id)
            project = await self.db.projects.find_one({"id": project_id}) or project
            ontology = list(project.get("label_ontology") or [])
            labels = list(project.get("labels") or [])

        if not ontology_is_approved():
            raise ValidationAppError(
                "Approve the ontology before starting annotation",
                details={"ontology_status": "pending_approval"},
            )

        logger.info("batch_creation_start", project_id=project_id)

        # Idempotency check: prevent duplicate active batch
        active = await self.find_active_compatible(project_id, execution_modality, execution_task)
        if active:
            items = await self.db.job_items.find({"batch_id": active["id"]}).to_list(length=100000)
            return _batch_out(active, items_list=items)

        if payload.idempotency_key:
            existing = await self.db.batches.find_one({
                "project_id": project_id,
                "idempotency_key": payload.idempotency_key,
            })
            if existing:
                items = await self.db.job_items.find({"batch_id": existing["id"]}).to_list(length=100000)
                return _batch_out(existing, items_list=items)

        if payload.asset_ids is not None:
            asset_ids = list(dict.fromkeys(payload.asset_ids))
            if not asset_ids:
                raise ValidationAppError("asset_ids cannot be empty")
            raw_assets = await self.db.assets.find({
                "project_id": project_id,
                "id": {"$in": asset_ids}
            }).to_list(length=100000)
            assets = to_mongo_docs(raw_assets)
            found = {a.id for a in assets}
            missing = [aid for aid in asset_ids if aid not in found]
            if missing:
                raise ValidationAppError(
                    "One or more asset_ids are invalid for this project",
                    details={"missing": missing},
                )
        else:
            raw_assets = await self.db.assets.find({"project_id": project_id}).to_list(length=100000)
            assets = to_mongo_docs(raw_assets)
            if not assets:
                raise ValidationAppError("Project has no assets to process")
            pending = [
                a for a in assets
                if a.get("status") in {AssetStatus.UPLOADED.value, AssetStatus.FAILED.value, AssetStatus.QUEUED.value}
            ]
            if pending and len(pending) < len(assets):
                assets = pending

        plan = await self.db.project_plans.find_one({"project_id": project_id})
        workflow: list[Any] = []
        if self.settings.demo_image_pipeline:
            workflow = [{"key": key, "required": True} for key in ("florence", "yolo26", "dino")]
        elif plan and plan.get("status") == PlanStatus.APPROVED.value and plan.get("workflow"):
            workflow = list(plan["workflow"])
        elif plan and plan.get("workflow") and plan.get("status") != PlanStatus.APPROVED.value:
            raise ValidationAppError(
                "Approve the project plan before starting inference",
                details={"plan_status": plan.get("status")},
            )
        else:
            workflow = [
                {
                    "key": "yolo26",
                    "purpose": "Primary object detection",
                    "required": True,
                    "model_id": self.settings.yolo26_model_id,
                }
            ]

        from app.inference.ontology_map import build_ontology_index
        from app.inference.routing import ensure_detection_workflow

        ont_index = build_ontology_index(
            list(project.get("labels") or []),
            ontology=list(project.get("label_ontology") or []),
        )
        workflow = ensure_detection_workflow(
            workflow,
            ont_index,
            dino_enabled=self.settings.dino_enabled,
            yolo_enabled=self.settings.yolo26_enabled,
        )

        now = _utcnow()
        batch_id = _uuid()
        batch_doc = {
            "id": batch_id,
            "project_id": project_id,
            "asset_ids": [str(asset.id) for asset in assets],
            "status": BatchStatus.QUEUED.value,
            "idempotency_key": payload.idempotency_key,
            "total": len(assets),
            "completed": 0,
            "failed": 0,
            "running": 0,
            "model_id": self.settings.yolo26_model_id,
            "workflow": workflow,
            "batch_creation_source": batch_creation_source,
            "explicit_ai_annotation_trigger": explicit_ai_annotation_trigger,
            "execution_modality": execution_modality,
            "execution_task": execution_task,
            "caller_context": caller_context,
            "metrics": {},
            "error_summary": "",
            "created_at": now,
            "updated_at": now,
        }
        await self.db.batches.insert_one(batch_doc)
        logger.info(
            "BATCH_PERSISTED",
            project_id=project_id,
            asset_count=len(assets),
            batch_id=batch_id,
            status=batch_doc["status"],
            job_item_count=0,
            database_id=database_id,
        )
        logger.info(
            "batch_created",
            batch_id=batch_id,
            project_id=project_id,
            job_id=batch_id,
            status=batch_doc["status"],
            database_id=getattr(self.db, "database_id", ""),
            firestore_project=getattr(self.db, "project_id", ""),
            collection="batches",
            created_at=now,
            total_items=batch_doc["total"],
            batch_creation_source=batch_creation_source,
            explicit_ai_annotation_trigger=explicit_ai_annotation_trigger,
            caller_context=caller_context,
        )

        # Verify the write through the same database/client that performed it,
        # before creating dependent job items.  This makes a cross-process or
        # configuration mismatch fail at the point of creation instead of
        # leaving a batch that the worker can never discover.
        verified_batch = await self.db.batches.find_one({"id": batch_id})
        if verified_batch is None:
            logger.error(
                "batch_creation_verification_failed",
                batch_id=batch_id,
                project_id=project_id,
                job_id=batch_id,
                status=batch_doc["status"],
                database_id=getattr(self.db, "database_id", ""),
                firestore_project=getattr(self.db, "project_id", ""),
                collection="batches",
            )
            raise RuntimeError(f"Batch write could not be read back: {batch_id}")
        logger.info(
            "batch_creation_verified",
            batch_id=batch_id,
            project_id=project_id,
            job_id=batch_id,
            status=verified_batch.get("status"),
            database_id=getattr(self.db, "database_id", ""),
            firestore_project=getattr(self.db, "project_id", ""),
            collection="batches",
        )
        if verified_batch.get("status") != BatchStatus.QUEUED.value:
            raise RuntimeError(
                f"Batch status changed during creation for {batch_id}: "
                f"{verified_batch.get('status')!r}"
            )

        seen_assets: set[str] = set()
        item_docs = []
        asset_ids_to_queue = []
        for asset in assets:
            if asset.id in seen_assets:
                continue
            seen_assets.add(asset.id)
            item_docs.append({
                "id": _uuid(),
                "batch_id": batch_id,
                "asset_id": asset.id,
                "execution_modality": execution_modality,
                "execution_task": execution_task,
                "status": JobItemStatus.QUEUED.value,
                "attempt": 0,
                "error_message": "",
                "detection_count": 0,
                "created_at": now,
                "updated_at": now,
            })
            asset_ids_to_queue.append(asset.id)

        if item_docs:
            await self.db.job_items.insert_many(item_docs)
            logger.info(
                "JOB_ITEMS_CREATED",
                project_id=project_id,
                asset_count=len(assets),
                batch_id=batch_id,
                status=JobItemStatus.QUEUED.value,
                job_item_count=len(item_docs),
                database_id=database_id,
            )
            logger.info(
                "job_items_created",
                batch_id=batch_id,
                count=len(item_docs),
                item_ids=[item["id"] for item in item_docs],
            )
            for item in item_docs:
                logger.info(
                    "job_created",
                    batch_id=batch_id,
                    job_id=item["id"],
                    job_item_id=item["id"],
                    asset_id=item["asset_id"],
                    created_at=item["created_at"],
                    trigger_source=batch_creation_source,
                    explicit_ai_annotation_trigger=explicit_ai_annotation_trigger,
                )
            await self.db.assets.update_many(
                {"id": {"$in": asset_ids_to_queue}},
                {"$set": {"status": AssetStatus.QUEUED.value, "updated_at": now}}
            )

        requested_asset_ids = [str(asset.id) for asset in assets]
        created_asset_ids = [str(item.get("asset_id")) for item in item_docs]
        logger.info(
            "batch_job_item_reconciliation",
            batch_id=batch_id,
            project_id=project_id,
            requested_assets=len(requested_asset_ids),
            unique_assets=len(set(requested_asset_ids)),
            created_job_items=len(item_docs),
            unique_job_item_assets=len(set(created_asset_ids)),
            missing_assets=sorted(set(requested_asset_ids) - set(created_asset_ids)),
            unexpected_assets=sorted(set(created_asset_ids) - set(requested_asset_ids)),
        )
        if (
            len(requested_asset_ids) != len(set(requested_asset_ids))
            or len(item_docs) != len(requested_asset_ids)
            or set(created_asset_ids) != set(requested_asset_ids)
        ):
            raise RuntimeError(
                f"Batch job-item identity mismatch for {batch_id}: "
                f"requested={requested_asset_ids!r}, created={created_asset_ids!r}"
            )

        await self.db.projects.update_one({"id": project_id}, {"$set": {"status": ProjectStatus.PROCESSING.value, "updated_at": now}})

        persisted_batch = await self.db.batches.find_one({"id": batch_id})
        persisted_items = await self.db.job_items.find({"batch_id": batch_id}).to_list(length=100000)
        database_id = getattr(self.db, "database_id", "unknown")
        logger.info(
            "BATCH_CREATE_RESULT",
            project_id=project_id,
            asset_count=len(assets),
            batch_id=batch_id,
            status=persisted_batch.get("status") if persisted_batch else None,
            job_item_count=len(persisted_items),
            database_id=database_id,
        )
        logger.info(
            "batch_creation_persisted",
            batch_id=batch_id,
            status=persisted_batch.get("status") if persisted_batch else None,
            database_id=database_id,
        )
        if not persisted_batch:
            raise RuntimeError(f"Batch read-back failed after creation: {batch_id}")
        observed_batch_status = persisted_batch.get("status")
        if observed_batch_status not in {
            BatchStatus.QUEUED.value,
            BatchStatus.RUNNING.value,
            BatchStatus.SUCCEEDED.value,
            BatchStatus.FAILED.value,
            BatchStatus.PARTIAL_SUCCESS.value,
            "partially_failed",
        }:
            raise RuntimeError(
                f"Batch status read-back mismatch for {batch_id}: {observed_batch_status!r}"
            )
        if len(persisted_items) != len(item_docs) or {
            str(item.get("asset_id")) for item in persisted_items
        } != set(requested_asset_ids) or any(item.get("status") not in {
            JobItemStatus.QUEUED.value,
            JobItemStatus.RUNNING.value,
            JobItemStatus.SUCCEEDED.value,
            JobItemStatus.FAILED.value,
            JobItemStatus.CANCELLED.value,
            JobItemStatus.HUMAN_REVIEW.value,
        } for item in persisted_items):
            raise RuntimeError(f"Job item read-back mismatch for batch {batch_id}")

        return _batch_out(batch_doc, items_list=item_docs)

    async def get(self, batch_id: str, include_items: bool = True) -> dict[str, Any]:
        doc = await self.db.batches.find_one({"id": batch_id})
        if not doc:
            raise NotFoundError("Batch", batch_id)
        items = []
        runs = []
        if include_items:
            items = await self.db.job_items.find({"batch_id": batch_id}).to_list(length=100000)
            runs = await self.db.model_runs.find({"batch_id": batch_id}).to_list(length=100000)
        return _batch_out(doc, include_items=include_items, items_list=items, model_runs=runs)

    async def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        cursor = self.db.batches.find({"project_id": project_id}).sort("created_at", -1)
        raw_docs = await cursor.to_list(length=1000)
        out = []
        for d in raw_docs:
            items = await self.db.job_items.find({"batch_id": d["id"]}).to_list(length=100000)
            out.append(_batch_out(d, items_list=items))
        return out

    async def cancel(self, batch_id: str) -> dict[str, Any]:
        doc = await self.db.batches.find_one({"id": batch_id})
        if not doc:
            raise NotFoundError("Batch", batch_id)
        now = _utcnow()
        await self.db.batches.update_one({"id": batch_id}, {"$set": {"status": BatchStatus.FAILED.value, "error_summary": "Cancelled by user", "updated_at": now}})
        await self.db.job_items.update_many(
            {"batch_id": batch_id, "status": JobItemStatus.QUEUED.value},
            {"$set": {"status": JobItemStatus.FAILED.value, "error_message": "Batch cancelled", "updated_at": now}}
        )
        return await self.get(batch_id)

    async def claim_next_item(
        self,
        *,
        cancelled_project_ids: set[str] | None = None,
    ) -> MongoDoc | None:
        now = _utcnow()
        queued_items = await self.db.job_items.find(
            {"status": JobItemStatus.QUEUED.value}
        ).sort("created_at", 1).to_list(length=100000)

        for queued in queued_items:
            item_id = str(queued.get("id") or "")
            batch_id = str(queued.get("batch_id") or "")
            asset_id = str(queued.get("asset_id") or "")
            if not item_id or not batch_id:
                continue

            batch = await self.db.batches.find_one({"id": batch_id})
            batch_status = (batch or {}).get("status")
            expected_assets = {str(value) for value in ((batch or {}).get("asset_ids") or [])}
            project = None
            asset = None
            error_message = None
            if batch is None:
                error_message = f"ORPHANED: batch {batch_id} no longer exists"
            elif str(batch.get("id") or "") != batch_id:
                error_message = "BATCH_IDENTITY_MISMATCH: job item batch does not match its parent"
            elif batch.get("explicit_ai_annotation_trigger") is not True:
                error_message = "UNAUTHORIZED_BATCH: explicit AI annotation trigger is missing"
            elif batch_status not in {BatchStatus.QUEUED.value, BatchStatus.RUNNING.value}:
                error_message = f"INACTIVE_BATCH: batch status is {batch_status}"
            elif not asset_id or asset_id not in expected_assets:
                error_message = "JOB_ITEM_IDENTITY_MISMATCH: asset is not a member of its batch"

            # Authorize the execution context before atomically claiming the
            # item. This prevents a generic queue poll from crossing between
            # text/document and image batches, including legacy records.
            if error_message is None and batch is not None:
                projects_collection = getattr(self.db, "projects", None)
                project = (
                    await projects_collection.find_one({"id": batch.get("project_id")})
                    if projects_collection is not None
                    else None
                )
                asset = await self.db.assets.find_one({
                    "id": asset_id,
                    "project_id": batch.get("project_id"),
                })
                requested_modality, requested_task = resolve_execution_context(project or {})
                batch_modality = str(batch.get("execution_modality") or requested_modality).lower()
                batch_task = str(batch.get("execution_task") or requested_task).upper()
                item_modality = str(queued.get("execution_modality") or batch_modality).lower()
                item_task = str(queued.get("execution_task") or batch_task).upper()
                asset_modality = resolve_asset_execution_modality(asset, batch_modality) if asset else "missing"
                mismatch = (
                    item_modality != batch_modality
                    or item_task != batch_task
                    or asset_modality != batch_modality
                )
                if mismatch:
                    error_message = "EXECUTION_CONTEXT_MISMATCH: queued item is not authorized for this batch"
                    logger.error(
                        "execution_dispatch_rejected",
                        requested_batch_id=batch_id,
                        job_item_batch_id=str(queued.get("batch_id") or ""),
                        requested_modality=batch_modality,
                        asset_modality=asset_modality,
                        requested_task=batch_task,
                        job_item_task=item_task,
                        asset_id=asset_id,
                        job_item_id=item_id,
                        batch_id=batch_id,
                        reason=error_message,
                    )

            if error_message:
                await self.db.job_items.update_one(
                    {"id": item_id, "status": JobItemStatus.QUEUED.value},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "error_message": error_message,
                        "finished_at": now,
                        "updated_at": now,
                    }},
                )
                if batch is not None:
                    await self.db.batches.update_one(
                        {"id": batch_id},
                        {"$set": {"error_summary": error_message, "updated_at": now}},
                    )
                logger.error(
                    "job_item_claim_rejected",
                    job_item_id=item_id,
                    batch_id=batch_id,
                    asset_id=asset_id,
                    error=error_message,
                )
                continue

            if str(batch.get("project_id") or "") in (cancelled_project_ids or set()):
                continue

            logger.info(
                "execution_dispatch_authorized",
                request_id=batch.get("caller_context"),
                batch_id=batch_id,
                job_item_id=item_id,
                asset_id=asset_id,
                task=str(batch.get("execution_task") or queued.get("execution_task") or "").upper(),
                modality=str(batch.get("execution_modality") or queued.get("execution_modality") or "").lower(),
                trigger_source=batch.get("batch_creation_source", "unknown"),
            )

            claimed = await self.db.job_items.find_one_and_update(
                {
                    "id": item_id,
                    "status": JobItemStatus.QUEUED.value,
                    "batch_id": batch_id,
                    "asset_id": asset_id,
                },
                {"$set": {
                    "status": JobItemStatus.RUNNING.value,
                    "started_at": now,
                    "updated_at": now,
                }, "$inc": {"attempt": 1}},
                return_document=True,
            )
            if not claimed:
                continue

            # The conditional single-document transition is the authorization
            # gate for execution; a cancellation or status change wins the race.
            claimed_batch = await self.db.batches.find_one_and_update(
                {
                    "id": batch_id,
                    "status": {"$in": [BatchStatus.QUEUED.value, BatchStatus.RUNNING.value]},
                    "explicit_ai_annotation_trigger": True,
                },
                {"$set": {
                    "status": BatchStatus.RUNNING.value,
                    "started_at": batch.get("started_at") or now,
                    "updated_at": now,
                }, "$inc": {"running": 1}},
                return_document=True,
            )
            if claimed_batch is None:
                await self.db.job_items.update_one(
                    {"id": item_id, "status": JobItemStatus.RUNNING.value, "batch_id": batch_id},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "error_message": "BATCH_AUTHORIZATION_CHANGED: batch became inactive before execution",
                        "finished_at": now,
                        "updated_at": now,
                    }},
                )
                continue

            return to_mongo_doc(claimed)

        return None

    async def complete_item(
        self,
        item_id: str,
        status: str,
        error_message: str = "",
        detection_count: int = 0,
        duration_ms: int | None = None,
    ) -> None:
        now = _utcnow()
        item = await self.db.job_items.find_one({"id": item_id})
        if not item:
            logger.error("job_item_completion_missing", job_item_id=item_id, status=status)
            return

        terminal_statuses = {
            JobItemStatus.SUCCEEDED.value,
            JobItemStatus.FAILED.value,
            JobItemStatus.CANCELLED.value,
            JobItemStatus.HUMAN_REVIEW.value,
        }
        if item.get("status") in terminal_statuses:
            logger.warning(
                "job_item_completion_duplicate",
                job_item_id=item_id,
                batch_id=item.get("batch_id"),
                asset_id=item.get("asset_id"),
                existing_status=item.get("status"),
                ignored_status=status,
            )
            return

        batch_id = item["batch_id"]
        is_success = status == JobItemStatus.SUCCEEDED.value
        is_review = status == JobItemStatus.HUMAN_REVIEW.value

        await self.db.job_items.update_one(
            {"id": item_id},
            {"$set": {
                "status": status,
                "error_message": error_message,
                "detection_count": detection_count,
                "duration_ms": duration_ms,
                "finished_at": now,
                "updated_at": now,
            }}
        )

        if item.get("asset_id"):
            asset_status = AssetStatus.READY.value if (is_success or is_review) else AssetStatus.FAILED.value
            await self.db.assets.update_one(
                {"id": item["asset_id"]},
                {"$set": {"status": asset_status, "updated_at": now}}
            )

        batch = await self.db.batches.find_one({"id": batch_id})
        if not batch:
            logger.warning(
                "job_item_completion_batch_missing",
                job_item_id=item_id,
                batch_id=batch_id,
                asset_id=item.get("asset_id"),
                status=status,
            )
            return
        items, missing, unexpected, non_terminal = await self._reconcile_batch_items(batch_id, batch=batch)
        if unexpected:
            logger.error(
                "batch_reconciliation_unexpected_assets",
                batch_id=batch_id,
                unexpected_assets=unexpected,
            )
        counts = self._item_counts(items)
        await self.db.batches.update_one(
            {"id": batch_id},
            {"$set": {
                "completed": counts["completed"],
                "failed": counts["failed"],
                "review": counts["review"],
                "running": counts["running"],
                "updated_at": now,
            }}
        )

        logger.info(
            "batch_progress",
            batch_id=batch_id,
            completed=counts["completed"],
            failed=counts["failed"],
            review=counts["review"],
            total=len(items),
        )
        logger.info(
            "batch_progress_updated",
            batch_id=batch_id,
            queued=counts["queued"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
            review=counts["review"],
            total=len(items),
        )

        logger.info(
            "batch_reconciliation",
            batch_id=batch_id,
            expected_assets=len((batch or {}).get("asset_ids") or []),
            job_items=len(items),
            queued=counts["queued"],
            processing=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
            missing_assets=missing,
            unexpected_assets=unexpected,
        )
        if not missing and not unexpected and not non_terminal:
            await self.finalize_batch(batch_id)

    @staticmethod
    def _item_counts(items: list[MongoDoc]) -> dict[str, int]:
        return {
            "queued": sum(1 for item in items if item.get("status") == JobItemStatus.QUEUED.value),
            "running": sum(1 for item in items if item.get("status") == JobItemStatus.RUNNING.value),
            "completed": sum(1 for item in items if item.get("status") == JobItemStatus.SUCCEEDED.value),
            "failed": sum(1 for item in items if item.get("status") in {
                JobItemStatus.FAILED.value,
                JobItemStatus.CANCELLED.value,
            }),
            "review": sum(1 for item in items if item.get("status") == JobItemStatus.HUMAN_REVIEW.value),
        }

    async def _reconcile_batch_items(
        self,
        batch_id: str,
        *,
        batch: Any | None = None,
    ) -> tuple[list[MongoDoc], list[str], list[str], list[MongoDoc]]:
        batch = batch or await self.db.batches.find_one({"id": batch_id})
        items = to_mongo_docs(await self.db.job_items.find({"batch_id": batch_id}).to_list(length=100000))
        expected = [str(aid) for aid in ((batch or {}).get("asset_ids") or [])]
        expected_set = set(expected)
        actual_set = {str(item.get("asset_id")) for item in items if item.get("asset_id") is not None}
        missing = sorted(expected_set - actual_set)
        unexpected = sorted(actual_set - expected_set) if expected_set else []

        recovery_allowed = bool(
            batch
            and batch.get("status") in {BatchStatus.QUEUED.value, BatchStatus.RUNNING.value}
            and batch.get("explicit_ai_annotation_trigger") is True
            and batch.get("recovered_from_restart") is True
            and getattr(self.settings, "recover_interrupted_batches", False)
        )
        if missing and not recovery_allowed:
            error_message = (
                "BATCH_RECONCILIATION_ERROR: missing job items are not eligible "
                "for automatic repair"
            )
            if batch:
                await self.db.batches.update_one(
                    {"id": batch_id, "status": {"$in": [BatchStatus.QUEUED.value, BatchStatus.RUNNING.value]}},
                    {"$set": {
                        "status": BatchStatus.FAILED.value,
                        "error_summary": error_message,
                        "finished_at": _utcnow(),
                        "updated_at": _utcnow(),
                    }},
                )
            logger.error(
                "batch_reconciliation_missing_items_blocked",
                batch_id=batch_id,
                missing_assets=missing,
                explicit_ai_annotation_trigger=(batch or {}).get("explicit_ai_annotation_trigger"),
                recovered_from_restart=(batch or {}).get("recovered_from_restart"),
            )

        if missing and recovery_allowed:
            now = _utcnow()
            repair_docs = [
                {
                    "id": _uuid(),
                    "batch_id": batch_id,
                    "asset_id": asset_id,
                    "status": JobItemStatus.QUEUED.value,
                    "attempt": 0,
                    "error_message": "",
                    "detection_count": 0,
                    "created_at": now,
                    "updated_at": now,
                }
                for asset_id in missing
            ]
            await self.db.job_items.insert_many(repair_docs)
            await self.db.assets.update_many(
                {"id": {"$in": missing}},
                {"$set": {"status": AssetStatus.QUEUED.value, "updated_at": now}},
            )
            await self.db.batches.update_one(
                {"id": batch_id},
                {"$set": {"total": len(expected), "updated_at": now}},
            )
            logger.error(
                "batch_reconciliation_missing_assets_repaired",
                batch_id=batch_id,
                missing_assets=missing,
                repaired_job_items=len(repair_docs),
            )
            items = to_mongo_docs(await self.db.job_items.find({"batch_id": batch_id}).to_list(length=100000))

        terminal = {
            JobItemStatus.SUCCEEDED.value,
            JobItemStatus.FAILED.value,
            JobItemStatus.CANCELLED.value,
            JobItemStatus.HUMAN_REVIEW.value,
        }
        non_terminal = [item for item in items if item.get("status") not in terminal]
        return items, missing, unexpected, non_terminal

    async def finalize_batch(self, batch_id: str) -> dict[str, Any]:
        batch = await self.db.batches.find_one({"id": batch_id})
        if not batch:
            raise NotFoundError("Batch", batch_id)

        items, missing, unexpected, non_terminal = await self._reconcile_batch_items(batch_id, batch=batch)
        counts = self._item_counts(items)
        expected_count = len((batch.get("asset_ids") or [])) or batch.get("total", 0)
        if missing or unexpected or non_terminal or len(items) != expected_count:
            logger.error(
                "batch_finalize_blocked",
                batch_id=batch_id,
                expected_assets=expected_count,
                job_items=len(items),
                missing_assets=missing,
                unexpected_assets=unexpected,
                non_terminal_job_items=[item.get("id") for item in non_terminal],
            )
            return await self.get(batch_id)
        durations = [i.get("duration_ms") for i in items if i.get("duration_ms") and i.get("duration_ms") > 0]
        detections = [i.get("detection_count") for i in items if i.get("detection_count") is not None]

        now = _utcnow()
        batch_status = (
            BatchStatus.FAILED.value if counts["failed"] > 0
            else BatchStatus.PARTIAL_SUCCESS.value if counts["review"] > 0
            else BatchStatus.SUCCEEDED.value
        )
        metrics = {
            "p50_duration_ms": _percentile(durations, 0.5),
            "p95_duration_ms": _percentile(durations, 0.95),
            "mean_detections": sum(detections) / len(detections) if detections else 0.0,
        }

        await self.db.batches.update_one(
            {"id": batch_id},
            {"$set": {
                "status": batch_status,
                "completed": counts["completed"],
                "failed": counts["failed"],
                "review": counts["review"],
                "running": counts["running"],
                "metrics": metrics,
                "finished_at": now,
                "updated_at": now,
            }}
        )

        # Update project status
        await self.db.projects.update_one(
            {"id": batch["project_id"]},
            {"$set": {"status": ProjectStatus.COMPLETED.value, "updated_at": now}}
        )
        result = await self.get(batch_id)
        logger.info(
            "batch_completed",
            batch_id=batch_id,
            status=batch_status,
            completed=counts["completed"],
            failed=counts["failed"],
            review=counts["review"],
            total=len(items),
        )
        return result

    async def reconcile_interrupted(self) -> None:
        """Reconcile job items or batches left in RUNNING state upon server startup.

        Also detects and fails orphaned job_items whose batch document no longer
        exists - these can never be processed and must not clog the queued scan.

        Startup is not an execution trigger. Persisted queued/interrupted work
        is closed here and requires a fresh explicit API request to run again.
        """
        now = _utcnow()
        recovery_window_seconds = max(
            1,
            int(getattr(self.settings, "timeout_batch_seconds", 600) or 600),
        )
        recovery_cutoff = now - timedelta(seconds=recovery_window_seconds)
        active_batch_docs = await self.db.batches.find({
            "status": {"$in": [BatchStatus.QUEUED.value, BatchStatus.RUNNING.value]}
        }).to_list(length=100000)
        active_batches = {str(item.get("id")): item for item in active_batch_docs if item.get("id")}

        def _last_activity(*docs: Any) -> datetime | None:
            timestamps = []
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                for field in ("updated_at", "started_at", "created_at"):
                    value = _as_utc(doc.get(field))
                    if value is not None:
                        timestamps.append(value)
            return max(timestamps) if timestamps else None

        running_items = await self.db.job_items.find(
            {"status": JobItemStatus.RUNNING.value}
        ).to_list(length=100000)
        requeued_asset_ids: list[str] = []
        recovered_terminal_items = 0
        for item in running_items:
            item_id = str(item.get("id") or "")
            batch_id = str(item.get("batch_id") or "")
            asset_id = str(item.get("asset_id") or "")
            batch_doc = active_batches.get(batch_id) or await self.db.batches.find_one({"id": batch_id})
            persisted_rows = await self.db.annotations.find({
                "asset_id": asset_id,
                "source": "ai",
            }).to_list(length=100000) if asset_id else []
            same_execution_result = any(
                str((row.get("provenance") or {}).get("batch_id") or "") == batch_id
                or str((row.get("provenance") or {}).get("job_item_id") or "") == item_id
                for row in persisted_rows
            )
            if same_execution_result:
                asset = await self.db.assets.find_one({"id": asset_id}) if asset_id else None
                review_status = str((asset or {}).get("review_status") or "").lower()
                terminal_status = (
                    JobItemStatus.HUMAN_REVIEW.value
                    if review_status in {"human_review", "human_review_required", "in_human_review"}
                    else JobItemStatus.SUCCEEDED.value
                )
                await self.db.job_items.update_one(
                    {"id": item_id, "status": JobItemStatus.RUNNING.value},
                    {"$set": {
                        "status": terminal_status,
                        "finished_at": now,
                        "updated_at": now,
                        "error_message": "Recovered persisted result after worker restart",
                    }}
                )
                recovered_terminal_items += 1
                logger.info(
                    "job_item_recovered_existing_result",
                    job_item_id=item_id,
                    batch_id=batch_id,
                    asset_id=asset_id,
                    resulting_state=terminal_status,
                    reason="persisted_result_matches_interrupted_execution",
                )
            elif (
                (_last_activity(item, batch_doc) is not None)
                and _last_activity(item, batch_doc) < recovery_cutoff
            ):
                await self.db.job_items.update_one(
                    {"id": item_id, "status": JobItemStatus.RUNNING.value},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "finished_at": now,
                        "updated_at": now,
                        "error_message": "Stale interrupted batch was not resumed after startup",
                    }}
                )
                logger.warning(
                    "stale_batch_recovery_suppressed",
                    batch_id=batch_id,
                    job_item_id=item_id,
                    asset_id=asset_id,
                    batch_status=(batch_doc or {}).get("status"),
                    last_activity_at=_last_activity(item, batch_doc),
                    recovery_window_seconds=recovery_window_seconds,
                    trigger_source=(batch_doc or {}).get("batch_creation_source", "unknown"),
                    reason="interrupted_work_exceeded_existing_batch_timeout",
                )
            else:
                await self.db.job_items.update_one(
                    {"id": item_id, "status": JobItemStatus.RUNNING.value},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "finished_at": now,
                        "updated_at": now,
                        "error_message": "Interrupted job was not resumed without explicit recovery authorization",
                    }}
                )
                logger.warning(
                    "batch_recovery_suppressed",
                    batch_id=batch_id,
                    job_item_id=item_id,
                    asset_id=asset_id,
                    explicit_ai_annotation_trigger=(batch_doc or {}).get("explicit_ai_annotation_trigger"),
                    recovery_enabled=False,
                    reason="startup_never_resumes_interrupted_work",
                )

        if requeued_asset_ids:
            await self.db.assets.update_many(
                {"id": {"$in": list(dict.fromkeys(requeued_asset_ids)),}, "status": AssetStatus.PROCESSING.value},
                {"$set": {"status": AssetStatus.QUEUED.value, "updated_at": now}}
            )
        # A queued batch can survive a process restart without appearing in
        # the RUNNING-item scan. Suppress only abandoned queued work outside
        # the existing batch timeout window; recent work remains recoverable.
        stale_queued_batches = []
        for batch_id, batch_doc in active_batches.items():
            if batch_doc.get("status") != BatchStatus.QUEUED.value:
                continue
            recovery_allowed = False
            if not recovery_allowed:
                error_message = "Queued batch was not resumed after startup; explicit user trigger is required"
                await self.db.job_items.update_many(
                    {"batch_id": batch_id, "status": JobItemStatus.QUEUED.value},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "finished_at": now,
                        "updated_at": now,
                        "error_message": error_message,
                    }}
                )
                await self.db.batches.update_one(
                    {"id": batch_id, "status": BatchStatus.QUEUED.value},
                    {"$set": {
                        "status": BatchStatus.FAILED.value,
                        "error_summary": error_message,
                        "finished_at": now,
                        "updated_at": now,
                    }}
                )
                stale_queued_batches.append(batch_id)
                logger.warning(
                    "batch_recovery_suppressed",
                    batch_id=batch_id,
                    explicit_ai_annotation_trigger=batch_doc.get("explicit_ai_annotation_trigger"),
                    recovery_enabled=False,
                    reason="startup_never_resumes_queued_work",
                )
                continue

        running_batches = await self.db.batches.find({"status": BatchStatus.RUNNING.value}).to_list(length=1000)
        requeued_running_batches = 0
        for b in running_batches:
            batch_last_activity = _last_activity(b)
            if batch_last_activity is not None and batch_last_activity < recovery_cutoff:
                await self.db.job_items.update_many(
                    {"batch_id": b["id"], "status": JobItemStatus.QUEUED.value},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "finished_at": now,
                        "updated_at": now,
                        "error_message": "Stale running batch was not resumed after startup",
                    }}
                )
                await self.db.batches.update_one(
                    {"id": b["id"], "status": BatchStatus.RUNNING.value},
                    {"$set": {
                        "status": BatchStatus.FAILED.value,
                        "error_summary": "Stale running batch was not resumed after startup",
                        "finished_at": now,
                        "updated_at": now,
                    }}
                )
                logger.warning(
                    "stale_batch_recovery_suppressed",
                    batch_id=b["id"],
                    batch_status=BatchStatus.RUNNING.value,
                    last_activity_at=batch_last_activity,
                    recovery_window_seconds=recovery_window_seconds,
                    trigger_source=b.get("batch_creation_source", "unknown"),
                    reason="running_work_exceeded_existing_batch_timeout",
                )
                continue
            queued_cnt = await self.db.job_items.count_documents({"batch_id": b["id"], "status": JobItemStatus.QUEUED.value})
            comp_cnt = await self.db.job_items.count_documents({"batch_id": b["id"], "status": JobItemStatus.SUCCEEDED.value})
            failed_cnt = await self.db.job_items.count_documents({"batch_id": b["id"], "status": JobItemStatus.FAILED.value})
            review_cnt = await self.db.job_items.count_documents({"batch_id": b["id"], "status": JobItemStatus.HUMAN_REVIEW.value})
            terminal_cnt = comp_cnt + failed_cnt + review_cnt
            total_cnt = b.get("total", 0)
            if queued_cnt > 0:
                await self.db.job_items.update_many(
                    {"batch_id": b["id"], "status": JobItemStatus.QUEUED.value},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "finished_at": now,
                        "updated_at": now,
                        "error_message": "Interrupted queued work was not resumed after startup",
                    }},
                )
                failed_cnt += queued_cnt
            reconciled_status = (
                BatchStatus.FAILED.value if failed_cnt > 0
                else BatchStatus.PARTIAL_SUCCESS.value if review_cnt > 0
                else BatchStatus.SUCCEEDED.value if terminal_cnt >= total_cnt
                else BatchStatus.FAILED.value
            )
            await self.db.batches.update_one(
                {"id": b["id"]},
                {"$set": {
                    "running": 0,
                    "completed": comp_cnt,
                    "failed": failed_cnt,
                    "review": review_cnt,
                    "status": reconciled_status,
                    "updated_at": now,
                }}
            )

        # Detect orphaned job_items: items in queued/running state whose batch
        # document no longer exists.  These items can never be processed and
        # must be failed immediately so they don't clog the polling loop.
        orphan_failed = 0
        queued_items = await self.db.job_items.find(
            {"status": {"$in": [JobItemStatus.QUEUED.value, JobItemStatus.RUNNING.value]}}
        ).to_list(length=10000)
        seen_batch_ids: dict[str, bool] = {}
        for item in queued_items:
            batch_id = item.get("batch_id")
            if not batch_id:
                continue
            if batch_id not in seen_batch_ids:
                batch_doc = await self.db.batches.find_one({"id": batch_id})
                seen_batch_ids[batch_id] = batch_doc is not None
            if not seen_batch_ids[batch_id]:
                await self.db.job_items.update_one(
                    {"id": item["id"]},
                    {"$set": {
                        "status": JobItemStatus.FAILED.value,
                        "error_message": f"ORPHANED: batch {batch_id} no longer exists",
                        "finished_at": now,
                        "updated_at": now,
                    }}
                )
                orphan_failed += 1

        logger.info(
            "reconcile_interrupted_complete",
            running_batches_requeued=requeued_running_batches,
            requeued_job_items=len(requeued_asset_ids),
            recovered_terminal_items=recovered_terminal_items,
            orphaned_items_failed=orphan_failed,
            stale_queued_batches_suppressed=len(stale_queued_batches),
            recovery_window_seconds=recovery_window_seconds,
        )

    async def retry_failed_items(self, batch_id: str) -> dict[str, Any]:
        """Reset failed items in a batch back to QUEUED for retrying."""
        batch = await self.db.batches.find_one({"id": batch_id})
        if not batch:
            raise NotFoundError("Batch", batch_id)

        failed_items = await self.db.job_items.find({"batch_id": batch_id, "status": JobItemStatus.FAILED.value}).to_list(length=100000)
        if not failed_items:
            return await self.get(batch_id)

        now = _utcnow()
        failed_count = len(failed_items)
        for item in failed_items:
            await self.db.job_items.update_one(
                {"id": item["id"]},
                {"$set": {"status": JobItemStatus.QUEUED.value, "error_message": "", "started_at": None, "finished_at": None, "updated_at": now}}
            )
            if item.get("asset_id"):
                await self.db.assets.update_one(
                    {"id": item["asset_id"]},
                    {"$set": {"status": AssetStatus.QUEUED.value, "updated_at": now}}
                )

        await self.db.batches.update_one(
            {"id": batch_id},
            {"$inc": {"failed": -failed_count}, "$set": {"status": BatchStatus.QUEUED.value, "updated_at": now}}
        )
        return await self.get(batch_id)
