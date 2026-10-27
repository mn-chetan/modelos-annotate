"""Async multi-model batch worker with bounded concurrency."""

from __future__ import annotations

import asyncio
import os
import socket
import tempfile
import time
import traceback
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.db.concurrency import commit_with_retry
from app.db.models import (
    AssetRow,
    BatchRow,
    JobItemRow,
    ModelRunRow,
    MongoDoc,
    MongoSession,
    ProjectRow,
    UsageEventRow,
    get_database,
    to_mongo_doc,
)
from app.db.firebase import DatabaseUnavailableError
from app.domain.enums import AssetStatus, BatchStatus, JobItemStatus, ModelRunStatus, ReviewStatus
from app.inference.contracts import BoundingBoxPercent, ModelAvailability, NormalizedDetection
from app.inference.detector import Detector
from app.inference.merge import merge_detections, stats_to_dict, verify_merged_detections
from app.inference.ontology_map import build_ontology_index
from app.inference.registry import InferenceRuntime, get_runtime
from app.inference.routing import SceneEvidence, build_capability_snapshot as build_label_source_plan
from app.logging import get_logger
from app.mcp.client.mcp_client import MCPClient
from app.services.annotations import AnnotationService
from app.services.batches import BatchService
from app.services.masks import MaskPersistenceError, MaskService
from app.services.review_decision import ReviewDecision, decide_review
from app.storage.files import FileStorage

logger = get_logger(__name__)

_SceneEvidence = SceneEvidence


def resolve_text_project_configuration(project: Any) -> tuple[str, list[str]]:
    """Resolve persisted text task and ontology without inheriting image defaults."""
    from app.agent.capability_registry import ModelCapabilityRegistry
    from app.services.text_capability import resolve_text_target_labels

    registry = ModelCapabilityRegistry()
    raw_task_values: list[Any] = []
    for field in ("text_analysis_type", "analysis_type", "annotation_type", "task_type"):
        value = getattr(project, field, None)
        if value:
            raw_task_values.append(value)
    annotation_types = getattr(project, "annotation_types", None) or []
    raw_task_values.extend(annotation_types if isinstance(annotation_types, list) else [annotation_types])

    task = ""
    for raw_task in raw_task_values:
        candidate = str(raw_task).strip()
        resolved, capability = registry.resolve_text_task(candidate)
        if capability and resolved != "UNSUPPORTED_TEXT_TASK":
            normalized = candidate.lower().replace("_", " ")
            if normalized not in {"object detection", "detection", "segmentation", "classification"}:
                task = resolved
                break
    if not task:
        task, _ = registry.resolve_text_task("NER")

    return task, resolve_text_target_labels(project, task)


def resolve_asset_modality(asset: Any, project: Any = None, path: Path | None = None) -> str:
    """Canonical resolver for asset modality.

    Resolution Priority:
    1. Direct asset modality/media_type/content_type metadata if explicit.
    2. Project modality metadata if explicit (text, document, video, image).
    3. File extension/MIME inspection as fallback.
    """
    def _read_attr(obj: Any, key: str) -> str | None:
        if obj is None:
            return None
        val = getattr(obj, key, None)
        if val is None and isinstance(obj, dict):
            val = obj.get(key)
        return str(val).strip().lower() if val else None

    # 1. Check asset metadata first
    for attr in ("modality", "media_type", "asset_type", "content_type", "file_type", "mime_type"):
        val = _read_attr(asset, attr)
        if val:
            if val in ("text", "document", "text/plain", "application/json", "text/csv", "application/xml", "text/xml", "text/markdown"):
                return "text"
            if val in ("video", "video/mp4", "video/quicktime", "video/x-msvideo"):
                return "video"
            if val in ("image", "image/jpeg", "image/png", "image/webp", "image/bmp"):
                return "image"

    # 2. Check project metadata
    for attr in ("modality", "task_type"):
        val = _read_attr(project, attr)
        if val:
            if val in ("text", "document", "sentiment", "sentiment_analysis", "ner", "entity_extraction", "text_classification", "relation_extraction"):
                return "text"
            if val in ("video", "video_tracking", "action_recognition"):
                return "video"
            if val in ("image", "object_detection", "instance_segmentation", "segmentation"):
                return "image"

    # 3. Fallback to filename extension inspection
    filename = _read_attr(asset, "filename") or _read_attr(asset, "original_filename") or (path.name if path else "")
    ext = Path(filename).suffix.lower()

    TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".log", ".yaml", ".yml", ".tsv", ".html"}
    VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".flv", ".wmv"}
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}

    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in IMAGE_EXTENSIONS:
        return "image"

    return "image"



def _is_transient_db_error(exc: BaseException) -> bool:
    if isinstance(exc, (DatabaseUnavailableError, TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    exc_str = str(exc).lower()
    return "database unavailable" in exc_str or "timeout" in exc_str or "connection" in exc_str or "firestore" in exc_str


async def _with_transient_db_retry(
    op_func: Any,
    batch_id: str,
    job_item_id: str,
    project_id: str,
    max_attempts: int = 3,
    initial_delay: float = 0.5,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await op_func()
        except Exception as exc:
            if not _is_transient_db_error(exc):
                raise
            last_exc = exc
            logger.warning(
                "firestore_transient_retry",
                batch_id=batch_id,
                job_item_id=job_item_id,
                project_id=project_id,
                attempt=attempt,
                max_attempts=max_attempts,
                exception_type=type(exc).__name__,
                error=str(exc),
            )
            if attempt < max_attempts:
                await asyncio.sleep(initial_delay * (2 ** (attempt - 1)))
    if last_exc:
        raise last_exc



async def _persist_mask_polygons(
    session: Any,
    storage: FileStorage,
    masks: list[Any],
) -> int:
    """Convert SAM2 masks into final polygon geometry for segmentation tasks in MongoDB."""

    import cv2
    from app.db.models import _utcnow, get_database
    from app.services.segmentation_quality import extract_polygon_from_mask

    db = get_database()
    polygon_count = 0
    for mask in masks:
        annotation_id = getattr(mask, "annotation_id", None)
        mask_path = getattr(mask, "mask_path", None)
        asset_id = getattr(mask, "asset_id", None)
        if not mask_path:
            continue
        image = cv2.imread(str(storage.resolve(mask_path)), cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue

        points = extract_polygon_from_mask(image, image.shape[1], image.shape[0])
        if not points or len(points) < 3:
            continue

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        polygon_geo = {"type": "polygon", "points": points}
        poly_x = min(xs)
        poly_y = min(ys)
        poly_w = max(max(xs) - min(xs), 0.1)
        poly_h = max(max(ys) - min(ys), 0.1)

        # Look up matching annotation doc in MongoDB
        target_doc = None
        if annotation_id:
            target_doc = await db.annotations.find_one({"id": annotation_id})
        if not target_doc and asset_id:
            target_doc = await db.annotations.find_one({"asset_id": asset_id})

        if target_doc:
            prov = dict(target_doc.get("provenance") or {})
            prov["segmentation_model"] = "sam2"
            prov["mask_id"] = getattr(mask, "id", None)
            prov["polygon_point_count"] = len(points)

            await db.annotations.update_one(
                {"_id": target_doc["_id"]},
                {
                    "$set": {
                        "geometry_type": "polygon",
                        "geometry": polygon_geo,
                        "x": poly_x,
                        "y": poly_y,
                        "w": poly_w,
                        "h": poly_h,
                        "provenance": prov,
                        "updated_at": _utcnow(),
                    }
                },
            )
            polygon_count += 1
    return polygon_count


def verify_annotations(
    merged: list[Any],
    all_detections: list[Any],
    scene_evidence: Any | None,
    completed_models: list[str],
    execution_plan: Any | None = None,
    enabled_map: dict[str, bool] | None = None,
    merge_stats: Any | None = None,
    auto_approve_threshold: float = 0.90,
) -> bool:
    """Run automated verification on merged detections to decide if human review is needed.

    Returns True if the asset requires human review, and False if it can be auto-approved.
    """
    req_verification = getattr(execution_plan, "verification", "standard") if execution_plan else "standard"
    rejected_count = (merge_stats.duplicates_suppressed + merge_stats.giant_suppressed) if merge_stats else 0
    model_avail = {k: bool(v) for k, v in enabled_map.items()} if enabled_map else {
        "yolo26": "yolo26" in completed_models,
        "faster_rcnn": "faster_rcnn" in completed_models
    }

    review_decision = decide_review(
        merged=merged,
        all_detections=all_detections,
        scene_evidence=scene_evidence,
        completed_models=completed_models,
        required_verification=req_verification,
        rejected_count=rejected_count,
        model_availability=model_avail,
        auto_approve_threshold=auto_approve_threshold,
    )
    return review_decision.human_review_required


def _attach_verification_evidence(
    merged: list[Any],
    all_detections: list[Any],
    *,
    decision: ReviewDecision,
    verification_report: dict[str, Any] | None = None,
) -> list[Any]:
    """Attach verification facts without altering model scores."""
    from app.inference.merge import box_iou_percent

    enriched = []
    for detection in merged:
        contributors = list((detection.provenance or {}).get("contributing_models") or [])
        agreeing_models = {detection.model_key}
        for raw in all_detections:
            if raw is detection or raw.label != detection.label or raw.model_key == detection.model_key:
                continue
            try:
                if box_iou_percent(detection, raw) >= 0.45:
                    agreeing_models.add(raw.model_key)
            except Exception:
                continue
        provenance = {
            **(detection.provenance or {}),
            "detection_evidence": {
                "contributing_models": contributors or [detection.model_key],
                "supporting_model_count": len(agreeing_models),
            },
            "model_agreement": len(agreeing_models) > 1,
            "verification_status": decision.status,
            "human_review_required": decision.human_review_required,
            "review_decision": {
                "unresolved_reasons": list(decision.unresolved_reasons),
                "evidence": decision.evidence,
            },
            "post_merge_verification": verification_report or {},
        }
        enriched.append(replace(detection, provenance=provenance))
    return enriched


@dataclass(frozen=True)
class _ExecutionPlan:
    """Backward-compatible execution plan used by the worker.

    If the routing module exposes a richer agentic plan, the worker consumes
    it dynamically. Otherwise this conservative plan keeps the existing
    workflow operational.
    """

    models: tuple[str, ...]
    strategy: str
    image_size: int | None
    tile_rows: int
    tile_cols: int
    tile_overlap: float
    reason: str
    planner_source: str
    verification: str = "standard"


class BatchWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: FileStorage,
        detector: Any = None,
        runtime: InferenceRuntime | None = None,
        session_factory: Any = MongoSession,
        db: Any = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.detector = detector
        try:
            self.runtime = runtime or get_runtime()
        except Exception:
            self.runtime = runtime
        from app.db.models import get_database
        self.db = db or get_database()
        self.session_factory = (
            (lambda: MongoSession(self.db))
            if db is not None and (session_factory is MongoSession or session_factory is None)
            else (session_factory or (lambda: MongoSession(self.db)))
        )
        # MCP capability layer wraps the same registry/adapters below; it is
        # additive and only used when settings.mcp_enabled (see _run_model_step).
        _reg = getattr(self.runtime, "registry", self.runtime)
        self.mcp_client = MCPClient(_reg) if _reg is not None else None
        host_name = socket.gethostname()
        pid = os.getpid()
        self.worker_identity = f"batch_worker_{host_name}_{pid}_{hex(id(self))}"
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._stop_lock = asyncio.Lock()
        self._shutdown_complete = False
        # max_parallel_workers is the authoritative worker-wide limit. The
        # previous fallback to max_concurrent_images allowed four claims while
        # startup reported a configured limit of two.
        configured_workers = max(1, getattr(settings, "max_parallel_workers", 2))
        cpu_workers = max(1, os.cpu_count() or 1)
        workers = min(configured_workers, cpu_workers)
        self._concurrency_reason = f"max_parallel_workers:{configured_workers},cpu_bound:{cpu_workers}"
        self._parallel_workers = workers
        self._semaphore = asyncio.Semaphore(workers)
        self._active = 0
        self._cancelled_projects: set[str] = set()
        self._job_tasks: dict[str, tuple[str, str, asyncio.Task[None]]] = {}

    @property
    def active_workers(self) -> int:
        return self._active

    def cancel_project(self, project_id: str, active_jobs: int = 0) -> None:
        self._cancelled_projects.add(project_id)
        for job_id, task_entry in list(self._job_tasks.items()):
            job_project_id = task_entry[0]
            task = task_entry[2] if len(task_entry) > 2 else task_entry[1]
            if job_project_id == project_id and not task.done():
                task.cancel()
                logger.info(
                    "job_cancelled_project_deleted",
                    job_id=job_id,
                    project_id=project_id,
                )
        logger.info(
            "project_jobs_cancellation_requested",
            project_id=project_id,
            active_jobs=active_jobs,
        )

    async def cancel_project_and_wait(self, project_id: str) -> None:
        """Stop project jobs before project-owned records are deleted."""
        self.cancel_project(project_id, active_jobs=self.active_workers)
        tasks = [
            entry[2]
            for entry in self._job_tasks.values()
            if entry[0] == project_id and len(entry) > 2 and not entry[2].done()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(
            "project_jobs_cancellation_complete",
            project_id=project_id,
            cancelled_tasks=len(tasks),
        )

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            logger.warning("batch_worker_already_running", worker_identity=self.worker_identity)
            return

        from app.db.models import get_database
        db = self.db or get_database()
        client_obj = getattr(db, "client", None)
        logger.info(
            "worker_firestore_configuration",
            worker_firestore_project=getattr(db, "project_id", ""),
            worker_firestore_database=getattr(db, "database_id", ""),
            worker_firestore_location="asia-south1",
            worker_firestore_client_identity=hex(id(client_obj)) if client_obj is not None else "None",
            worker_firebase_app_identity=hex(id(db)),
            worker_database_init_status=getattr(db, "connection_status", "unknown"),
        )
        # Perform actual Firestore operations to verify connectivity to batches & job_items
        await db.batches.find_one({})
        await db.job_items.find_one({})
        logger.info(
            "worker_firestore_connectivity_verified",
            database_id=getattr(db, "database_id", ""),
        )

        async with self.session_factory() as session:
            await BatchService(session, self.settings).reconcile_interrupted()
        self._stop.clear()
        self._shutdown_complete = False

        # Load primary eager models once into process memory upon worker startup; optional models load on demand
        if self.runtime is not None and not self.settings.skip_model_load:
            self.runtime.registry.load_eager()
            loaded_keys = [s.key for s in self.runtime.model_statuses() if s.loaded]
            logger.info("worker_models_preloaded", loaded_models=loaded_keys)

        def _on_worker_task_done(t: asyncio.Task[None]) -> None:
            if not t.cancelled() and t.exception():
                err = t.exception()
                logger.error(
                    "batch_worker_task_uncaught_exception",
                    worker_identity=self.worker_identity,
                    error=str(err),
                    exception_type=type(err).__name__,
                )

        self._task = asyncio.create_task(self._loop(), name="batch-worker")
        self._task.add_done_callback(_on_worker_task_done)

        logger.info(
            "batch_worker_started",
            worker_identity=self.worker_identity,
            max_parallel_workers=self._parallel_workers,
            configured_max_parallel_workers=self.settings.max_parallel_workers,
            concurrency_reason=self._concurrency_reason,
        )

    async def stop(self) -> None:
        """Stop polling and drain all jobs before the event loop is closed.

        The polling task and per-job tasks have separate lifetimes. Cancelling
        only the poller leaves model inference tasks alive while Uvicorn begins
        closing the loop, which is unsafe on Windows' Proactor loop.
        """
        async with self._stop_lock:
            if self._shutdown_complete:
                return

            active_tasks = [
                entry[2]
                for entry in self._job_tasks.values()
                if len(entry) > 2 and not entry[2].done()
            ]
            logger.info(
                "annotation_worker_stop_requested",
                worker_identity=self.worker_identity,
                active_annotation_tasks=len(active_tasks),
            )
            self._stop.set()

            if self._task is not None and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

            if active_tasks:
                logger.info(
                    "annotation_tasks_cancel_started",
                    worker_identity=self.worker_identity,
                    active_annotation_tasks=len(active_tasks),
                )
                for task in active_tasks:
                    task.cancel()
                await asyncio.gather(*active_tasks, return_exceptions=True)
                logger.info(
                    "annotation_tasks_cancel_complete",
                    worker_identity=self.worker_identity,
                    active_annotation_tasks=len(active_tasks),
                )

            # Tasks remove themselves in _run_guarded.finally; clear any
            # already-finished entries left by a concurrent completion.
            self._job_tasks.clear()
            self._shutdown_complete = True
            logger.info("batch_worker_stopped", worker_identity=self.worker_identity)

    async def _loop(self) -> None:
        poll = self.settings.worker_poll_interval_ms / 1000.0
        idle_poll = poll
        max_idle_poll = min(max(poll, 2.0), 10.0)
        database_backoff = 1.0
        while not self._stop.is_set():
            try:
                claimed = await self._claim_and_spawn()
                database_backoff = 1.0
                if claimed:
                    idle_poll = poll
                else:
                    idle_poll = min(idle_poll * 2.0, max_idle_poll)
            except asyncio.CancelledError:
                raise
            except DatabaseUnavailableError as exc:
                logger.warning(
                    "database_unavailable",
                    component="batch_worker",
                    retry_in_seconds=database_backoff,
                    error=str(exc),
                )
                await asyncio.sleep(database_backoff)
                database_backoff = min(database_backoff * 2, 30.0)
            except Exception:  # noqa: BLE001
                logger.exception("batch_worker_loop_error")
            finally:
                if not self._stop.is_set():
                    await asyncio.sleep(idle_poll)

    async def _claim_and_spawn(self) -> bool:
        available = self._parallel_workers - self._active
        if available <= 0:
            return False

        db = self.db or get_database()
        now = datetime.now(UTC)

        # 1. Query queued job items (Requirement 2)
        raw_queued_items = await db.job_items.find({
            "status": JobItemStatus.QUEUED.value
        }).sort("created_at", 1).to_list(length=available * 2)

        queued_items_found = len(raw_queued_items)
        if queued_items_found > 0:
            logger.info(
                "worker_poll",
                queued_items_found=queued_items_found,
                worker_identity=self.worker_identity,
            )
        else:
            logger.debug(
                "worker_poll",
                queued_items_found=0,
                worker_identity=self.worker_identity,
            )

        # Also support legacy batch query diagnostic for test_empty_query_returns_cleanly
        raw_batches = await db.batches.find({"status": BatchStatus.QUEUED.value}).sort("created_at", 1).to_list(length=10)
        if len(raw_batches) > 0:
            logger.info(
                "queued_batches_fetched",
                worker_identity=self.worker_identity,
                count=len(raw_batches),
                batch_ids=[b.get("id") for b in raw_batches if b.get("id")],
                batch_statuses=[b.get("status") for b in raw_batches if b.get("status")],
                database_id=getattr(db, "database_id", ""),
                project_id=getattr(db, "project_id", ""),
                collection="batches",
                query_filter={"status": BatchStatus.QUEUED.value},
            )
        else:
            logger.debug(
                "queued_batches_fetched",
                worker_identity=self.worker_identity,
                count=0,
                database_id=getattr(db, "database_id", ""),
                project_id=getattr(db, "project_id", ""),
                collection="batches",
                query_filter={"status": BatchStatus.QUEUED.value},
            )

        claimed_items: list[tuple[str, str, str, str, dict[str, Any]]] = []
        batch_service = BatchService(db, self.settings)
        while len(claimed_items) < available:
            claimed_doc = await batch_service.claim_next_item(
                cancelled_project_ids=self._cancelled_projects,
            )
            if claimed_doc is None:
                break
            item_id = str(claimed_doc.get("id") or "")
            batch_id = str(claimed_doc.get("batch_id") or "")
            asset_id = str(claimed_doc.get("asset_id") or "")
            batch_doc = await db.batches.find_one({"id": batch_id})
            if not item_id:
                continue
            if not batch_doc:
                await batch_service.complete_item(
                    item_id=item_id,
                    status=JobItemStatus.FAILED.value,
                    error_message="ORPHANED: parent batch disappeared after claim",
                )
                continue
            project_id = str(batch_doc.get("project_id", ""))

            if project_id in self._cancelled_projects:
                await batch_service.complete_item(
                    item_id=item_id,
                    status=JobItemStatus.CANCELLED.value,
                    error_message="Project cancelled before worker dispatch",
                )
                continue

            if asset_id:
                await db.assets.update_one(
                    {"id": asset_id},
                    {"$set": {"status": AssetStatus.PROCESSING.value, "updated_at": now}},
                )

            logger.info(
                "worker_claimed",
                job_item_id=item_id,
                batch_id=batch_id,
                asset_id=asset_id,
                worker_identity=self.worker_identity,
            )
            logger.info(
                "job_claimed",
                job_item_id=item_id,
                asset_id=asset_id,
                batch_id=batch_id,
                previous_status=JobItemStatus.QUEUED.value,
                new_status=JobItemStatus.RUNNING.value,
                worker_identity=self.worker_identity,
                batch_execution_trigger_source=batch_doc.get("batch_creation_source", "unknown"),
                trigger_type=("recovery" if batch_doc.get("recovered_from_restart") else "user_request"),
            )
            logger.info(
                "job_item_claimed",
                job_item_id=item_id,
                batch_id=batch_id,
                worker_identity=self.worker_identity,
            )
            logger.info(
                "job_item_processing_started",
                job_item_id=item_id,
                batch_id=batch_id,
                worker_identity=self.worker_identity,
            )
            claimed_items.append((item_id, batch_id, project_id, asset_id, batch_doc))

        # Check for batches that have no remaining queued or running items and finalize them
        active_batches = await db.batches.find({
            "status": {"$in": [BatchStatus.QUEUED.value, BatchStatus.RUNNING.value]}
        }).sort("created_at", 1).to_list(length=10)
        for b_doc in active_batches:
            b_id = b_doc.get("id")
            if not b_id:
                continue
            q_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.QUEUED.value})
            r_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.RUNNING.value})
            if q_cnt == 0 and r_cnt == 0:
                tot_cnt = await db.job_items.count_documents({"batch_id": b_id})
                comp_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.SUCCEEDED.value})
                fail_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.FAILED.value})
                review_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.HUMAN_REVIEW.value})
                if tot_cnt == 0 or (comp_cnt + fail_cnt + review_cnt >= tot_cnt):
                    finalized_doc = await BatchService(db, self.settings).finalize_batch(b_id)
                    logger.info(
                        "batch_processing_completed",
                        batch_id=b_id,
                        worker_id=self.worker_identity,
                        worker_identity=self.worker_identity,
                        duration_ms=0,
                        resulting_state=finalized_doc.get("status") if finalized_doc else BatchStatus.SUCCEEDED.value,
                    )

        for item_id, batch_id, project_id, asset_id, batch_doc in claimed_items:
            try:
                task = asyncio.create_task(
                    self._run_guarded(item_id, batch_id),
                    name=f"job-{item_id}",
                )
                self._job_tasks[item_id] = (project_id, batch_id, task)
                logger.info(
                    "batch_execution_dispatch",
                    batch_id=batch_id,
                    job_item_id=item_id,
                    asset_id=asset_id,
                    batch_execution_trigger_source=(batch_doc or {}).get("batch_creation_source", "unknown"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "batch_execution_exception",
                    batch_id=batch_id,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                    traceback=traceback.format_exc(),
                )
        return len(claimed_items) > 0

    async def _run_guarded(self, item_id: str, batch_id: str) -> None:
        async with self._semaphore:
            self._active += 1
            try:
                await self._process_item(item_id, batch_id)
            except Exception as exc:  # noqa: BLE001
                if _is_transient_db_error(exc):
                    logger.warning(
                        "job_item_retryable_database_error",
                        batch_id=batch_id,
                        job_item_id=item_id,
                        project_id="",
                        attempt=1,
                        max_attempts=self.settings.retry_count,
                        exception_type=type(exc).__name__,
                        error=str(exc),
                    )
                    max_rec_attempts = 3
                    for rec_att in range(1, max_rec_attempts + 1):
                        try:
                            logger.warning(
                                "job_item_state_retry",
                                batch_id=batch_id,
                                job_item_id=item_id,
                                project_id="",
                                attempt=rec_att,
                                max_attempts=max_rec_attempts,
                                exception_type=type(exc).__name__,
                                error=str(exc),
                            )
                            db = self.db or get_database()
                            await db.job_items.update_one(
                                {"id": item_id},
                                {"$set": {"status": JobItemStatus.QUEUED.value, "started_at": None}, "$inc": {"attempt": 1}},
                            )
                            break
                        except Exception as rec_exc:
                            if rec_att < max_rec_attempts:
                                await asyncio.sleep(0.5 * (2 ** (rec_att - 1)))
                    return

                logger.exception("job_item_unhandled_error", job_id=item_id, batch_id=batch_id)
                logger.error(
                    "batch_execution_exception",
                    batch_id=batch_id,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                    traceback=traceback.format_exc(),
                )
                try:
                    db = self.db or get_database()
                    logger.info(
                        "job_item_processing_failed",
                        job_item_id=item_id,
                        batch_id=batch_id,
                        worker_identity=self.worker_identity,
                        duration_ms=0,
                        error=str(exc),
                        resulting_state=JobItemStatus.FAILED.value,
                    )
                    await BatchService(db, self.settings).complete_item(
                        item_id=item_id,
                        status=JobItemStatus.FAILED.value,
                        error_message=f"Unhandled worker error: {exc}",
                    )
                    batch_doc = await db.batches.find_one({"id": batch_id})
                    if batch_doc and batch_doc.get("status") in (BatchStatus.SUCCEEDED.value, BatchStatus.FAILED.value, BatchStatus.PARTIAL_SUCCESS.value, "partially_failed"):
                        logger.info(
                            "batch_processing_completed",
                            batch_id=batch_id,
                            worker_identity=self.worker_identity,
                            duration_ms=0,
                            resulting_state=batch_doc.get("status"),
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("job_item_fail_recovery_failed", job_id=item_id)
            finally:
                self._active -= 1
                self._job_tasks.pop(item_id, None)

    async def _fail_item(
        self,
        session: Any,
        item: Any,
        batch_id: str,
        error_message: str,
        duration_ms: int = 0,
        asset_id: str | None = None,
    ) -> None:
        item_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
        if not item_id:
            return
        db = self.db or get_database()
        logger.info(
            "job_item_processing_failed",
            job_item_id=item_id,
            batch_id=batch_id,
            asset_id=asset_id or getattr(item, "asset_id", None) or (item.get("asset_id") if isinstance(item, dict) else None),
            worker_identity=self.worker_identity,
            duration_ms=duration_ms,
            error=error_message,
            resulting_state=JobItemStatus.FAILED.value,
        )
        await BatchService(db, self.settings).complete_item(
            item_id=item_id,
            status=JobItemStatus.FAILED.value,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        batch_doc = await db.batches.find_one({"id": batch_id})
        if batch_doc and batch_doc.get("status") in (BatchStatus.SUCCEEDED.value, BatchStatus.FAILED.value, BatchStatus.PARTIAL_SUCCESS.value, "partially_failed"):
            logger.info(
                "batch_processing_completed",
                batch_id=batch_id,
                worker_identity=self.worker_identity,
                duration_ms=duration_ms,
                resulting_state=batch_doc.get("status"),
            )

    async def _should_stop_for_project(
        self, session: Any, job_id: str, project_id: str, batch_id: str | None = None
    ) -> bool:
        if project_id in self._cancelled_projects:
            logger.info(
                "worker_stopping_cancelled_project",
                job_id=job_id,
                project_id=project_id,
            )
            return True
        max_attempts = 3
        project_exists = None
        item_doc = None
        state_check_failed = False
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                project_exists = await session.get(ProjectRow, project_id)
                item_doc = await session.get(JobItemRow, job_id)
                state_check_failed = False
                break
            except Exception as exc:
                if not _is_transient_db_error(exc):
                    raise
                last_exc = exc
                state_check_failed = True
                logger.warning(
                    "project_state_check_retry",
                    batch_id=batch_id or "",
                    job_item_id=job_id,
                    project_id=project_id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    exception_type=type(exc).__name__,
                    error=str(exc),
                )
                if attempt < max_attempts:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

        if state_check_failed:
            logger.warning(
                "project_state_check_transient_unavailable",
                batch_id=batch_id or "",
                job_item_id=job_id,
                project_id=project_id,
                exception_type=type(last_exc).__name__ if last_exc else "Unknown",
                error=str(last_exc),
            )
            return False
        # item_doc already retrieved in retry block
        item_status = item_doc.status if item_doc else None
        if project_exists is None:
            logger.warning(
                "worker_project_not_found",
                job_id=job_id,
                project_id=project_id,
                action="failing_job_item",
            )
            if batch_id and item_doc is not None:
                await self._fail_item(
                    session,
                    item_doc,
                    batch_id,
                    f"PROJECT_NOT_FOUND: project {project_id} no longer exists",
                )
            return True
        if item_status == JobItemStatus.CANCELLED.value:
            logger.info(
                "worker_stopping_cancelled_job",
                job_id=job_id,
                project_id=project_id,
            )
            return True
        return False

    def _workflow_steps(self, batch: BatchRow) -> list[dict[str, Any]]:
        workflow = list(batch.workflow or [])
        if workflow:
            return workflow
        return [
            {
                "key": "yolo26",
                "purpose": "Primary detection",
                "required": True,
                "model_id": batch.model_id or self.settings.yolo26_model_id,
            }
        ]

    async def _process_item(self, item_id: str, batch_id: str) -> None:
        start = time.perf_counter()
        logger.info("job_item_start", job_id=item_id, batch_id=batch_id)
        async with self.session_factory() as session:
            item = await session.get(JobItemRow, item_id)
            batch = await session.get(BatchRow, batch_id)
            if item is None:
                logger.error("job_item_not_found", job_id=item_id, batch_id=batch_id)
                return
            if batch is None:
                logger.error("batch_not_found_for_job_item", job_id=item_id, batch_id=batch_id)
                db = self.db or get_database()
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.FAILED.value,
                    error_message=f"BATCH_NOT_FOUND: batch {batch_id} not found",
                )
                return
            logger.info(
                "job_execution_started",
                job_id=item_id,
                job_item_id=item_id,
                batch_id=batch_id,
                asset_id=getattr(item, "asset_id", None),
                execution_id=None,
                batch_execution_trigger_source=getattr(batch, "batch_creation_source", None),
                trigger_type=(
                    "recovery" if getattr(batch, "recovered_from_restart", False)
                    else "user_request"
                ),
            )
            db = self.db or get_database()
            persisted_batch = await db.batches.find_one({"id": batch_id})
            item_batch_id = str(getattr(item, "batch_id", "") or "")
            item_asset_id = str(getattr(item, "asset_id", "") or "")
            batch_asset_ids = {
                str(value) for value in ((persisted_batch or {}).get("asset_ids") or [])
            }
            if (
                persisted_batch is None
                or item_batch_id != str(persisted_batch.get("id") or "")
                or not item_asset_id
                or item_asset_id not in batch_asset_ids
            ):
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    "JOB_ITEM_IDENTITY_MISMATCH: item does not belong to its persisted batch asset set",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    asset_id=item_asset_id or None,
                )
                return
            if persisted_batch.get("explicit_ai_annotation_trigger") is not True:
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    "UNAUTHORIZED_BATCH: explicit AI annotation trigger is missing",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    asset_id=item_asset_id,
                )
                return
            if persisted_batch.get("status") != BatchStatus.RUNNING.value:
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.CANCELLED.value,
                    error_message="Batch became inactive before worker execution",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
                return

            item_asset_id = getattr(item, "asset_id", None)
            asset = await session.get(AssetRow, item_asset_id) if item_asset_id else None
            # Capture primitives to avoid using ORM objects after a failed transaction
            primitive_item_id = getattr(item, "id", item_id)
            primitive_asset_id = getattr(asset, "id", None) if asset is not None else None
            primitive_project_id = getattr(batch, "project_id", None)
            primitive_attempt = getattr(item, "attempt", 0) or 0
            if str(item_asset_id) != str(primitive_asset_id):
                logger.critical(
                    "asset_identity_violation",
                    project_id=primitive_project_id,
                    batch_id=batch_id,
                    job_item_id=primitive_item_id,
                    job_item_asset_id=item_asset_id,
                    loaded_asset_id=primitive_asset_id,
                    worker_identity=self.worker_identity,
                )
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    "ASSET_IDENTITY_VIOLATION: job item and loaded asset differ",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    asset_id=primitive_asset_id,
                )
                return
            project = await session.get(ProjectRow, primitive_project_id) if primitive_project_id else None
            if asset is None:
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    "Asset missing",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
                return

            if project is None:
                logger.warning(
                    "worker_project_not_found",
                    job_id=item_id,
                    project_id=primitive_project_id,
                    action="failing_job_item",
                )
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    f"PROJECT_NOT_FOUND: project {primitive_project_id} no longer exists",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
                return

            # A new batch/job item must not cause an already completed asset to
            # execute again.  This guard is intentionally before scene analysis,
            # agent startup, and model execution.
            persisted_annotations = await db.annotations.find({
                "asset_id": primitive_asset_id,
                "source": "ai",
            }).to_list(length=100000)
            matching_persisted_result = next(
                (
                    row for row in persisted_annotations
                    if str((row.get("provenance") or {}).get("batch_id") or "") == str(batch_id)
                    or str((row.get("provenance") or {}).get("job_item_id") or "") == str(item_id)
                ),
                None,
            )
            if matching_persisted_result:
                existing_execution_id = str(
                    (matching_persisted_result.get("provenance") or {}).get("execution_id")
                    or (matching_persisted_result.get("provenance") or {}).get("agent_run_id")
                    or item_id
                )
                logger.info(
                    "execution_skipped_existing_result",
                    asset_id=primitive_asset_id,
                    job_item_id=item_id,
                    batch_id=batch_id,
                    existing_execution_id=existing_execution_id,
                    existing_status=JobItemStatus.SUCCEEDED.value,
                    reason="persisted_result_matches_current_batch_or_job_item",
                )
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.SUCCEEDED.value,
                    error_message="Skipped: persisted result already exists for this execution",
                    duration_ms=0,
                )
                return
            terminal_statuses = {
                JobItemStatus.SUCCEEDED.value,
                JobItemStatus.HUMAN_REVIEW.value,
                "completed",
            }
            prior_items = await db.job_items.find({"asset_id": primitive_asset_id}).to_list(length=100000)
            prior_terminal = []
            prior_active_same_batch = []
            for prior in prior_items:
                if str(prior.get("id")) == str(item_id):
                    continue
                prior_batch_id = str(prior.get("batch_id") or "")
                if prior_batch_id == str(batch_id) and prior.get("status") == JobItemStatus.RUNNING.value:
                    prior_active_same_batch.append(prior)
                    continue
                if prior.get("status") not in terminal_statuses or not prior_batch_id:
                    continue
                prior_batch = await db.batches.find_one({"id": prior_batch_id})
                if prior_batch and str(prior_batch.get("project_id")) == str(primitive_project_id):
                    prior_terminal.append(prior)

            if prior_terminal and persisted_batch.get("explicit_ai_annotation_trigger") is not True:
                existing = prior_terminal[0]
                existing_execution_id = str(existing.get("execution_id") or existing.get("agent_run_id") or existing.get("id"))
                logger.info(
                    "execution_skipped_existing_result",
                    asset_id=primitive_asset_id,
                    job_item_id=item_id,
                    batch_id=batch_id,
                    existing_execution_id=existing_execution_id,
                    existing_status=existing.get("status"),
                    existing_job_item_id=existing.get("id"),
                    reason="terminal_job_item_exists_without_explicit_reprocess",
                )
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.SUCCEEDED.value,
                    error_message="Skipped: existing terminal result reused",
                    detection_count=int(existing.get("detection_count", 0) or 0),
                    duration_ms=0,
                )
                return

            if prior_active_same_batch:
                logger.info(
                    "duplicate_claim_prevented",
                    job_item_id=item_id,
                    asset_id=primitive_asset_id,
                    batch_id=batch_id,
                    existing_status=JobItemStatus.RUNNING.value,
                    existing_job_item_id=prior_active_same_batch[0].get("id"),
                    worker_id=self.worker_identity,
                    reason="same_asset_already_running_in_batch",
                )
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.CANCELLED.value,
                    error_message="Skipped duplicate job item: same asset is already running",
                    duration_ms=0,
                )
                return

            if await self._should_stop_for_project(session, item_id, batch.project_id, batch_id=batch_id):
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.CANCELLED.value,
                    error_message="Job cancelled before inference started",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
                return

            # Model availability is determined once and reused by the
            # dynamic planner and execution loop.
            statuses = {}
            if self.runtime is not None:
                statuses = {s.key: s.availability for s in self.runtime.registry.status()}
            logger.info("model_availability", **statuses)

            enabled_map = {
                "yolo26": self.settings.yolo26_enabled and statuses.get("yolo26") != ModelAvailability.UNAVAILABLE.value,
                "faster_rcnn": self.settings.faster_rcnn_enabled and statuses.get("faster_rcnn") != ModelAvailability.UNAVAILABLE.value,
                "dino": self.settings.dino_enabled and statuses.get("dino") != ModelAvailability.UNAVAILABLE.value,
                "florence": self.settings.florence_enabled and statuses.get("florence") != ModelAvailability.UNAVAILABLE.value,
                "sam2": self.settings.sam2_enabled and statuses.get("sam2") != ModelAvailability.UNAVAILABLE.value,
            }

            labels = list(getattr(project, "labels", None) or [])
            ontology = list(getattr(project, "label_ontology", None) or [])
            asset_sp = (
                getattr(asset, "storage_path", None)
                or (asset.get("storage_path") if isinstance(asset, dict) else None)
                or (asset.get("file_path") if isinstance(asset, dict) else None)
                or (asset.get("path") if isinstance(asset, dict) else None)
                or ""
            )
            path = self.storage.resolve(asset_sp)
            stored_filename = (
                getattr(asset, "filename", None)
                or getattr(asset, "original_filename", None)
                or (asset.get("filename") if isinstance(asset, dict) else None)
                or (asset.get("original_filename") if isinstance(asset, dict) else None)
            )
            resolved_modality = resolve_asset_modality(asset, project, path)

            logger.info(
                "asset_modality_resolved",
                asset_id=primitive_asset_id,
                project_id=primitive_project_id,
                modality=resolved_modality,
                content_type=(
                    getattr(asset, "content_type", None)
                    or getattr(asset, "mime_type", None)
                    or (asset.get("content_type") if isinstance(asset, dict) else None)
                    or (asset.get("mime_type") if isinstance(asset, dict) else None)
                    or "unknown"
                ),
                stored_filename=stored_filename,
                resolved_path=str(path),
            )

            text_task_type = None
            text_target_objects: list[str] = []
            if resolved_modality in {"text", "document"}:
                text_task_type, text_target_objects = resolve_text_project_configuration(project)
                labels = list(text_target_objects)
                logger.info(
                    "worker_text_configuration_resolved",
                    project_id=primitive_project_id,
                    asset_id=primitive_asset_id,
                    modality=resolved_modality,
                    task_type=text_task_type,
                    target_objects=text_target_objects,
                )

            project_snapshot = {
                "id": primitive_project_id,
                "labels": labels,
                "target_labels": list(labels),
                "label_ontology": ontology,
                "target_objects": text_target_objects if resolved_modality in {"text", "document"} else None,
                "quality_policy": dict(getattr(project, "quality_policy", None) or {}),
                "task_type": text_task_type if resolved_modality in {"text", "document"} else (getattr(project, "task_type", None) or "object_detection"),
                "modality": resolved_modality,
                "goal": getattr(project, "goal", None) or "",
            }
            configured_task = str(project_snapshot.get("task_type") or "").strip().lower()
            configured_geometry = {
                "object_detection": "box",
                "detection": "box",
                "segmentation": "polygon",
                "instance_segmentation": "polygon",
                "classification": "classification",
            }.get(configured_task, "text_span" if resolved_modality in {"text", "document"} else "box")
            configured_categories = [
                str(item.get("name"))
                for item in ontology
                if isinstance(item, dict) and item.get("name")
            ]
            logger.info(
                "project_configuration_loaded",
                project_id=primitive_project_id,
                batch_id=batch_id,
                job_id=item_id,
                job_item_id=item_id,
                asset_id=primitive_asset_id,
                modality=resolved_modality,
                annotation_type=project_snapshot.get("task_type"),
                target_labels=list(labels),
                target_categories=configured_categories,
                geometry=configured_geometry,
                source="current_project_configuration",
            )
            modality = resolved_modality
            asset_snapshot = {
                "id": primitive_asset_id,
                "width": getattr(asset, "width", 0),
                "height": getattr(asset, "height", 0),
                "storage_path": getattr(asset, "storage_path", ""),
            }
            ont_index = build_ontology_index(labels, ontology=ontology)
            source_plan = build_label_source_plan(
                ont_index,
                yolo_enabled=enabled_map["yolo26"],
                dino_enabled=enabled_map["dino"],
            )

            # Pre-inference validation
            file_exists = path.exists() and path.is_file()
            file_size = path.stat().st_size if file_exists else 0

            logger.info(
                "asset_file_resolved",
                asset_id=primitive_asset_id,
                project_id=primitive_project_id,
                stored_filename=stored_filename,
                resolved_path=str(path),
                exists=file_exists,
                file_size=file_size,
            )

            if not file_exists or file_size == 0:
                logger.error(
                    "asset_file_not_found_or_empty",
                    asset_id=primitive_asset_id,
                    project_id=primitive_project_id,
                    resolved_path=str(path),
                    exists=file_exists,
                    file_size=file_size,
                )
                duration_ms = int((time.perf_counter() - start) * 1000)
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    f"ASSET_FILE_NOT_FOUND_OR_EMPTY: {path} (exists={file_exists}, size={file_size})",
                    duration_ms=duration_ms,
                    asset_id=primitive_asset_id,
                )
                return

            t_scene_start = time.perf_counter()
            if modality in {"text", "document"}:
                logger.info(
                    "text_batch_execution_dispatch",
                    asset_id=primitive_asset_id,
                    project_id=primitive_project_id,
                    batch_id=batch_id,
                    job_id=item_id,
                    resolved_path=str(path),
                )
                scene_evidence = _SceneEvidence(
                    image_width=0,
                    image_height=0,
                    megapixels=0.0,
                    large_image=False,
                    priority_labels=tuple(labels),
                    metadata={
                        "modality": "text",
                        "project_id": batch.project_id,
                        "task_type": getattr(project, "task_type", "sentiment_analysis") if project else "entity_extraction",
                        "segmentation_required": False,
                        "text_required": True,
                    },
                )
            elif modality == "video":
                discovery_started = time.perf_counter()
                # Release the read transaction opened while loading context
                # before decode, model inference, tracking, or verification.
                await commit_with_retry(session)
                logger.info(
                    "discovery_started",
                    asset_id=asset.id,
                    batch_id=batch_id,
                    duration_ms=0,
                )
                logger.info(
                    "video_inference_transaction_released",
                    asset_id=asset.id,
                    batch_id=batch_id,
                )
                # Video discovery: read metadata using cv2
                import cv2
                cap = cv2.VideoCapture(str(path))
                if not cap.isOpened():
                    raise RuntimeError(f"Could not open video file {path}")
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = frame_count / fps if fps > 0 else 0.0

                # Extract first frame (frame 0) to a temp file for scene inspection
                import tempfile
                ret, first_frame = cap.read()
                cap.release()

                if ret:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_f:
                        first_frame_path = Path(tmp_f.name)
                    cv2.imwrite(str(first_frame_path), first_frame)
                    try:
                        scene_evidence = await self._inspect_scene(
                            path=first_frame_path,
                            asset_id=asset.id,
                            priority_labels=tuple(labels),
                            use_florence=False,
                            use_agent_scene=False,
                        )
                    finally:
                        if first_frame_path.exists():
                            first_frame_path.unlink()
                else:
                    scene_evidence = _SceneEvidence(
                        image_width=width,
                        image_height=height,
                        priority_labels=tuple(labels),
                    )

                # Merge metadata
                import dataclasses
                scene_evidence = dataclasses.replace(
                    scene_evidence,
                    image_width=width,
                    image_height=height,
                    metadata={
                        **(scene_evidence.metadata or {}),
                        "modality": "video",
                        "fps": fps,
                        "frame_count": frame_count,
                        "duration": duration,
                        "segmentation_required": project.task_type == "segmentation" if project else False,
                        "text_required": False,
                    }
                )
                project_snapshot["scene_evidence"] = {
                    "scene_type": scene_evidence.scene_type,
                    "object_density": scene_evidence.object_density,
                    "small_object_ratio": scene_evidence.small_object_ratio,
                    "expected_object_count": scene_evidence.expected_object_count,
                    "aerial": scene_evidence.aerial,
                    "crowded": scene_evidence.crowded,
                    "metadata": dict(scene_evidence.metadata or {}),
                }

                logger.info(
                    "video_metadata_loaded",
                    asset_id=asset.id,
                    width=width,
                    height=height,
                    fps=fps,
                    frame_count=frame_count,
                    duration=duration,
                )
                logger.info(
                    "discovery_completed",
                    asset_id=asset.id,
                    batch_id=batch_id,
                    frame_count=frame_count,
                    duration_ms=int((time.perf_counter() - discovery_started) * 1000),
                )
            elif modality == "image":
                logger.info(
                    "image_batch_execution_dispatch",
                    asset_id=primitive_asset_id,
                    project_id=primitive_project_id,
                    batch_id=batch_id,
                    job_id=item_id,
                    resolved_path=str(path),
                )
                scene_evidence = await self._inspect_scene(
                    path=path,
                    asset_id=asset.id,
                    priority_labels=tuple(labels),
                    use_florence=False,
                    use_agent_scene=False,
                )
                import dataclasses
                scene_evidence = dataclasses.replace(
                    scene_evidence,
                    metadata={
                        **(scene_evidence.metadata or {}),
                        "modality": "image",
                        "project_id": batch.project_id,
                        "annotation_intent": "instance_segmentation" if project and getattr(project, "task_type", "") == "segmentation" else "object_detection",
                        "task_type": getattr(project, "task_type", "object_detection") if project else "object_detection",
                        "segmentation_required": getattr(project, "task_type", "") == "segmentation" if project else False,
                        "text_required": False,
                    }
                )
            else:
                duration_ms = int((time.perf_counter() - start) * 1000)
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    f"UNSUPPORTED_ASSET_MODALITY: {modality} for file {stored_filename}",
                    duration_ms=duration_ms,
                    asset_id=primitive_asset_id,
                )
                return
            scene_analysis_ms = (time.perf_counter() - t_scene_start) * 1000.0

            if await self._should_stop_for_project(session, item_id, batch.project_id):
                await BatchService(self.db or get_database(), self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.CANCELLED.value,
                    error_message="Job cancelled before model execution",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
                return

            # Execute standard image production annotation request through the LangGraph Agentic Pipeline
            from app.agent.graphs.agentic_pipeline_graph import run_agentic_pipeline_graph

            user_prompt = (
                getattr(batch, "user_request", None)
                or getattr(batch, "prompt", None)
                or (getattr(project, "goal", "") if project else "")
                or f"Identify all relevant objects in the image according to the project ontology: {', '.join(labels)}."
            )

            # End the read transaction before any agent/model work without
            # expiring the ORM objects passed to the graph. The graph opens
            # its own short write transaction only when persisting.
            await commit_with_retry(session)

            graph_res = await run_agentic_pipeline_graph(
                project=project,
                asset=asset,
                user_request=user_prompt,
                session=session,
                storage=self.storage,
                runtime=self.runtime,
                batch_id=batch_id,
                job_id=item_id,
                project_id=primitive_project_id,
                asset_id=primitive_asset_id,
                project_snapshot=project_snapshot,
                asset_snapshot=asset_snapshot,
                )

            invalid_plan = graph_res.get("agent_plan_invalid")
            if invalid_plan:
                duration_ms = int((time.perf_counter() - start) * 1000)
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    str(invalid_plan),
                    duration_ms=duration_ms,
                    asset_id=primitive_asset_id,
                )
                logger.error(
                    "job_item_failed_agent_plan",
                    job_id=item_id,
                    batch_id=batch_id,
                    asset_id=asset.id,
                    agent_plan_invalid=invalid_plan,
                )
                return

            merged_count = (
                len(graph_res.get("merged_detections", []))
                or len(graph_res.get("text_annotations", []))
                or int(graph_res.get("persisted_count", 0))
            )
            if graph_res.get("execution_failed"):
                error_message = "; ".join(
                    str(error.get("model")) + ": " + str(error.get("error"))
                    for error in graph_res.get("execution_errors", [])
                ) or "Model execution failed"
                duration_ms = int((time.perf_counter() - start) * 1000)
                await self._fail_item(
                    session,
                    item,
                    batch_id,
                    error_message,
                    duration_ms=duration_ms,
                    asset_id=primitive_asset_id,
                )
                logger.error(
                    "job_item_failed_execution",
                    job_id=item_id,
                    batch_id=batch_id,
                    asset_id=asset.id,
                    execution_errors=graph_res.get("execution_errors", []),
                )
                return

            # A verification HUMAN_REVIEW result is persisted for HITL, but
            # must not be converted into a completed/succeeded job item.
            final_review_status = str(graph_res.get("final_status") or "").lower()
            if final_review_status in {
                ReviewStatus.HUMAN_REVIEW.value,
                ReviewStatus.HUMAN_REVIEW_REQUIRED.value,
                ReviewStatus.REVIEW.value,
            }:
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.HUMAN_REVIEW.value,
                    error_message="Awaiting human review",
                    detection_count=merged_count,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
                logger.info(
                    "job_item_hitl_required",
                    job_item_id=item_id,
                    batch_id=batch_id,
                    asset_id=primitive_asset_id,
                    final_decision="HUMAN_REVIEW",
                    review_status=final_review_status,
                    resulting_state=JobItemStatus.HUMAN_REVIEW.value,
                    persistence_status="readback_verified",
                )
                return

            duration_ms = int((time.perf_counter() - start) * 1000)
            db = self.db or get_database()
            await BatchService(db, self.settings).complete_item(
                item_id=item_id,
                status=JobItemStatus.SUCCEEDED.value,
                detection_count=merged_count,
                duration_ms=duration_ms,
            )
            logger.info(
                "job_item_processing_completed",
                job_item_id=item_id,
                batch_id=batch_id,
                asset_id=primitive_asset_id,
                worker_identity=self.worker_identity,
                duration_ms=duration_ms,
                final_detection_count=merged_count,
                persisted_annotation_count=getattr(graph_res.get("audit_record"), "persisted_annotation_count", merged_count),
                resulting_state=JobItemStatus.SUCCEEDED.value,
            )
            logger.info(
                "asset_annotation_lifecycle",
                project_id=primitive_project_id,
                batch_id=batch_id,
                job_item_id=item_id,
                asset_id=primitive_asset_id,
                worker=self.worker_identity,
                inference_started=True,
                inference_completed=True,
                final_detection_count=merged_count,
                persisted_annotation_count=getattr(graph_res.get("audit_record"), "persisted_annotation_count", merged_count),
                status=JobItemStatus.SUCCEEDED.value,
            )
            batch_doc = await db.batches.find_one({"id": batch_id})
            if batch_doc and batch_doc.get("status") in (BatchStatus.SUCCEEDED.value, BatchStatus.FAILED.value, BatchStatus.PARTIAL_SUCCESS.value, "partially_failed"):
                logger.info(
                    "batch_processing_completed",
                    batch_id=batch_id,
                    worker_identity=self.worker_identity,
                    duration_ms=duration_ms,
                    resulting_state=batch_doc.get("status"),
                )

            persist_ms = float(graph_res.get("timings", {}).get("persistence_ms", 0.0))

            graph_timings = graph_res.get("timings", {})
            agent_planning_ms = float(graph_timings.get("agent_planning_ms", 0.0))
            inference_ms = float(graph_timings.get("yolo_ms", 0.0) + graph_timings.get("dino_ms", 0.0) + graph_timings.get("faster_rcnn_ms", 0.0) + graph_timings.get("fusion_ms", 0.0) + graph_timings.get("sam2_ms", 0.0))
            verification_ms = float(graph_timings.get("quality_ms", 0.0))
            total_asset_ms = (time.perf_counter() - start) * 1000.0

            logger.info(
                "asset_processing_timing",
                job_id=item_id,
                asset_id=primitive_asset_id,
                batch_id=batch_id,
                agent_planning_ms=round(agent_planning_ms, 2),
                scene_analysis_ms=round(scene_analysis_ms, 2),
                inference_ms=round(inference_ms, 2),
                verification_ms=round(verification_ms, 2),
                persistence_ms=round(persist_ms, 2),
                total_asset_ms=round(total_asset_ms, 2),
            )

            logger.info(
                "job_item_completed_agentic",
                job_id=item_id,
                asset_id=primitive_asset_id,
                batch_id=batch_id,
                detection_count=merged_count,
                duration_ms=duration_ms,
            )
            logger.info(
                "job_item_completed",
                job_id=item_id,
                job_item_id=item_id,
                asset_id=primitive_asset_id,
                batch_id=batch_id,
                detection_count=merged_count,
            )
            return

            decode_time_ms = 0
            preprocessing_time_ms = 0
            yolo_time_ms = 0
            yolo_recall_time_ms = 0
            dino_time_ms = 0
            dino_recall_time_ms = 0
            nms_time_ms = 0
            fusion_time_ms = 0

            second_pass_reason = "Not evaluated"
            second_pass_evidence: dict[str, Any] = {}
            total_detections = 0
            all_detections: list[Any] = []
            completed_models: list[str] = []
            executed_models: list[str] = []
            failed_models: list[str] = []
            mask_count = 0
            step_errors: list[str] = []

            detection_started = time.perf_counter()
            try:
                if await self._should_stop_for_project(session, item_id, batch.project_id):
                    return
                # Lightweight Vision Orchestrator: scene understanding, iterative detection,
                # targeted open-vocab refinement, and optional segmentation.
                # Run optional Florence caption/label assist first to get scene hints.
                florence_suggestions: list[str] = []
                if enabled_map.get("florence", False) and "florence" in execution_plan.models:
                    executed_models.append("florence")
                    run = ModelRunRow(
                        job_item_id=item_id,
                        batch_id=batch_id,
                        asset_id=asset.id,
                        model_key="florence",
                        model_id=str(batch.model_id or "florence"),
                        status=ModelRunStatus.RUNNING.value,
                        purpose="Scene understanding / label assist",
                        started_at=datetime.now(UTC),
                    )
                    session.add(run)
                    await commit_with_retry(session)
                    run_start = time.perf_counter()
                    try:
                        # Call Florence adapter directly to obtain label suggestions for scene understanding.
                        if self.runtime is None:
                            raise RuntimeError("Florence requires inference runtime")
                        registry = self.runtime.registry
                        adapter = registry.get("florence")
                        if not registry.try_load("florence"):
                            raise RuntimeError("Florence unavailable")
                        suggestion = await asyncio.to_thread(
                            adapter.assist, path, asset_id=asset.id, labels=labels, goal="", strategy="detailed"
                        )
                        duration_ms = int((time.perf_counter() - run_start) * 1000)
                        run.model_id = adapter.model_id
                        run.detection_count = 0
                        run.mask_count = 0
                        run.duration_ms = duration_ms
                        run.status = ModelRunStatus.SUCCEEDED.value
                        run.finished_at = datetime.now(UTC)
                        session.add(
                            UsageEventRow(
                                project_id=batch.project_id,
                                kind="cv_inference",
                                model_id=adapter.model_id,
                                asset_id=asset.id,
                                batch_id=batch_id,
                                duration_ms=duration_ms,
                                detection_count=0,
                                tokens_in=0,
                                tokens_out=0,
                                cost_usd=None,
                            )
                        )
                        if suggestion and getattr(suggestion, "labels", None):
                            approved = {
                                str(name).strip()
                                for name in ont_index.canonical_names
                                if str(name).strip()
                            }
                            florence_suggestions = [
                                str(name).strip()
                                for name in suggestion.labels
                                if str(name).strip() in approved
                            ]
                        if "florence" not in completed_models:
                            completed_models.append("florence")
                    except Exception as exc:  # noqa: BLE001
                        failed_models.append("florence")
                        duration_ms = int((time.perf_counter() - run_start) * 1000)
                        run.duration_ms = duration_ms
                        run.error_message = str(exc)
                        run.finished_at = datetime.now(UTC)
                        run.status = (
                            ModelRunStatus.UNAVAILABLE.value
                            if "unavailable" in str(exc).lower()
                            or "not installed" in str(exc).lower()
                            else ModelRunStatus.FAILED.value
                        )
                        logger.warning(
                            "model_run_failed",
                            job_id=item_id,
                            model_key="florence",
                            model_run_id=run.id,
                            error=str(exc),
                            required=False,
                        )

                # Iterative agentic detection loop. A second/third round is
                # used for evidence-driven refinement, not for blindly lowering
                # confidence thresholds.
                MAX_ROUNDS = 3
                round_idx = 0
                requested_dino_labels: set[str] = set()

                while round_idx < MAX_ROUNDS:
                    round_idx += 1

                    logger.info(
                        "vision_round_start",
                        job_id=item_id,
                        batch_id=batch_id,
                        asset_id=asset.id,
                        round=round_idx,
                        strategy=execution_plan.strategy,
                        image_size=execution_plan.image_size,
                        tile_rows=execution_plan.tile_rows,
                        tile_cols=execution_plan.tile_cols,
                        tile_overlap=execution_plan.tile_overlap,
                        planner_source=execution_plan.planner_source,
                        reason=execution_plan.reason,
                    )

                    # Decide which primary model should run
                    yolo_should_run = (
                        round_idx == 1
                        and enabled_map.get("yolo26", False)
                        and "yolo26" in execution_plan.models
                    )

                    faster_rcnn_should_run = (
                        round_idx == 1
                        and enabled_map.get("faster_rcnn", False)
                        and "faster_rcnn" in execution_plan.models
                        and not yolo_should_run
                    )

                    if yolo_should_run:
                        model_key = "yolo26"
                        executed_models.append("yolo26")
                        logger.info(
                            "yolo_execution_started",
                            job_id=item_id,
                            asset_id=asset.id,
                            yolo_requested_classes=list(source_plan.yolo_canonical),
                            execution_plan_models=list(execution_plan.models),
                        )
                        purpose = (
                            "Closed-vocabulary detection "
                            f"({execution_plan.strategy})"
                        )
                        required = not bool(source_plan.dino_prompt_labels)
                    elif faster_rcnn_should_run:
                        model_key = "faster_rcnn"
                        executed_models.append("faster_rcnn")
                        purpose = (
                            "Fallback closed-vocabulary detection "
                            f"({execution_plan.strategy})"
                        )
                        required = not bool(source_plan.dino_prompt_labels)
                    else:
                        model_key = None

                    # Run YOLO if chosen
                    if model_key:
                        logger.info(
                            "model_execution_start",
                            job_id=item_id,
                            batch_id=batch_id,
                            asset_id=asset.id,
                            model_key=model_key,
                            purpose=purpose,
                        )
                        run = ModelRunRow(
                            job_item_id=item_id,
                            batch_id=batch_id,
                            asset_id=asset.id,
                            model_key=model_key,
                            model_id=str(batch.model_id or model_key),
                            status=ModelRunStatus.RUNNING.value,
                            purpose=purpose,
                            started_at=datetime.now(UTC),
                        )
                        session.add(run)
                        await commit_with_retry(session)
                        run_start = time.perf_counter()
                        try:
                            dets, masks, model_id = await asyncio.to_thread(
                                self._run_model_step,
                                model_key,
                                path,
                                asset.id,
                                labels,
                                all_detections,
                                execution_plan=execution_plan,
                                ont_index=ont_index,
                            )
                            duration_ms = int((time.perf_counter() - run_start) * 1000)
                            if model_key == "yolo26":
                                yolo_time_ms = duration_ms
                            run.model_id = model_id
                            run.detection_count = len(dets)
                            run.mask_count = len(masks)
                            run.duration_ms = duration_ms
                            run.status = ModelRunStatus.SUCCEEDED.value
                            run.finished_at = datetime.now(UTC)
                            total_detections += len(dets)
                            all_detections.extend(dets)
                            if model_key not in completed_models:
                                completed_models.append(model_key)

                            logger.info(
                                "detector_result",
                                model_key=model_key,
                                detections=len(dets),
                            )
                            if model_key == "yolo26":
                                from collections import Counter
                                from app.inference.ontology_map import apply_mapping_to_detection

                                raw_classes = [
                                    str((d.provenance or {}).get("raw_model_label") or d.label)
                                    for d in dets
                                ]
                                mapped_labels: list[str] = []
                                unmapped_count = 0
                                canonical_by_raw: dict[str, str] = {}
                                mapping_details: list[dict[str, Any]] = []
                                for detection in dets:
                                    mapped, _ = apply_mapping_to_detection(detection, ont_index)
                                    raw_label = str(
                                        (detection.provenance or {}).get("raw_model_label")
                                        or detection.label
                                    )
                                    if mapped is None:
                                        unmapped_count += 1
                                    else:
                                        mapped_labels.append(mapped.label)
                                        canonical_by_raw[raw_label] = mapped.label
                                        mapping_details.append({
                                            "raw_class_id": (detection.provenance or {}).get("raw_class_id"),
                                            "raw_class_name": raw_label,
                                            "canonical_class": mapped.label,
                                            "confidence": float(detection.confidence),
                                        })
                                logger.info(
                                    "yolo_detection_diagnostics",
                                    asset_id=asset.id,
                                    yolo_raw_detection_count=len(dets),
                                    yolo_filtered_detection_count=len(mapped_labels),
                                    yolo_class_mapping=canonical_by_raw,
                                    class_mapping_details=mapping_details,
                                    raw_class_ids=[
                                        (d.provenance or {}).get("raw_class_id")
                                        for d in dets
                                    ],
                                    yolo_raw_classes=raw_classes,
                                    yolo_canonical_classes=sorted(set(mapped_labels)),
                                    mapped_count=len(mapped_labels),
                                    unmapped_count=unmapped_count,
                                    suppressed_non_ontology_count=unmapped_count,
                                    canonical_class_counts=dict(Counter(mapped_labels)),
                                    raw_class_names=raw_classes,
                                    raw_confidences=[float(d.confidence) for d in dets],
                                    final_boxes=[d.bbox.model_dump() if hasattr(d.bbox, "model_dump") else str(d.bbox) for d in dets],
                                    yolo_car_detection_count=sum(
                                        1 for d in dets
                                        if str((d.provenance or {}).get("raw_model_label") or d.label).casefold() in {"car", "cars"}
                                    ),
                                )

                            self._log_detection_stage(
                                job_id=item_id,
                                asset_id=asset.id,
                                stage=f"raw_detector_candidates:{model_key}",
                                detections=dets,
                            )

                            if masks:
                                mask_svc = MaskService(session, self.storage)
                                await mask_svc.replace_ai_masks(asset.id, masks)
                            session.add(
                                UsageEventRow(
                                    project_id=batch.project_id,
                                    kind="cv_inference",
                                    model_id=model_id,
                                    asset_id=asset.id,
                                    batch_id=batch_id,
                                    duration_ms=duration_ms,
                                    detection_count=len(dets),
                                    tokens_in=0,
                                    tokens_out=0,
                                    cost_usd=None,
                                )
                            )
                            logger.info(
                                "model_execution_complete",
                                job_id=item_id,
                                batch_id=batch_id,
                                asset_id=asset.id,
                                model_key=model_key,
                                model_run_id=run.id,
                                detections=len(dets),
                                masks=len(masks),
                                duration_ms=duration_ms,
                            )
                            logger.info(
                                "model_run_complete",
                                job_id=item_id,
                                batch_id=batch_id,
                                asset_id=asset.id,
                                model_key=model_key,
                                model_run_id=run.id,
                                detections=len(dets),
                                masks=len(masks),
                                duration_ms=duration_ms,
                            )
                        except Exception as exc:  # noqa: BLE001
                            failed_models.append(model_key)
                            duration_ms = int((time.perf_counter() - run_start) * 1000)
                            run.duration_ms = duration_ms
                            run.error_message = str(exc)
                            run.finished_at = datetime.now(UTC)
                            run.status = (
                                ModelRunStatus.UNAVAILABLE.value
                                if "unavailable" in str(exc).lower()
                                or "not installed" in str(exc).lower()
                                else ModelRunStatus.FAILED.value
                            )
                            step_errors.append(f"{model_key}: {exc}")
                            logger.warning(
                                "model_run_failed",
                                job_id=item_id,
                                model_key=model_key,
                                model_run_id=run.id,
                                error=str(exc),
                                required=required,
                            )
                            if required:
                                raise

                    # ------------------------------------------------------------
                    # Dynamic Coverage Check & Secondary/Tiled Fallbacks
                    # ------------------------------------------------------------
                    if (
                        model_key == "yolo26"
                        and "yolo26" in completed_models
                    ):
                        from app.inference.routing import evaluate_detection_coverage

                        coverage_eval = evaluate_detection_coverage(
                            detections=dets,
                            scene_evidence=scene_evidence,
                            source_plan=source_plan,
                            settings=self.settings,
                            ontology_index=ont_index,
                        )
                        
                        confidences = [float(getattr(d, "confidence", 0.0) or 0.0) for d in dets]
                        logger.info(
                            "vision_coverage_diagnostics",
                            image_id=asset.id,
                            scene_type=str(getattr(scene_evidence, "scene_type", "unknown")),
                            primary_detection_count=len(dets),
                            detected_classes=list({str(getattr(d, "label", "")).strip().lower() for d in dets}),
                            small_object_ratio=float(getattr(scene_evidence, "small_object_ratio", 0.0) or 0.0),
                            confidence_distribution={
                                "min": min(confidences) if confidences else 0.0,
                                "mean": (sum(confidences) / len(confidences)) if confidences else 0.0,
                                "max": max(confidences) if confidences else 0.0,
                            },
                            coverage_score=coverage_eval.get("coverage_score", 0.0),
                            coverage_threshold=coverage_eval.get("coverage_threshold"),
                            missing_expected_classes=coverage_eval.get("missing_expected_classes", []),
                            coverage_expected_classes=coverage_eval.get("coverage_expected_classes", []),
                            coverage_detected_classes=coverage_eval.get("coverage_detected_classes", []),
                            fallback_decision="yes" if (coverage_eval.get("suggest_secondary_detector", False) or coverage_eval.get("suggest_tiled_inference", False)) else "no",
                            fallback_reason=coverage_eval.get("reason", ""),
                        )
                        
                        second_pass_reason = coverage_eval.get("reason", "Unknown")
                        second_pass_evidence.update(coverage_eval)
                        
                        # Only run Faster R-CNN when:
                        #   1. The agentic planner explicitly selected it (not a reactive fallback).
                        #   2. There are YOLO-responsible classes still missing AFTER YOLO ran.
                        #
                        # DINO-owned missing classes must NEVER trigger Faster R-CNN —
                        # they will be handled by DINO in the same detection loop.
                        def _worker_norm(s: str) -> str:
                            return s.strip().casefold()
                        _dino_responsible = {
                            _worker_norm(lbl) for lbl in source_plan.dino_prompt_labels
                        }
                        missing_yolo_classes = [
                            c for c in coverage_eval.get("missing_expected_classes", [])
                            if _worker_norm(c) not in _dino_responsible
                        ]
                        run_secondary = (
                            enabled_map.get("faster_rcnn", False)
                            and "faster_rcnn" not in completed_models
                            and "faster_rcnn" in execution_plan.models
                            # A planned secondary model still needs a concrete YOLO
                            # class gap; scene density alone is not a fallback reason.
                            and bool(missing_yolo_classes)
                        )
                        
                        if run_secondary:
                            second_model = "faster_rcnn"
                            executed_models.append(second_model)
                            run = ModelRunRow(
                                job_item_id=item_id,
                                batch_id=batch_id,
                                asset_id=asset.id,
                                model_key=second_model,
                                model_id=self.settings.faster_rcnn_model_id,
                                status=ModelRunStatus.RUNNING.value,
                                purpose=f"Secondary detector pass: {coverage_eval.get('reason')}",
                                started_at=datetime.now(UTC),
                            )
                            session.add(run)
                            await commit_with_retry(session)
                            run_start = time.perf_counter()
                            
                            # Log fallback started
                            logger.info(
                                "fallback_started",
                                fallback_model=second_model,
                                asset_id=asset.id,
                                batch_id=batch_id,
                            )
                            
                            try:
                                second_dets, second_masks, second_model_id = (
                                    await asyncio.to_thread(
                                        self._run_model_step,
                                        second_model,
                                        path,
                                        asset.id,
                                        labels,
                                        all_detections,
                                        execution_plan=execution_plan,
                                        ont_index=ont_index,
                                    )
                                )
                                duration_ms = int((time.perf_counter() - run_start) * 1000)
                                run.model_id = second_model_id
                                run.detection_count = len(second_dets)
                                run.mask_count = len(second_masks)
                                run.duration_ms = duration_ms
                                run.status = ModelRunStatus.SUCCEEDED.value
                                run.finished_at = datetime.now(UTC)
                                all_detections.extend(second_dets)
                                if second_model not in completed_models:
                                    completed_models.append(second_model)
                                    
                                logger.info(
                                    "detector_result",
                                    model_key=second_model,
                                    detections=len(second_dets),
                                )
                                
                                # Log fallback completed
                                logger.info(
                                    "fallback_completed",
                                    fallback_model=second_model,
                                    detections=len(second_dets),
                                )
                                
                                self._log_detection_stage(
                                    job_id=item_id,
                                    asset_id=asset.id,
                                    stage=f"raw_detector_candidates:{second_model}",
                                    detections=second_dets,
                                )
                            except Exception as exc:
                                failed_models.append(second_model)
                                run.duration_ms = int((time.perf_counter() - run_start) * 1000)
                                run.error_message = str(exc)
                                run.finished_at = datetime.now(UTC)
                                run.status = ModelRunStatus.FAILED.value
                                logger.warning(
                                    "secondary_pass_failed",
                                    job_id=item_id,
                                    asset_id=asset.id,
                                    model_key=second_model,
                                    error=str(exc),
                                )
                                
                        # 2. Run Tiled YOLO26 Pass if suggested and we haven't already run tiled
                        coverage_assessment = (
                            coverage_eval.get("agent_coverage_assessment") or {}
                        )
                        agent_recovery_strategy = str(
                            coverage_assessment.get("recovery_strategy") or "none"
                        ).strip().lower()
                        low_confidence_ratio = float(
                            (coverage_eval.get("confidence_signals") or {}).get(
                                "low_confidence_ratio", 0.0
                            ) or 0.0
                        )
                        agent_requested_tiled_recovery = (
                            agent_recovery_strategy in {"tiled", "high_resolution", "multi_model"}
                            or str(coverage_assessment.get("coverage_assessment") or "").lower()
                            in {"marginal", "insufficient"}
                        )
                        run_tiled = (
                            enabled_map.get("yolo26", False)
                            and "yolo26" in completed_models
                            and execution_plan.strategy not in {"tiled", "high_resolution_tiled", "small_object_tiled"}
                            and (
                                coverage_eval.get("suggest_tiled_inference", False)
                                or bool(coverage_eval.get("missing_expected_classes"))
                                or agent_requested_tiled_recovery
                                or (
                                    low_confidence_ratio >= 0.45
                                    and bool(getattr(scene_evidence, "crowded", False))
                                )
                            )
                        )
                        
                        if run_tiled:
                            tiled_plan = _ExecutionPlan(
                                models=("yolo26",),
                                strategy="tiled",
                                image_size=1280,
                                tile_rows=3,
                                tile_cols=3,
                                tile_overlap=0.20,
                                reason=f"Dynamic tiled fallback: {coverage_eval.get('reason')}",
                                planner_source="coverage_evaluator_tiled_fallback",
                                verification=execution_plan.verification,
                            )
                            
                            run = ModelRunRow(
                                job_item_id=item_id,
                                batch_id=batch_id,
                                asset_id=asset.id,
                                model_key="yolo26",
                                model_id=str(batch.model_id or "yolo26"),
                                status=ModelRunStatus.RUNNING.value,
                                purpose="Dynamic YOLO26 tiled fallback",
                                started_at=datetime.now(UTC),
                            )
                            session.add(run)
                            await commit_with_retry(session)
                            run_start = time.perf_counter()
                            
                            # Log fallback started
                            logger.info(
                                "fallback_started",
                                fallback_model="yolo26_tiled",
                                asset_id=asset.id,
                                batch_id=batch_id,
                            )
                            
                            try:
                                tiled_dets, tiled_masks, tiled_model_id = (
                                    await asyncio.to_thread(
                                        self._run_model_step,
                                        "yolo26",
                                        path,
                                        asset.id,
                                        labels,
                                        all_detections,
                                        execution_plan=tiled_plan,
                                        ont_index=ont_index,
                                    )
                                )
                                duration_ms = int((time.perf_counter() - run_start) * 1000)
                                run.model_id = tiled_model_id
                                run.detection_count = len(tiled_dets)
                                run.mask_count = len(tiled_masks)
                                run.duration_ms = duration_ms
                                run.status = ModelRunStatus.SUCCEEDED.value
                                run.finished_at = datetime.now(UTC)
                                all_detections.extend(tiled_dets)
                                
                                logger.info(
                                    "detector_result",
                                    model_key="yolo26_tiled",
                                    detections=len(tiled_dets),
                                )
                                
                                # Log fallback completed
                                logger.info(
                                    "fallback_completed",
                                    fallback_model="yolo26_tiled",
                                    detections=len(tiled_dets),
                                )
                                
                                self._log_detection_stage(
                                    job_id=item_id,
                                    asset_id=asset.id,
                                    stage="raw_detector_candidates:yolo26_tiled",
                                    detections=tiled_dets,
                                )
                            except Exception as exc:
                                run.duration_ms = int((time.perf_counter() - run_start) * 1000)
                                run.error_message = str(exc)
                                run.finished_at = datetime.now(UTC)
                                run.status = ModelRunStatus.FAILED.value
                                logger.warning(
                                    "tiled_pass_failed",
                                    job_id=item_id,
                                    asset_id=asset.id,
                                    error=str(exc),
                                )

                    # Evaluate evidence and decide if DINO should be invoked
                    mapped, _stats = merge_detections(
                        [d for d in all_detections if getattr(d, "model_key", "") in DETECTION_MODELS]
                        or list(all_detections),
                        ont_index,
                        iou_threshold=self.settings.merge_iou_threshold,
                        max_box_area=self.settings.max_box_area_pct,
                        review_risk_threshold=self.settings.review_risk_confidence_threshold,
                        source_plan=source_plan,
                    )

                    self._log_detection_stage(
                        job_id=item_id,
                        asset_id=asset.id,
                        stage="after_confidence_nms_and_ontology_mapping",
                        detections=mapped,
                    )
                    from collections import Counter
                    dino_final = [d for d in mapped if getattr(d, "model_key", "") == "dino"]
                    logger.info(
                        "dino_detection_final_diagnostics",
                        project_id=batch.project_id,
                        asset_id=asset.id,
                        nms_input_count=sum(1 for d in all_detections if getattr(d, "model_key", "") == "dino"),
                        nms_count=len(dino_final),
                        final_count=len(dino_final),
                        duplicates_removed=_stats.duplicates_suppressed,
                        detections_by_requested_class=dict(Counter(str(d.label) for d in dino_final)),
                        requested_classes=list(source_plan.dino_prompt_labels),
                    )

                    detected_labels = {
                        d.label
                        for d in mapped
                    }
                    # A planned DINO pass must execute once for its requested
                    # ontology labels, even if another detector happened to
                    # produce an overlapping label. It never receives unrelated
                    # labels because both sources are ontology-scoped.
                    to_prompt = set(source_plan.dino_prompt_labels) if "dino" in execution_plan.models else set()
                    to_prompt |= set(florence_suggestions) if "dino" in execution_plan.models else set()
                    new_prompts = list(to_prompt - requested_dino_labels)

                    execution_plan_models = [
                        m for m in execution_plan.models
                        if (m == "yolo26" and yolo_should_run)
                        or (m == "dino" and enabled_map.get("dino", False) and bool(to_prompt))
                    ]

                    logger.info(
                        "vision_model_routing_decision",
                        job_id=item_id,
                        asset_id=asset.id,
                        round=round_idx,
                        yolo_enabled=enabled_map.get("yolo26", False),
                        yolo_in_execution_plan=yolo_should_run,
                        yolo_canonical=list(source_plan.yolo_canonical),
                        dino_enabled=enabled_map.get("dino", False),
                        dino_prompt_labels=list(source_plan.dino_prompt_labels),
                        requested_dino_labels=list(requested_dino_labels),
                        to_prompt=list(to_prompt),
                        new_prompts=new_prompts,
                        execution_plan_models=execution_plan_models,
                    )

                    if enabled_map.get("dino", False) and to_prompt:
                        model_key = "dino"
                        executed_models.append("dino")
                        purpose = "Open-vocabulary detection"
                        required = False
                        # Limit prompts to new labels we haven't requested before
                        if not new_prompts:
                            break
                        requested_dino_labels.update(new_prompts)
                        logger.info(
                            "dino_execution_started",
                            job_id=item_id,
                            batch_id=batch_id,
                            asset_id=asset.id,
                            model_key=model_key,
                            purpose=purpose,
                            dino_requested_classes=new_prompts,
                        )
                        run = ModelRunRow(
                            job_item_id=item_id,
                            batch_id=batch_id,
                            asset_id=asset.id,
                            model_key=model_key,
                            model_id=str(batch.model_id or model_key),
                            status=ModelRunStatus.RUNNING.value,
                            purpose=purpose,
                            started_at=datetime.now(UTC),
                        )
                        session.add(run)
                        await commit_with_retry(session)
                        run_start = time.perf_counter()
                        try:
                            dets, masks, model_id = await asyncio.to_thread(
                                self._run_model_step,
                                model_key,
                                path,
                                asset.id,
                                list(new_prompts),
                                all_detections,
                                execution_plan=execution_plan,
                                ont_index=ont_index,
                            )
                            duration_ms = int((time.perf_counter() - run_start) * 1000)
                            dino_time_ms = duration_ms
                            run.model_id = model_id
                            run.detection_count = len(dets)
                            run.mask_count = len(masks)
                            run.duration_ms = duration_ms
                            run.status = ModelRunStatus.SUCCEEDED.value
                            run.finished_at = datetime.now(UTC)
                            total_detections += len(dets)
                            all_detections.extend(dets)
                            if "dino" not in completed_models:
                                completed_models.append("dino")

                            from collections import Counter
                            dino_by_class = dict(Counter(str(d.label) for d in dets))
                            logger.info(
                                "dino_detection_diagnostics",
                                project_id=batch.project_id,
                                asset_id=asset.id,
                                image_name=asset.filename,
                                prompt=list(new_prompts),
                                requested_classes=list(new_prompts),
                                raw_detection_count=len(dets),
                                threshold_filtered_count=len(dets),
                                nms_count=None,
                                final_count=None,
                                detections_by_requested_class=dino_by_class,
                                confidence_min=min((float(d.confidence) for d in dets), default=None),
                                confidence_mean=(sum(float(d.confidence) for d in dets) / len(dets)) if dets else None,
                                confidence_max=max((float(d.confidence) for d in dets), default=None),
                            )
                            for requested_class in new_prompts:
                                if not any(str(d.label).casefold() == requested_class.casefold() for d in dets):
                                    logger.info(
                                        "dino_missing_class",
                                        project_id=batch.project_id,
                                        asset_id=asset.id,
                                        missing_class=requested_class,
                                    )

                            logger.info(
                                "detector_result",
                                model_key=model_key,
                                detections=len(dets),
                            )

                            self._log_detection_stage(
                                job_id=item_id,
                                asset_id=asset.id,
                                stage=f"raw_detector_candidates:{model_key}",
                                detections=dets,
                            )

                            session.add(
                                UsageEventRow(
                                    project_id=batch.project_id,
                                    kind="cv_inference",
                                    model_id=model_id,
                                    asset_id=asset.id,
                                    batch_id=batch_id,
                                    duration_ms=duration_ms,
                                    detection_count=len(dets),
                                    tokens_in=0,
                                    tokens_out=0,
                                    cost_usd=None,
                                )
                            )
                            logger.info(
                                "model_execution_complete",
                                job_id=item_id,
                                batch_id=batch_id,
                                asset_id=asset.id,
                                model_key=model_key,
                                model_run_id=run.id,
                                detections=len(dets),
                                masks=len(masks),
                                duration_ms=duration_ms,
                            )
                            logger.info(
                                "model_run_complete",
                                job_id=item_id,
                                batch_id=batch_id,
                                asset_id=asset.id,
                                model_key=model_key,
                                model_run_id=run.id,
                                detections=len(dets),
                                masks=len(masks),
                                duration_ms=duration_ms,
                            )
                        except Exception as exc:  # noqa: BLE001
                            failed_models.append("dino")
                            duration_ms = int((time.perf_counter() - run_start) * 1000)
                            run.duration_ms = duration_ms
                            run.error_message = str(exc)
                            run.finished_at = datetime.now(UTC)
                            run.status = (
                                ModelRunStatus.UNAVAILABLE.value
                                if "unavailable" in str(exc).lower()
                                or "not installed" in str(exc).lower()
                                else ModelRunStatus.FAILED.value
                            )
                            step_errors.append(f"{model_key}: {exc}")
                            logger.warning(
                                "model_run_failed",
                                job_id=item_id,
                                model_key=model_key,
                                model_run_id=run.id,
                                error=str(exc),
                                required=required,
                            )
                    else:
                        # Nothing else to prompt; exit early
                        break

                logger.info(
                    "perf",
                    image=asset.id,
                    stage="detection",
                    duration_ms=int((time.perf_counter() - detection_started) * 1000),
                )

                # Canonical map + cross-model merge, then persist
                if not any(m in completed_models for m in DETECTION_MODELS):
                    raise RuntimeError("No detection model executed successfully for this item.")

                ann = AnnotationService(session)
                detection_only = [
                    d for d in all_detections if getattr(d, "model_key", "") in DETECTION_MODELS
                ]
                if not detection_only and all_detections:
                    detection_only = all_detections
                fusion_start_time = time.perf_counter()
                merged, merge_stats = merge_detections(
                    detection_only,
                    ont_index,
                    iou_threshold=self.settings.merge_iou_threshold,
                    max_box_area=self.settings.max_box_area_pct,
                    review_risk_threshold=self.settings.review_risk_confidence_threshold,
                    source_plan=source_plan,
                )
                fusion_time_ms = int((time.perf_counter() - fusion_start_time) * 1000)
                nms_time_ms = fusion_time_ms
                raw_confidences = [float(d.confidence) for d in detection_only if d.confidence is not None]
                raw_by_class: dict[str, int] = {}
                for detection in detection_only:
                    label = str(getattr(detection, "label", "unknown"))
                    raw_by_class[label] = raw_by_class.get(label, 0) + 1
                logger.info(
                    "detection_recall_diagnostic",
                    asset_id=asset.id,
                    image_name=asset.filename,
                    model="|".join(completed_models),
                    raw_count=len(all_detections),
                    filtered_count=len(detection_only),
                    nms_input_count=len(detection_only),
                    nms_output_count=len(merged),
                    final_count=len(merged),
                    confidence_min=min(raw_confidences) if raw_confidences else None,
                    confidence_mean=sum(raw_confidences) / len(raw_confidences) if raw_confidences else None,
                    confidence_max=max(raw_confidences) if raw_confidences else None,
                    detections_by_class=raw_by_class,
                )
                logger.info("merge_result", detections=len(merged))
                logger.info(
                    "merged_detection_count",
                    asset_id=asset.id,
                    merged_detection_count=len(merged),
                )
                logger.info(
                    "verification_result",
                    strategy=execution_plan.verification,
                    rejected_count=merge_stats.duplicates_suppressed + merge_stats.giant_suppressed,
                )

                verification_report = verify_merged_detections(
                    merged,
                    ont_index,
                    expected_labels=list(source_plan.ontology_labels),
                )
                logger.info(
                    "post_merge_verification",
                    asset_id=asset.id,
                    object_count=verification_report["object_count"],
                    detected_labels=verification_report["detected_labels"],
                    missing_expected_labels=verification_report["missing_expected_labels"],
                    duplicate_count=len(verification_report["duplicate_pairs"]),
                    oversized_count=len(verification_report["oversized_boxes"]),
                    out_of_bounds_count=len(verification_report["out_of_bounds"]),
                    invalid_label_count=len(verification_report["invalid_labels"]),
                    low_confidence_count=len(verification_report["low_confidence"]),
                    small_object_count=len(verification_report["small_object_ids"]),
                    spatial_region_count=verification_report["spatial_region_count"],
                    class_coverage=verification_report["class_coverage"],
                    needs_review=verification_report["needs_review"],
                )

                verification_started = time.perf_counter()
                review_decision = decide_review(
                    merged=merged,
                    all_detections=all_detections,
                    scene_evidence=scene_evidence,
                    completed_models=completed_models,
                    required_verification=execution_plan.verification,
                    rejected_count=merge_stats.duplicates_suppressed + merge_stats.giant_suppressed,
                    model_availability={k: bool(v) for k, v in enabled_map.items()},
                    auto_approve_threshold=project.quality_policy.get("auto_approve_threshold", 0.90) if project.quality_policy else 0.90,
                    verification_report=verification_report,
                )
                merged = _attach_verification_evidence(
                    merged,
                    all_detections,
                    decision=review_decision,
                    verification_report=verification_report,
                )
                logger.info(
                    "perf",
                    image=asset.id,
                    stage="verification",
                    duration_ms=int((time.perf_counter() - verification_started) * 1000),
                )
                self._log_detection_stage(
                    job_id=item_id,
                    asset_id=asset.id,
                    stage="after_ontology_normalization_and_merge",
                    detections=merged,
                )

                self._log_detection_stage(
                    job_id=item_id,
                    asset_id=asset.id,
                    stage="before_persistence",
                    detections=merged,
                )

                # CRITICAL: Verify project and asset still exist before persistence
                # to prevent orphaned annotations if project is deleted during processing
                if await self._should_stop_for_project(session, item_id, batch.project_id):
                    logger.info(
                        "worker_skipping_persistence_project_deleted",
                        job_id=item_id,
                        batch_id=batch_id,
                        project_id=batch.project_id,
                        asset_id=asset.id,
                        detections=len(merged),
                    )
                    return
                asset_still_exists = await session.get(AssetRow, asset.id)
                if asset_still_exists is None:
                    logger.info(
                        "worker_skipping_persistence_asset_deleted",
                        job_id=item_id,
                        batch_id=batch_id,
                        asset_id=asset.id,
                        detections=len(merged),
                    )
                    return

                persistence_started = time.perf_counter()
                ann_result, _ = await ann.replace_ai_detections(
                    asset.id, merged, model_id=getattr(pipeline_plan, "model_id", "pipeline"), project_id=batch.project_id, job_item_id=item_id, batch_id=batch_id
                )
                count = len(ann_result)
                merge_stats.persisted_annotations = count

                if len(merged) != count:
                    logger.warning(
                        "fusion_count_persistence_mismatch",
                        asset_id=asset.id,
                        fusion_final_count=len(merged),
                        annotations_persisted=count,
                        difference=len(merged) - count,
                    )

                persistence_duration_ms = int((time.perf_counter() - persistence_started) * 1000)
                total_duration_ms = int((time.perf_counter() - start) * 1000)

                logger.info(
                    "asset_performance_metrics",
                    asset_id=asset.id,
                    image_name=asset.filename,
                    decode_time_ms=decode_time_ms,
                    preprocessing_time_ms=preprocessing_time_ms,
                    yolo_time_ms=yolo_time_ms,
                    yolo_recall_time_ms=yolo_recall_time_ms,
                    dino_time_ms=dino_time_ms,
                    dino_recall_time_ms=dino_recall_time_ms,
                    nms_time_ms=nms_time_ms,
                    fusion_time_ms=fusion_time_ms,
                    annotation_persistence_time_ms=persistence_duration_ms,
                    total_time_ms=total_duration_ms,
                )

                logger.info(
                    "annotation_pipeline_counts",
                    asset_id=asset.id,
                    db_persisted_count=count,
                    api_expected_count=count,
                    final_models=completed_models,
                )
                logger.info(
                    "perf",
                    image=asset.id,
                    stage="database_persistence",
                    duration_ms=persistence_duration_ms,
                )
                logger.info(
                    "detections_merged",
                    job_id=item_id,
                    asset_id=asset.id,
                    **stats_to_dict(merge_stats),
                    raw_candidates=len(detection_only),
                    merged_candidates=len(merged),
                    persisted=count,
                )
                logger.info(
                    "final_annotation_count",
                    asset_id=asset.id,
                    final_annotation_count=count,
                )
                logger.info(
                    "detection_recall_diagnostic_final",
                    asset_id=asset.id,
                    image_name=asset.filename,
                    model="|".join(completed_models),
                    raw_count=len(all_detections),
                    filtered_count=len(detection_only),
                    nms_input_count=len(detection_only),
                    nms_output_count=len(merged),
                    final_count=count,
                    detections_by_class=dict(merge_stats.by_canonical),
                )
                # Structured annotation summary: per-class counts, model responsibility,
                # coverage score, and any classes that were not detected.
                _yolo_resp = list(source_plan.yolo_canonical)
                _dino_resp = list(source_plan.dino_prompt_labels)
                _detected_canonical = set(merge_stats.by_canonical.keys())
                _missing_yolo = [lbl for lbl in _yolo_resp if lbl not in _detected_canonical]
                _missing_dino  = [lbl for lbl in _dino_resp  if lbl not in _detected_canonical]
                logger.info(
                    "annotation_class_summary",
                    asset_id=asset.id,
                    batch_id=batch_id,
                    per_class_counts=dict(merge_stats.by_canonical),
                    yolo_responsible=_yolo_resp,
                    dino_responsible=_dino_resp,
                    executed_models=executed_models,
                    coverage_score=second_pass_evidence.get("coverage_score", 1.0),
                    missing_yolo_classes=_missing_yolo,
                    missing_dino_classes=_missing_dino,
                    final_annotation_count=count,
                )
                total_detections += len(merged)
                saved_detections = merged

                if enabled_map.get("sam2", False) and "sam2" in execution_plan.models and saved_detections:
                    executed_models.append("sam2")
                    boxes = [d.bbox for d in saved_detections]
                    ann_ids = [d.id for d in saved_detections]
                    box_labels = [d.label for d in saved_detections]
                    run = ModelRunRow(
                        job_item_id=item_id,
                        batch_id=batch_id,
                        asset_id=asset.id,
                        model_key="sam2",
                        model_id=str(batch.model_id or "sam2"),
                        status=ModelRunStatus.RUNNING.value,
                        purpose="Segmentation from boxes",
                        started_at=datetime.now(UTC),
                    )
                    session.add(run)
                    await commit_with_retry(session)
                    run_start = time.perf_counter()
                    try:
                        logger.info(
                            "sam2_execution_started",
                            job_id=item_id,
                            asset_id=asset.id,
                            prompt_box_count=len(boxes),
                            prompt_labels=box_labels,
                        )
                        masks = await asyncio.to_thread(
                            self.runtime.registry.get("sam2").segment_boxes,
                            path,
                            asset_id=asset.id,
                            boxes=boxes,
                            labels=box_labels,
                            annotation_ids=ann_ids,
                            storage_dir=self.storage.root / "masks" / asset.id,
                        )
                        duration_ms = int((time.perf_counter() - run_start) * 1000)
                        run = await session.get(ModelRunRow, run.id)
                        if run is None:
                            raise RuntimeError("SAM2 model_run row missing after commit")
                        run.model_id = self.runtime.registry.get("sam2").model_id
                        run.detection_count = 0
                        run.mask_count = len(masks)
                        run.duration_ms = duration_ms
                        run.status = ModelRunStatus.SUCCEEDED.value
                        run.finished_at = datetime.now(UTC)
                        if masks:
                            mask_svc = MaskService(session, self.storage)
                            try:
                                await mask_svc.replace_ai_masks(
                                    asset.id,
                                    masks,
                                    commit=False,
                                )
                                await commit_with_retry(session)
                                mask_count = len(masks)
                                polygon_count = 0
                                if project and project.task_type == "segmentation":
                                    polygon_count = await _persist_mask_polygons(
                                        session,
                                        self.storage,
                                        masks,
                                    )
                                    await commit_with_retry(session)
                                logger.info(
                                    "sam2_polygon_result",
                                    asset_id=asset.id,
                                    polygon_count=polygon_count,
                                    mask_count=len(masks),
                                )
                            except Exception as exc:  # noqa: BLE001
                                run = await session.get(ModelRunRow, run.id)
                                if run is not None:
                                    run.error_message = str(exc)
                                    run.finished_at = datetime.now(UTC)
                                    run.mask_count = 0
                                    run.status = (
                                        ModelRunStatus.UNAVAILABLE.value
                                        if "unavailable" in str(exc).lower()
                                        or "not installed" in str(exc).lower()
                                        else ModelRunStatus.FAILED.value
                                    )
                                await commit_with_retry(session)
                                logger.warning(
                                    "model_run_failed",
                                    job_id=item_id,
                                    batch_id=batch_id,
                                    asset_id=asset.id,
                                    model_key="sam2",
                                    model_run_id=run.id if run is not None else None,
                                    error=str(exc),
                                    required=False,
                                )
                                masks = []
                            else:
                                session.add(
                                    UsageEventRow(
                                        project_id=batch.project_id,
                                        kind="cv_inference",
                                        model_id=run.model_id,
                                        asset_id=asset.id,
                                        batch_id=batch_id,
                                        duration_ms=duration_ms,
                                        detection_count=0,
                                        tokens_in=0,
                                        tokens_out=0,
                                        cost_usd=None,
                                    )
                                )
                                await commit_with_retry(session)
                                logger.info(
                                    "model_run_complete",
                                    job_id=item_id,
                                    batch_id=batch_id,
                                    asset_id=asset.id,
                                    model_key="sam2",
                                    model_run_id=run.id,
                                    detections=0,
                                    masks=len(masks),
                                    duration_ms=duration_ms,
                                )
                                completed_models.append("sam2")
                        else:
                            session.add(
                                UsageEventRow(
                                    project_id=batch.project_id,
                                    kind="cv_inference",
                                    model_id=run.model_id,
                                    asset_id=asset.id,
                                    batch_id=batch_id,
                                    duration_ms=duration_ms,
                                    detection_count=0,
                                    tokens_in=0,
                                    tokens_out=0,
                                    cost_usd=None,
                                )
                            )
                            await commit_with_retry(session)
                            logger.info(
                                "model_run_complete",
                                job_id=item_id,
                                batch_id=batch_id,
                                asset_id=asset.id,
                                model_key="sam2",
                                model_run_id=run.id,
                                detections=0,
                                masks=0,
                                duration_ms=duration_ms,
                            )
                            completed_models.append("sam2")
                    except Exception as exc:  # noqa: BLE001
                        failed_models.append("sam2")
                        run = await session.get(ModelRunRow, run.id)
                        if run is not None:
                            run.model_id = self.runtime.registry.get("sam2").model_id
                            run.detection_count = 0
                            run.mask_count = 0
                            run.duration_ms = int((time.perf_counter() - run_start) * 1000)
                            run.error_message = str(exc)
                            run.finished_at = datetime.now(UTC)
                            run.status = (
                                ModelRunStatus.UNAVAILABLE.value
                                if "unavailable" in str(exc).lower()
                                or "not installed" in str(exc).lower()
                                else ModelRunStatus.FAILED.value
                            )
                        await commit_with_retry(session)
                        logger.warning(
                            "model_run_failed",
                            job_id=item_id,
                            batch_id=batch_id,
                            asset_id=asset.id,
                            model_key="sam2",
                            model_run_id=run.id if run is not None else None,
                            error=str(exc),
                            required=False,
                        )

                item = await session.get(JobItemRow, item_id)
                asset = await session.get(AssetRow, asset.id)
                assert item is not None and asset is not None

                duration_ms = int((time.perf_counter() - start) * 1000)
                item.status = JobItemStatus.SUCCEEDED.value
                item.detection_count = count
                item.duration_ms = duration_ms
                item.finished_at = datetime.now(UTC)
                item.error_message = "; ".join(step_errors) if step_errors else ""
                asset.status = AssetStatus.READY.value
                asset.review_status = (
                    ReviewStatus.REVIEW.value
                    if review_decision.human_review_required
                    else ReviewStatus.APPROVED.value
                )

                logger.info(
                    "review_decision",
                    job_id=item_id,
                    asset_id=asset.id,
                    needs_human_review=review_decision.human_review_required,
                    unresolved_reasons=list(review_decision.unresolved_reasons),
                    review_status=asset.review_status,
                )

                # Detailed structured logging for every image
                from app.inference.merge import box_iou_percent
                yolo_dets = [d for d in all_detections if getattr(d, "model_key", "") == "yolo26"]
                rcnn_dets = [d for d in all_detections if getattr(d, "model_key", "") == "faster_rcnn"]
                yolo_confidences = [d.confidence for d in yolo_dets]
                rcnn_confidences = [d.confidence for d in rcnn_dets]
                original_confidences = [
                    {"model_key": getattr(d, "model_key", ""), "label": getattr(d, "label", ""), "confidence": getattr(d, "confidence", 0.0)}
                    for d in all_detections
                ]
                iou_associations = [
                    d.provenance.get("merge_iou")
                    for d in merged
                    if getattr(d, "provenance", None) and d.provenance.get("merge_iou") is not None
                ]
                new_objects_recovered = 0
                for d in merged:
                    prov = getattr(d, "provenance", None) or {}
                    contributing = prov.get("contributing_models") or []
                    supporting = {item.get("model_key") for item in contributing if item.get("model_key")}
                    if supporting == {"faster_rcnn"} or (not supporting and d.model_key == "faster_rcnn"):
                        new_objects_recovered += 1

                same_object_matches = len(merged) - new_objects_recovered
                
                # Conflicting labels details
                label_conflict_pairs = [
                    {"first": first.label, "second": second.label}
                    for index, first in enumerate(merged)
                    for second in merged[index + 1 :]
                    if box_iou_percent(first, second) >= 0.45 and first.label != second.label
                ]

                logger.info(
                    "image_pipeline_details",
                    asset_id=asset.id,
                    yolo26={
                        "raw_detection_count": len(yolo_dets),
                        "original_confidences": yolo_confidences,
                    },
                    agent={
                        "evidence_considered": second_pass_evidence,
                        "reason_for_second_pass_decision": second_pass_reason,
                        "use_faster_rcnn": "faster_rcnn" in executed_models,
                    },
                    faster_rcnn={
                        "raw_detection_count": len(rcnn_dets),
                        "original_confidences": rcnn_confidences,
                    },
                    fusion={
                        "iou_associations": iou_associations,
                        "same_object_matches": same_object_matches,
                        "new_objects_recovered": new_objects_recovered,
                        "duplicates_removed": merge_stats.duplicates_suppressed,
                        "conflicting_labels": label_conflict_pairs,
                        "contributing_models": [
                            [item.get("model_key") for item in d.provenance.get("contributing_models", [])]
                            if getattr(d, "provenance", None) and d.provenance.get("contributing_models")
                            else [d.model_key]
                            for d in merged
                        ],
                    },
                    verification={
                        "resolved": not review_decision.human_review_required,
                        "reasoning": list(review_decision.unresolved_reasons),
                        "coverage_concern": review_decision.evidence.get("evidence", {}).get("coverage_concern", False),
                    },
                    review={
                        "final_decision": "auto_approve" if not review_decision.human_review_required else "human_review",
                        "reason": ", ".join(review_decision.unresolved_reasons) if review_decision.unresolved_reasons else "All evidence resolved successfully",
                    }
                )

                thresh = float(project.quality_policy.get("auto_approve_threshold", 0.92)) if project.quality_policy else 0.92
                valid_confidences = [
                    float(d.confidence)
                    for d in merged
                    if d.confidence is not None
                    and isinstance(d.confidence, (int, float))
                    and not isinstance(d.confidence, bool)
                    and 0.0 <= float(d.confidence) <= 1.0
                    and getattr(d, "source", "ai") not in ("human", "human_modified")
                ] if merged else []
                if valid_confidences:
                    img_mean = sum(valid_confidences) / len(valid_confidences)
                    asset.mean_confidence = img_mean
                    if not review_decision.human_review_required and img_mean >= thresh:
                        asset.review_status = ReviewStatus.AUTO_APPROVED.value
                        asset.review_reason = f"Auto-approved: image confidence {round(img_mean * 100, 1)}% >= review threshold {round(thresh * 100)}%"
                    else:
                        asset.review_status = ReviewStatus.HUMAN_REVIEW.value
                        reasons_str = ", ".join(review_decision.unresolved_reasons) if review_decision.unresolved_reasons else f"LOW_CONFIDENCE: image confidence {round(img_mean * 100, 1)}% < review threshold {round(thresh * 100)}%"
                        asset.review_reason = reasons_str
                else:
                    asset.mean_confidence = None
                    asset.review_status = ReviewStatus.HUMAN_REVIEW.value
                    asset.review_reason = "NO_VALID_AI_DETECTIONS"
                await commit_with_retry(session)
                try:
                    from app.services.review_priority import refresh_review_priorities

                    await refresh_review_priorities(session, asset.project_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("review_priority_refresh_failed", error=str(exc))
                logger.info(
                    "detection_execution_summary",
                    job_id=item_id,
                    batch_id=batch_id,
                    asset_id=asset.id,
                    executed_models=executed_models,
                    successful_models=completed_models,
                    failed_models=failed_models,
                    detections=count,
                )
                logger.info(
                    "job_item_complete",
                    job_id=item_id,
                    batch_id=batch_id,
                    asset_id=asset.id,
                    detections=count,
                    mask_count=mask_count,
                    completed_models=completed_models,
                    status=item.status,
                    duration_ms=duration_ms,
                )
                logger.info(
                    "perf",
                    image=asset.id,
                    stage="total_image_processing",
                    duration_ms=duration_ms,
                )
            except Exception as exc:  # noqa: BLE001
                duration_ms = int((time.perf_counter() - start) * 1000)
                try:
                    pass
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "job_item_rollback_failed",
                        job_id=item_id,
                        batch_id=batch_id,
                    )
                from PIL import UnidentifiedImageError
                is_deterministic = isinstance(exc, (IntegrityError, MaskPersistenceError, UnidentifiedImageError))
                is_transient = _is_transient_db_error(exc)
                will_retry = not is_deterministic and primitive_attempt <= self.settings.retry_count
                if is_transient:
                    logger.warning(
                        "job_item_retryable_database_error",
                        batch_id=batch_id,
                        job_item_id=primitive_item_id,
                        project_id=primitive_project_id,
                        attempt=primitive_attempt,
                        max_attempts=self.settings.retry_count,
                        exception_type=type(exc).__name__,
                        error=str(exc),
                    )
                if is_deterministic:
                    logger.warning(
                        "job_item_deterministic_failure",
                        job_id=item_id,
                        batch_id=batch_id,
                        error=str(exc),
                    )
                if will_retry:
                    try:
                        async with self.session_factory() as recovery_session:
                            itm = await recovery_session.get(JobItemRow, primitive_item_id)
                            if itm is not None:
                                itm.status = JobItemStatus.QUEUED.value
                                itm.error_message = f"Attempt {primitive_attempt} failed: {exc}"
                                itm.started_at = None
                                await commit_with_retry(recovery_session)
                        logger.warning(
                            "job_item_retry",
                            job_id=item_id,
                            batch_id=batch_id,
                            attempt=primitive_attempt,
                            error=str(exc),
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("job_item_retry_failed", job_id=item_id, batch_id=batch_id)
                else:
                    if is_transient:
                        logger.warning(
                            "job_item_transient_db_reset_deferred",
                            job_id=item_id,
                            batch_id=batch_id,
                            error=str(exc),
                        )
                    else:
                        try:
                            async with self.session_factory() as recovery_session:
                                itm = await recovery_session.get(JobItemRow, primitive_item_id)
                                await self._fail_item(
                                recovery_session,
                                itm,
                                batch_id,
                                str(exc),
                                duration_ms=duration_ms,
                                asset_id=primitive_asset_id,
                            )
                        except Exception:  # noqa: BLE001
                            logger.exception("job_item_fail_recovery_failed", job_id=item_id)

        async with self.session_factory() as session:
            svc = BatchService(session, self.settings)
            await svc.finalize_if_done(batch_id)

    async def _inspect_scene(
        self,
        *,
        path: Path,
        asset_id: str,
        priority_labels: tuple[str, ...] = (),
        use_florence: bool = False,
        use_agent_scene: bool = False,
    ) -> _SceneEvidence:
        """Collect deterministic routing evidence and enrich using Florence-2/LLM Agent if requested."""

        image_load_started = time.perf_counter()

        def inspect() -> _SceneEvidence:
            from PIL import Image

            with Image.open(path) as image:
                width, height = image.size

            megapixels = (width * height) / 1_000_000.0

            large_image = (
                megapixels >= 4.0
                or max(width, height) >= 3000
            )

            return _SceneEvidence(
                image_width=width,
                image_height=height,
                megapixels=megapixels,
                large_image=large_image,
                priority_labels=priority_labels,
            )

        evidence = await asyncio.to_thread(inspect)
        logger.info(
            "perf",
            image=asset_id,
            stage="image_load",
            duration_ms=int((time.perf_counter() - image_load_started) * 1000),
        )

        # 2. Get caption from Florence-2 if enabled
        caption = None
        florence_enabled = (
            use_florence
            and self.settings.florence_enabled
            and self.runtime is not None
        )
        if florence_enabled:
            florence_started = time.perf_counter()
            try:
                registry = self.runtime.registry
                if registry.try_load("florence"):
                    adapter = registry.get("florence")
                    suggestion = await asyncio.to_thread(
                        adapter.assist, path, asset_id=asset_id, labels=list(priority_labels), goal="", strategy="generic"
                    )
                    caption = getattr(suggestion, "caption", None)
            except Exception as exc:
                logger.warning("discovery_florence_assist_failed", error=str(exc))
            finally:
                logger.info(
                    "perf",
                    image=asset_id,
                    stage="florence",
                    duration_ms=int((time.perf_counter() - florence_started) * 1000),
                )

        # 3. Call the Discovery Agent (LLM) only if explicitly requested
        scene_type = None
        object_density = None
        small_object_ratio = None
        expected_object_count = None
        aerial = False
        crowded = False
        
        agent_enabled = self.settings.agent_enabled and use_agent_scene
        if agent_enabled:
            reasoning_started = time.perf_counter()
            payload = {
                "image_width": evidence.image_width,
                "image_height": evidence.image_height,
                "megapixels": evidence.megapixels,
                "large_image": evidence.large_image,
                "priority_labels": list(priority_labels),
                "visual_caption": caption,
            }
            
            system_prompt = (
                "You are the Image Discovery Agent for an annotation pipeline.\n"
                "Your task is to inspect the image metadata and caption to determine useful scene information.\n"
                "Determine:\n"
                "- scene_type: e.g. 'traffic scene', 'urban street', 'aerial/overhead', 'crowded scene', etc.\n"
                "- object_density: float between 0.0 (sparse) and 1.0 (extremely dense)\n"
                "- small_object_ratio: float between 0.0 and 1.0 (ratio of small/distant objects)\n"
                "- expected_object_count: integer estimate of expected target objects\n"
                "- aerial: boolean (true if bird's-eye/aerial/overhead view)\n"
                "- crowded: boolean (true if objects are crowded/dense)\n"
                "- pedestrians_present: boolean (true if pedestrians/people are visible)\n"
                "- custom_object_possibility: boolean\n"
                "\n"
                "Return ONLY JSON:\n"
                "{\n"
                "  \"scene_type\": string,\n"
                "  \"object_density\": float,\n"
                "  \"small_object_ratio\": float,\n"
                "  \"expected_object_count\": integer,\n"
                "  \"aerial\": boolean,\n"
                "  \"crowded\": boolean,\n"
                "  \"pedestrians_present\": boolean,\n"
                "  \"custom_object_possibility\": boolean\n"
                "}"
            )
            
            from app.inference.agent_reasoning import call_json_agent
            res = call_json_agent(
                system_prompt=system_prompt,
                user_payload=payload,
                settings=self.settings,
            )
            logger.info(
                "perf",
                image=asset_id,
                stage="scene_classification",
                duration_ms=int((time.perf_counter() - reasoning_started) * 1000),
            )
            if res:
                scene_type = res.get("scene_type")
                object_density = res.get("object_density")
                if object_density is not None:
                    object_density = float(object_density)
                small_object_ratio = res.get("small_object_ratio")
                if small_object_ratio is not None:
                    small_object_ratio = float(small_object_ratio)
                expected_object_count = res.get("expected_object_count")
                if expected_object_count is not None:
                    expected_object_count = int(expected_object_count)
                aerial = bool(res.get("aerial", False))
                crowded = bool(res.get("crowded", False))
                
                metadata = {
                    "pedestrians_present": bool(res.get("pedestrians_present", False)),
                    "custom_object_possibility": bool(res.get("custom_object_possibility", False)),
                    "caption": caption,
                }
                
                evidence = _SceneEvidence(
                    image_width=evidence.image_width,
                    image_height=evidence.image_height,
                    megapixels=evidence.megapixels,
                    large_image=evidence.large_image,
                    priority_labels=priority_labels,
                    scene_type=scene_type,
                    object_density=object_density,
                    small_object_ratio=small_object_ratio,
                    expected_object_count=expected_object_count,
                    aerial=aerial,
                    crowded=crowded,
                    metadata=metadata,
                )
                
        # 4. Fallback heuristics if LLM was unavailable/failed
        if evidence.scene_type is None:
            text = (caption or "").lower()
            aerial_flag = "aerial" in text or "overhead" in text or "drone" in text
            crowded_flag = "crowd" in text or "many" in text or "busy" in text or "dense" in text
            is_traffic = "traffic" in text or "street" in text or "road" in text or "highway" in text or "car" in text
            pedestrians = "person" in text or "people" in text or "pedestrian" in text or "man" in text or "woman" in text
            
            estimated_count = 15 if crowded_flag else (5 if text else None)
            small_ratio = 0.4 if (aerial_flag or "distant" in text or "far" in text) else 0.1
            density = 0.6 if crowded_flag else (0.2 if text else None)
            
            metadata = {
                "pedestrians_present": pedestrians,
                "custom_object_possibility": False,
                "caption": caption,
            }
            evidence = _SceneEvidence(
                image_width=evidence.image_width,
                image_height=evidence.image_height,
                megapixels=evidence.megapixels,
                large_image=evidence.large_image,
                priority_labels=priority_labels,
                scene_type="traffic scene" if is_traffic else ("general scene" if text else None),
                object_density=density,
                small_object_ratio=small_ratio,
                expected_object_count=estimated_count,
                aerial=aerial_flag,
                crowded=crowded_flag,
                metadata=metadata,
            )

        logger.info(
            "vision_scene_evidence",
            asset_id=asset_id,
            image_width=evidence.image_width,
            image_height=evidence.image_height,
            megapixels=evidence.megapixels,
            large_image=evidence.large_image,
            aerial=evidence.aerial,
            crowded=evidence.crowded,
            object_density=evidence.object_density,
            small_object_ratio=evidence.small_object_ratio,
        )

        return evidence

    def _run_model_step(
        self,
        model_key: str,
        path: Path,
        asset_id: str,
        labels: list[str],
        prior_detections: list[Any],
        *,
        execution_plan: _ExecutionPlan | None = None,
        scene_evidence: Any = None,
        ont_index: Any = None,
    ) -> tuple[list[Any], list[Any], str]:
        """Execute one model while preserving provenance and confidence."""

        if model_key == "yolo26":
            detector = self.detector

            # Filter only exact raw classes that YOLO can emit.  Parent or
            # custom ontology labels must not be passed to the detector,
            # otherwise valid raw classes are discarded before ontology
            # mapping (and human review) can see them.
            from app.inference.adapters.yolo26 import YOLO_SUPPORTED_LABELS
            from app.inference.ontology_map import map_raw_label, build_ontology_index

            if ont_index is None:
                ont_index = build_ontology_index(labels)

            yolo_labels = []
            for raw_lbl in YOLO_SUPPORTED_LABELS:
                res = map_raw_label(raw_lbl, ont_index)
                if res.accepted:
                    yolo_labels.append(raw_lbl)

            strategy = (
                execution_plan.strategy
                if execution_plan is not None
                else "full_image"
            )



            if strategy in {
                "tiled",
                "high_resolution_tiled",
                "small_object_tiled",
            }:
                return self._run_yolo_tiled(
                    detector=detector,
                    image_path=path,
                    asset_id=asset_id,
                    labels=yolo_labels,
                    execution_plan=execution_plan,
                )

            kwargs: dict[str, Any] = {
                "asset_id": asset_id,
                "labels": yolo_labels or None,
            }

            # Pass planning information only to adapters that explicitly
            # support it. This keeps old/fake adapters backward compatible.
            if execution_plan is not None:
                kwargs.update(
                    {
                        "strategy": execution_plan.strategy,
                        "image_size": execution_plan.image_size,
                        "tile_rows": execution_plan.tile_rows,
                        "tile_cols": execution_plan.tile_cols,
                        "tile_overlap": execution_plan.tile_overlap,
                        "plan_source": execution_plan.planner_source,
                        "plan_reason": execution_plan.reason,
                    }
                )

            try:
                dets = detector.predict(
                    path,
                    **kwargs,
                )
            except TypeError:
                # Existing adapter contract compatibility.
                try:
                    dets = detector.predict(
                        path,
                        asset_id=asset_id,
                        labels=yolo_labels or None,
                    )
                except TypeError:
                    dets = detector.predict(
                        path,
                        asset_id=asset_id,
                    )

            return (
                list(dets),
                [],
                detector.model_id,
            )

        if self.runtime is None:
            raise RuntimeError(
                f"Model {model_key} requires inference runtime"
            )

        registry = self.runtime.registry
        adapter = registry.get(model_key)

        if not registry.try_load(model_key):
            raise RuntimeError(
                registry._errors.get(
                    model_key,
                    f"{model_key} unavailable",
                )
            )

        if model_key == "dino":
            if self.mcp_client is not None and self.settings.mcp_enabled:
                result = self.mcp_client.vision.detect_custom_objects(
                    path, asset_id=asset_id, prompts=labels or None
                )
                if result.success:
                    return (list(result.data), [], adapter.model_id)
                raise RuntimeError(result.error.message)
            dets = adapter.predict(
                path,
                asset_id=asset_id,
                labels=labels or None,
            )
            return (
                list(dets),
                [],
                adapter.model_id,
            )

        if model_key == "faster_rcnn":
            threshold = getattr(
                self.settings,
                "faster_rcnn_confidence_threshold",
                0.15,
            )
            dets = adapter.predict(
                path,
                asset_id=asset_id,
                labels=labels or None,
                confidence_threshold=threshold,
            )
            return (
                list(dets),
                [],
                adapter.model_id,
            )

        if model_key == "florence":
            adapter.assist(
                path,
                asset_id=asset_id,
                labels=labels,
                goal="scene_understanding",
                strategy="detailed",
            )
            return (
                [],
                [],
                adapter.model_id,
            )

        if model_key == "sam2":
            boxes = [
                d.bbox
                for d in prior_detections
            ]
            ann_ids = [
                getattr(d, "id", None)
                for d in prior_detections
            ]
            box_labels = [
                getattr(d, "label", "object")
                for d in prior_detections
            ]

            if not boxes:
                return (
                    [],
                    [],
                    adapter.model_id,
                )

            mask_dir = (
                self.storage.root
                / "masks"
                / asset_id
            )

            if self.mcp_client is not None and self.settings.mcp_enabled:
                result = self.mcp_client.vision.segment_objects(
                    path,
                    asset_id=asset_id,
                    detections=prior_detections,
                    storage_dir=mask_dir,
                )
                if result.success:
                    return ([], list(result.data), adapter.model_id)
                raise RuntimeError(result.error.message)

            masks = adapter.segment_boxes(
                path,
                asset_id=asset_id,
                boxes=boxes,
                labels=box_labels,
                annotation_ids=ann_ids,
                storage_dir=mask_dir,
            )

            return (
                [],
                list(masks),
                adapter.model_id,
            )

        raise RuntimeError(
            f"Unsupported model key {model_key}"
        )

    def _run_yolo_tiled(
        self,
        *,
        detector: Any,
        image_path: Path,
        asset_id: str,
        labels: list[str],
        execution_plan: _ExecutionPlan | None,
    ) -> tuple[list[Any], list[Any], str]:
        """Run YOLO on image tiles and transform boxes to global coordinates.

        Model confidence is copied unchanged from each detector result.
        Tile coordinates are converted deterministically to natural-image
        coordinates. Cross-tile duplicate removal remains the responsibility
        of the deterministic merge/NMS stage.
        """

        from PIL import Image

        raw_rows = (
            execution_plan.tile_rows
            if execution_plan is not None
            else 2
        )
        raw_cols = (
            execution_plan.tile_cols
            if execution_plan is not None
            else 2
        )
        # Adaptively use 2x2 (4 tiles) for standard resolution images
        rows = max(1, min(2, int(raw_rows))) if raw_rows == 3 else max(1, int(raw_rows))
        cols = max(1, min(2, int(raw_cols))) if raw_cols == 3 else max(1, int(raw_cols))

        overlap = min(
            0.45,
            max(
                0.0,
                float(
                    execution_plan.tile_overlap
                    if execution_plan is not None
                    else 0.15
                ),
            ),
        )

        image_size = (
            execution_plan.image_size
            if execution_plan is not None
            else None
        )

        logger.info(
            "adaptive_tiling_decision",
            tiling_enabled=True,
            tile_count=rows * cols,
            tile_rows=rows,
            tile_cols=cols,
            tile_size=image_size or 1024,
            overlap=overlap,
            reason=execution_plan.reason if execution_plan is not None else "adaptive_small_object_tiling",
        )

        with Image.open(image_path) as source:
            image = source.convert("RGB")
            width, height = image.size

            # Build an exact rows x cols grid. Tile size is enlarged enough
            # to create the requested overlap, while tile origins are spaced
            # deterministically across the complete original image.
            tile_w = min(
                width,
                max(
                    1,
                    int(
                        width
                        / cols
                        / max(0.01, 1.0 - overlap)
                    ),
                ),
            )
            tile_h = min(
                height,
                max(
                    1,
                    int(
                        height
                        / rows
                        / max(0.01, 1.0 - overlap)
                    ),
                ),
            )

            if cols == 1:
                x_starts = [0]
            else:
                max_x = max(0, width - tile_w)
                x_starts = [
                    int(round(
                        c * max_x / (cols - 1)
                    ))
                    for c in range(cols)
                ]

            if rows == 1:
                y_starts = [0]
            else:
                max_y = max(0, height - tile_h)
                y_starts = [
                    int(round(
                        r * max_y / (rows - 1)
                    ))
                    for r in range(rows)
                ]

            detections: list[NormalizedDetection] = []

            with tempfile.TemporaryDirectory(
                prefix="ingenii-yolo-tiles-"
            ) as tmp:
                tile_index = 0

                for y0 in y_starts:
                    for x0 in x_starts:
                        x1 = min(
                            width,
                            x0 + tile_w,
                        )
                        y1 = min(
                            height,
                            y0 + tile_h,
                        )

                        tile = image.crop(
                            (x0, y0, x1, y1)
                        )

                        tile_path = (
                            Path(tmp)
                            / f"tile-{tile_index}.jpg"
                        )
                        tile.save(
                            tile_path,
                            quality=95,
                        )

                        tile_kwargs: dict[str, Any] = {
                            "asset_id": asset_id,
                            "labels": labels or None,
                        }

                        if image_size is not None:
                            tile_kwargs["image_size"] = image_size

                        try:
                            tile_dets = detector.predict(
                                tile_path,
                                **tile_kwargs,
                            )
                        except TypeError:
                            try:
                                tile_dets = detector.predict(
                                    tile_path,
                                    asset_id=asset_id,
                                    labels=labels or None,
                                )
                            except TypeError:
                                tile_dets = detector.predict(
                                    tile_path,
                                    asset_id=asset_id,
                                )

                        self._log_detection_stage(
                            job_id=asset_id,
                            asset_id=asset_id,
                            stage=(
                                "tile_raw_candidates"
                                f":tile_{tile_index}"
                            ),
                            detections=list(tile_dets),
                        )

                        for detection in tile_dets:
                            bbox = detection.bbox

                            tile_width = x1 - x0
                            tile_height = y1 - y0

                            global_x = (
                                x0
                                + (
                                    bbox.x
                                    / 100.0
                                    * tile_width
                                )
                            )
                            global_y = (
                                y0
                                + (
                                    bbox.y
                                    / 100.0
                                    * tile_height
                                )
                            )
                            global_w = (
                                bbox.w
                                / 100.0
                                * tile_width
                            )
                            global_h = (
                                bbox.h
                                / 100.0
                                * tile_height
                            )

                            global_bbox = BoundingBoxPercent(
                                x=max(
                                    0.0,
                                    min(
                                        100.0,
                                        (
                                            global_x
                                            / width
                                            * 100.0
                                        ),
                                    ),
                                ),
                                y=max(
                                    0.0,
                                    min(
                                        100.0,
                                        (
                                            global_y
                                            / height
                                            * 100.0
                                        ),
                                    ),
                                ),
                                w=max(
                                    0.0,
                                    min(
                                        100.0,
                                        (
                                            global_w
                                            / width
                                            * 100.0
                                        ),
                                    ),
                                ),
                                h=max(
                                    0.0,
                                    min(
                                        100.0,
                                        (
                                            global_h
                                            / height
                                            * 100.0
                                        ),
                                    ),
                                ),
                            )

                            provenance = dict(
                                getattr(
                                    detection,
                                    "provenance",
                                    {},
                                )
                                or {}
                            )

                            provenance.update(
                                {
                                    "inference_mode": "tiled",
                                    "tile_index": tile_index,
                                    "tile_origin_xy": [
                                        x0,
                                        y0,
                                    ],
                                    "tile_size": [
                                        tile_width,
                                        tile_height,
                                    ],
                                    "source_image_size": [
                                        width,
                                        height,
                                    ],
                                    "coordinate_transform": (
                                        "tile_percent_to_global_percent"
                                    ),
                                }
                            )

                            # Preserve model confidence exactly.
                            detections.append(
                                replace(
                                    detection,
                                    bbox=global_bbox,
                                    provenance=provenance,
                                )
                            )

                        tile_index += 1

        logger.info(
            "yolo_tiled_complete",
            asset_id=asset_id,
            rows=rows,
            cols=cols,
            overlap=overlap,
            detections=len(detections),
        )

        return (
            detections,
            [],
            detector.model_id,
        )

    def _log_detection_stage(
        self,
        *,
        job_id: str,
        asset_id: str,
        stage: str,
        detections: list[Any],
    ) -> None:
        """Log exactly how many detections survive each pipeline stage."""

        by_model: dict[str, int] = {}
        by_label: dict[str, int] = {}

        for detection in detections:
            model_key = str(
                getattr(
                    detection,
                    "model_key",
                    "unknown",
                )
            )
            label = str(
                getattr(
                    detection,
                    "label",
                    "unknown",
                )
            )

            by_model[model_key] = (
                by_model.get(model_key, 0) + 1
            )
            by_label[label] = (
                by_label.get(label, 0) + 1
            )

        logger.info(
            "detection_pipeline_stage",
            job_id=job_id,
            asset_id=asset_id,
            stage=stage,
            count=len(detections),
            by_model=by_model,
            by_label=by_label,
        )

    async def _fail_item(
        self,
        session: Any,
        item: Any,
        batch_id: str,
        message: str = "",
        *,
        duration_ms: int | None = None,
        asset_id: str | None = None,
    ) -> None:
        """Mark a job item and its associated asset as FAILED in MongoDB cleanly."""
        item_id = (
            getattr(item, "id", None)
            or (item.get("id") if isinstance(item, dict) else str(item))
            if item else None
        )
        db = getattr(session, "db", None)
        if db is None:
            db = get_database()
        if item_id:
            await BatchService(db, self.settings).complete_item(
                item_id=item_id,
                status=JobItemStatus.FAILED.value,
                error_message=message,
                duration_ms=duration_ms,
            )
        target_asset_id = asset_id
        if not target_asset_id and item is not None:
            if isinstance(item, dict):
                target_asset_id = item.get("asset_id")
            else:
                target_asset_id = getattr(item, "asset_id", None)
        if target_asset_id:
            now = datetime.now(UTC)
            await db.assets.update_one(
                {"id": target_asset_id},
                {"$set": {"status": AssetStatus.FAILED.value, "updated_at": now}}
            )
        batch = await db.batches.find_one({"id": batch_id})
        if batch and not batch.get("error_summary"):
            await db.batches.update_one({"id": batch_id}, {"$set": {"error_summary": message}})
        logger.error(
            "job_item_failed",
            job_id=item_id,
            batch_id=batch_id,
            error=message,
            will_retry=False,
        )

    async def _process_video_item(
        self,
        *,
        item_id: str,
        batch_id: str,
        session: Any,
        item: JobItemRow,
        batch: BatchRow,
        project: ProjectRow,
        asset: AssetRow,
        labels: list[str],
        enabled_map: dict[str, bool],
        start: float,
        scene_evidence: Any,
        execution_plan: Any,
        ont_index: Any,
        source_plan: Any,
    ) -> None:
        import os
        import cv2
        import shutil
        import asyncio
        from datetime import UTC, datetime
        from app.inference.adapters.multimodal_experts import TrackerAdapter
        from app.services.annotations import AnnotationService
        from app.services.masks import MaskService
        from app.services.review_decision import decide_review
        from app.db.models import ModelRunRow, UsageEventRow
        from app.domain.enums import ModelRunStatus, JobItemStatus, AssetStatus, ReviewStatus, BatchStatus
        from app.inference.contracts import NormalizedDetection, BoundingBoxPercent
        from app.inference.merge import merge_detections

        # Scene discovery has already populated the video metadata by the
        # time this processing stage begins.
        fps = scene_evidence.metadata.get("fps") or 25.0
        frame_count = scene_evidence.metadata.get("frame_count") or 0
        duration = scene_evidence.metadata.get("duration") or 0.0

        logger.info(
            "video_processing_started",
            batch_id=batch_id,
            asset_id=asset.id,
            models=list(execution_plan.models),
            frame_count=frame_count,
        )

        def stage_log(event: str, started: float, **fields: Any) -> int:
            duration_ms = int((time.perf_counter() - started) * 1000)
            fields.setdefault("frame_count", frame_count)
            logger.info(
                event,
                asset_id=asset.id,
                batch_id=batch_id,
                duration_ms=duration_ms,
                **fields,
            )
            return duration_ms

        step_errors = []
        completed_models = []
        executed_models = []
        failed_models = []

        asset_sp = (
            getattr(asset, "storage_path", None)
            or (asset.get("storage_path") if isinstance(asset, dict) else None)
            or (asset.get("file_path") if isinstance(asset, dict) else None)
            or (asset.get("path") if isinstance(asset, dict) else None)
            or ""
        )
        path = self.storage.resolve(asset_sp)

        # Frame Sampling
        decode_started = time.perf_counter()
        logger.info(
            "video_decode_started",
            asset_id=asset.id,
            batch_id=batch_id,
            frame_count=frame_count,
        )
        logger.info(
            "video_frame_sampling_started",
            asset_id=asset.id,
            batch_id=batch_id,
            fps=fps,
            frame_count=frame_count,
        )

        step = max(1, int(fps / 5.0))
        sampled_frame_indices = list(range(0, frame_count, step))

        # Create temporary frames directory
        frames_dir = self.storage.asset_dir(project.id, asset.id) / "temp_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        sampled_frames = []
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            sampled_set = set(sampled_frame_indices)
            curr_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if curr_idx in sampled_set:
                    frame_path = frames_dir / f"frame_{curr_idx:06d}.jpg"
                    cv2.imwrite(str(frame_path), frame)
                    sampled_frames.append((curr_idx, frame_path))
                    logger.info(
                        "video_frame_selected",
                        asset_id=asset.id,
                        batch_id=batch_id,
                        frame_index=curr_idx,
                        timestamp=curr_idx / fps,
                    )
                curr_idx += 1
            cap.release()
        stage_log(
            "video_decode_completed",
            decode_started,
            frame_count=frame_count,
            processed_frames=len(sampled_frames),
        )

        # Dynamic Model Selection & Detection Loop
        # We will run detections on each frame
        detections_by_frame = {}
        all_raw_detections = []

        # Create ModelRunRows for active detectors
        detector_keys = [k for k in ["yolo26", "faster_rcnn", "dino"] if k in execution_plan.models and enabled_map.get(k, False)]
        detector_runs = {}
        for k in detector_keys:
            purpose = "Video frame detection"
            run = ModelRunRow(
                job_item_id=item_id,
                batch_id=batch_id,
                asset_id=asset.id,
                model_key=k,
                model_id=str(batch.model_id or k),
                status=ModelRunStatus.RUNNING.value,
                purpose=purpose,
                started_at=datetime.now(UTC),
            )
            session.add(run)
            executed_models.append(k)
            detector_runs[k] = (run, time.perf_counter())
        await commit_with_retry(session)

        detection_started = time.perf_counter()
        logger.info(
            "detection_started",
            asset_id=asset.id,
            batch_id=batch_id,
            frame_count=frame_count,
            processed_frames=len(sampled_frames),
        )
        for frame_idx, frame_path in sampled_frames:
            frame_raw_dets = []
            for k in detector_keys:
                logger.info(
                    "inference_started",
                    asset_id=asset.id,
                    batch_id=batch_id,
                    model=k,
                    frame_index=frame_idx,
                )
                try:
                    # Run model step
                    dets, _, model_id = await asyncio.to_thread(
                        self._run_model_step,
                        k,
                        frame_path,
                        asset.id,
                        labels,
                        [],
                        execution_plan=execution_plan,
                        scene_evidence=scene_evidence,
                        ont_index=ont_index,
                    )
                    for d in dets:
                        # Ensure model_key is set correctly
                        object.__setattr__(d, "model_key", k)
                    frame_raw_dets.extend(dets)
                    logger.info(
                        "inference_completed",
                        asset_id=asset.id,
                        batch_id=batch_id,
                        model=k,
                        frame_index=frame_idx,
                        detections=len(dets),
                    )
                    # Update model run ID
                    run_obj = detector_runs[k][0]
                    run_obj.model_id = model_id
                    if k not in completed_models:
                        completed_models.append(k)
                except Exception as exc:
                    logger.warning(
                        "model_run_failed_for_frame",
                        frame_index=frame_idx,
                        model=k,
                        error=str(exc),
                    )
                    step_errors.append(f"Frame {frame_idx} Model {k}: {exc}")
                    if k not in failed_models:
                        failed_models.append(k)

            # Merge raw detections for the current frame
            merged, merge_stats = merge_detections(
                frame_raw_dets,
                ont_index,
                iou_threshold=self.settings.merge_iou_threshold,
                max_box_area=self.settings.max_box_area_pct,
                review_risk_threshold=self.settings.review_risk_confidence_threshold,
                source_plan=source_plan,
                )
            detections_by_frame[frame_idx] = merged
            all_raw_detections.extend(merged)
        detector_runtime_ms = stage_log(
            "detection_completed",
            detection_started,
            detection_frames=sum(bool(dets) for dets in detections_by_frame.values()),
            processed_frames=len(sampled_frames),
        )

        # Update detector ModelRunRows status at the end
        for k, (run_obj, start_time) in detector_runs.items():
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            run_obj = await session.get(ModelRunRow, run_obj.id)
            if run_obj:
                run_obj.duration_ms = duration_ms
                run_obj.finished_at = datetime.now(UTC)
                if k in failed_models and k not in completed_models:
                    run_obj.status = ModelRunStatus.FAILED.value
                else:
                    run_obj.status = ModelRunStatus.SUCCEEDED.value
                    run_obj.detection_count = len([d for d in all_raw_detections if d.model_key == k])
                session.add(run_obj)
                
                # Add usage event
                session.add(
                    UsageEventRow(
                        project_id=batch.project_id,
                        kind="cv_inference",
                        model_id=run_obj.model_id,
                        asset_id=asset.id,
                        batch_id=batch_id,
                        duration_ms=duration_ms,
                        detection_count=run_obj.detection_count,
                        tokens_in=0,
                        tokens_out=0,
                        cost_usd=None,
                    )
                )
        await commit_with_retry(session)

        # Object Tracking
        tracking_started = time.perf_counter()
        logger.info("tracking_started", asset_id=asset.id, batch_id=batch_id, frame_count=frame_count)
        sorted_frame_indices = sorted(detections_by_frame.keys())
        tracker_input = []
        for f_idx in sorted_frame_indices:
            frame_dets = detections_by_frame[f_idx]
            det_dicts = []
            for d in frame_dets:
                det_dicts.append({
                    "bbox": d.bbox,
                    "label": d.label,
                    "confidence": d.confidence,
                    "class_id": d.class_id,
                    "model_id": d.model_id,
                    "model_key": d.model_key,
                    "inferred_at": d.inferred_at,
                    "provenance": d.provenance,
                    "original_id": d.id,
                })
            tracker_input.append(det_dicts)

        if self.runtime is not None:
            tracker = self.runtime.registry.get("tracker")
        else:
            tracker = TrackerAdapter()
        tracker.load()
        if self.mcp_client is not None and self.settings.mcp_enabled:
            track_result = self.mcp_client.vision.track_objects(
                tracker_input, asset_id=asset.id, iou_threshold=0.3
            )
            if track_result.success:
                tracked_frames = track_result.data
            else:
                tracked_frames = tracker.track(tracker_input, iou_threshold=0.3)
        else:
            tracked_frames = tracker.track(tracker_input, iou_threshold=0.3)
        tracker_runtime_ms = stage_log(
            "tracking_completed",
            tracking_started,
            tracking_frames=len(tracked_frames),
            active_tracks=len({d["track_id"] for frame in tracked_frames for d in frame}),
        )

        # Reconstruct tracked detections and assign colors
        final_detections = []
        all_tracked_detections = []

        COLORS = [
            "#FF5733", "#33FF57", "#3357FF", "#F3FF33", "#FF33F3", "#33FFF3",
            "#FFA833", "#A833FF", "#33FFA8", "#FF3380", "#3380FF", "#80FF33",
            "#FF8033", "#8033FF", "#33FF80", "#FF33D1", "#33D1FF", "#D1FF33",
        ]

        def get_track_color(tid: int) -> str:
            return COLORS[tid % len(COLORS)]

        unique_track_ids = set()
        for i, frame_idx in enumerate(sorted_frame_indices):
            ts = frame_idx / fps
            for td in tracked_frames[i]:
                tid = td["track_id"]
                unique_track_ids.add(tid)
                color = get_track_color(tid)
                det = NormalizedDetection(
                    id=td.get("original_id") or NormalizedDetection.new_id(),
                    asset_id=asset.id,
                    label=td["label"],
                    class_id=td["class_id"],
                    bbox=td["bbox"],
                    confidence=td["confidence"],
                    model_id=td["model_id"],
                    model_key=td["model_key"],
                    inferred_at=td["inferred_at"],
                    provenance={
                        **(td["provenance"] or {}),
                        "track_id": tid,
                        "frame_number": frame_idx,
                        "frame_index": frame_idx,
                        "timestamp": ts,
                        "source_model": td["model_key"],
                        "detector_source": td["model_key"],
                        "model_confidence": td["confidence"],
                        "tracking_state": "tracked",
                        "color": color,
                        "track_color": color,
                    }
                )
                final_detections.append(det)
                all_tracked_detections.append(det)

        # SAM2 Frame Segmentation (Optional)
        all_masks = []
        if enabled_map.get("sam2", False) and "sam2" in execution_plan.models and final_detections:
            executed_models.append("sam2")
            run = ModelRunRow(
                job_item_id=item_id,
                batch_id=batch_id,
                asset_id=asset.id,
                model_key="sam2",
                model_id=str(batch.model_id or "sam2"),
                status=ModelRunStatus.RUNNING.value,
                purpose="SAM2 Video segmentation",
                started_at=datetime.now(UTC),
            )
            session.add(run)
            await commit_with_retry(session)
            run_start = time.perf_counter()

            try:
                for frame_idx, frame_path in sampled_frames:
                    frame_dets = [d for d in final_detections if d.provenance["frame_number"] == frame_idx]
                    if not frame_dets:
                        continue
                    masks = await asyncio.to_thread(
                        self.runtime.registry.get("sam2").segment_boxes,
                        frame_path,
                        asset_id=asset.id,
                        boxes=[d.bbox for d in frame_dets],
                        labels=[d.label for d in frame_dets],
                        annotation_ids=[d.id for d in frame_dets],
                        storage_dir=self.storage.root / "masks" / asset.id,
                    )
                    all_masks.extend(masks)

                duration_ms = int((time.perf_counter() - run_start) * 1000)
                run = await session.get(ModelRunRow, run.id)
                if run:
                    run.model_id = self.runtime.registry.get("sam2").model_id
                    run.mask_count = len(all_masks)
                    run.duration_ms = duration_ms
                    run.status = ModelRunStatus.SUCCEEDED.value
                    run.finished_at = datetime.now(UTC)
                    completed_models.append("sam2")

                    session.add(
                        UsageEventRow(
                            project_id=batch.project_id,
                            kind="cv_inference",
                            model_id=run.model_id,
                            asset_id=asset.id,
                            batch_id=batch_id,
                            duration_ms=duration_ms,
                            detection_count=0,
                            tokens_in=0,
                            tokens_out=0,
                            cost_usd=None,
                        )
                    )
            except Exception as exc:
                failed_models.append("sam2")
                logger.warning("sam2_failed_for_video", error=str(exc))
                step_errors.append(f"sam2: {exc}")
                run = await session.get(ModelRunRow, run.id)
                if run:
                    run.model_id = self.runtime.registry.get("sam2").model_id
                    run.duration_ms = int((time.perf_counter() - run_start) * 1000)
                    run.error_message = str(exc)
                    run.finished_at = datetime.now(UTC)
                    run.status = ModelRunStatus.FAILED.value
            await commit_with_retry(session)

        # Verification & Review Decision
        verification_started = time.perf_counter()
        logger.info("verification_started", asset_id=asset.id, batch_id=batch_id)
        review_decision = decide_review(
            merged=final_detections,
            all_detections=all_tracked_detections,
            scene_evidence=scene_evidence,
            completed_models=completed_models,
            required_verification=execution_plan.verification,
            rejected_count=0,
            model_availability={k: bool(v) for k, v in enabled_map.items()},
            auto_approve_threshold=project.quality_policy.get("auto_approve_threshold", 0.90) if project.quality_policy else 0.90,
        )
        final_detections = _attach_verification_evidence(
            final_detections,
            all_tracked_detections,
            decision=review_decision,
        )
        verification_runtime_ms = stage_log(
            "verification_completed",
            verification_started,
            detections=len(final_detections),
        )

        # Persistence
        persistence_started = time.perf_counter()
        logger.info(
            "annotation_generation_started",
            asset_id=asset.id,
            batch_id=batch_id,
            detections=len(final_detections),
        )
        if await self._should_stop_for_project(session, item_id, batch.project_id):
            return
        ann_svc = AnnotationService(session)
        ann_result, _ = await ann_svc.replace_ai_detections(
            asset.id, final_detections, model_id="pipeline", project_id=batch.project_id, job_item_id=item_id, batch_id=batch_id
        )
        count = len(ann_result)
        annotation_generation_runtime_ms = stage_log(
            "annotation_generation_completed",
            persistence_started,
            annotation_count=count,
        )
        persistence_completed_started = time.perf_counter()
        logger.info("persistence_started", asset_id=asset.id, batch_id=batch_id, annotation_count=count)
        # replace_ai_detections commits its short transaction; this event keeps
        # persistence timing distinct from annotation preparation.
        persistence_runtime_ms = stage_log("persistence_completed", persistence_completed_started, annotation_count=count)
        logger.info("annotation_persisted", asset_id=asset.id, count=count)

        if all_masks:
            mask_svc = MaskService(session, self.storage)
            await mask_svc.replace_ai_masks(asset.id, all_masks, commit=False)
            logger.info("masks_persisted", asset_id=asset.id, count=len(all_masks))

        # Cleanup temporary frames
        try:
            shutil.rmtree(str(frames_dir))
        except Exception as exc:
            logger.warning("cleanup_temp_frames_failed", error=str(exc))

        # Finalize asset and item state
        item = await session.get(JobItemRow, item_id)
        asset = await session.get(AssetRow, asset.id)
        assert item is not None and asset is not None

        duration_ms = int((time.perf_counter() - start) * 1000)
        item.status = JobItemStatus.SUCCEEDED.value
        item.detection_count = count
        item.duration_ms = duration_ms
        item.finished_at = datetime.now(UTC)
        item.error_message = "; ".join(step_errors) if step_errors else ""

        asset.status = AssetStatus.READY.value
        proj = await session.get(ProjectRow, asset.project_id) if asset else None
        thresh = float(proj.quality_policy.get("auto_approve_threshold", 0.92)) if proj and proj.quality_policy else 0.92
        valid_final_confidences = [
            float(d.confidence)
            for d in final_detections
            if d.confidence is not None
            and isinstance(d.confidence, (int, float))
            and not isinstance(d.confidence, bool)
            and 0.0 <= float(d.confidence) <= 1.0
            and getattr(d, "source", "ai") not in ("human", "human_modified")
        ] if final_detections else []
        if valid_final_confidences:
            img_mean = sum(valid_final_confidences) / len(valid_final_confidences)
            asset.mean_confidence = img_mean
            if img_mean >= thresh:
                asset.review_status = ReviewStatus.AUTO_APPROVED.value
                asset.review_reason = f"Auto-approved: image confidence {round(img_mean * 100, 1)}% >= review threshold {round(thresh * 100)}%"
            else:
                asset.review_status = ReviewStatus.HUMAN_REVIEW.value
                asset.review_reason = f"LOW_CONFIDENCE: image confidence {round(img_mean * 100, 1)}% < review threshold {round(thresh * 100)}%"
        else:
            asset.mean_confidence = None
            asset.review_status = ReviewStatus.HUMAN_REVIEW.value
            asset.review_reason = "NO_VALID_AI_DETECTIONS"
        
        await commit_with_retry(session)
        batch_completion_started = time.perf_counter()
        logger.info("batch_completion_started", asset_id=asset.id, batch_id=batch_id)
        logger.info(
            "job_item_completed",
            job_id=item_id,
            batch_id=batch_id,
            asset_id=asset.id,
            duration_ms=duration_ms,
            detections=count,
            tracks=len(unique_track_ids),
        )

        batch_svc = BatchService(session, self.settings)
        await batch_svc.finalize_if_done(batch_id)
        stage_log("batch_completion_completed", batch_completion_started)
        total_runtime_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "video_processing_stats",
            asset_id=asset.id,
            width=asset.width,
            height=asset.height,
            fps=fps,
            total_frames=frame_count,
            processed_frames=len(sampled_frames),
            detection_frames=sum(bool(dets) for dets in detections_by_frame.values()),
            tracking_frames=len(tracked_frames),
            skipped_frames=max(0, frame_count - len(sampled_frames)),
            effective_processing_fps=(frame_count / (total_runtime_ms / 1000.0)) if total_runtime_ms else 0.0,
        )
        logger.info(
            "video_processing_summary",
            asset_id=asset.id,
            video_width=asset.width,
            video_height=asset.height,
            fps=fps,
            total_frames=frame_count,
            processed_frames=len(sampled_frames),
            detection_frames=sum(bool(dets) for dets in detections_by_frame.values()),
            tracking_frames=len(tracked_frames),
            effective_processing_fps=(frame_count / (total_runtime_ms / 1000.0)) if total_runtime_ms else 0.0,
            detector_runtime_ms=detector_runtime_ms,
            tracker_runtime_ms=tracker_runtime_ms,
            verification_runtime_ms=verification_runtime_ms,
            persistence_runtime_ms=persistence_runtime_ms,
            total_runtime_ms=total_runtime_ms,
            detections=count,
            tracks=len(unique_track_ids),
            workers_used=self._parallel_workers,
            model_device=(
                getattr(self.runtime.registry._adapters.get("yolo26"), "device", "unknown")
                if self.runtime else "unknown"
            ),
            fallback_triggered=False,
            fallback_strategy="none",
        )
        logger.info("video_processing_completed", asset_id=asset.id, batch_id=batch_id, duration_ms=total_runtime_ms)
        logger.info("batch_progress_updated", batch_id=batch_id)


_worker: BatchWorker | None = None


def get_worker() -> BatchWorker | None:
    return _worker


def set_worker(worker: BatchWorker | None) -> None:
    global _worker
    _worker = worker
