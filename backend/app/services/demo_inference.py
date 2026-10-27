"""Explicit image-only demo execution using real model adapters and existing jobs."""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.inference.merge import merge_detections
from app.inference.ontology_map import build_ontology_index
from app.services.annotations import AnnotationService
from app.services.batches import BatchService


async def run_demo_image(db, settings, storage, runtime, project, asset, item, batch_id):
    if project.get("modality", "image") != "image" or project.get("task_type") != "object_detection":
        raise ValueError("Demo processing supports image object detection only")
    if settings.force_fake:
        raise ValueError("Fake models are not allowed in the demo image pipeline")
    labels = list(project.get("labels") or [])
    if not labels:
        raise ValueError("Define project classes before running AI")
    path = storage.resolve(asset.get("storage_path") or "")
    if not path.is_file():
        raise ValueError("Uploaded image file is unavailable")
    await db.assets.update_one({"id": asset.id}, {"$set": {"status": "processing", "inference_error": None}})
    detections, errors, runs = [], [], []
    caption = None
    started = time.perf_counter()
    for key in ("florence", "yolo26", "dino"):
        run_id, tick = str(uuid4()), time.perf_counter()
        run = {"id": run_id, "project_id": project.id, "asset_id": asset.id,
               "job_item_id": item.id, "batch_id": batch_id, "model_key": key,
               "status": "running", "started_at": datetime.now(UTC)}
        await db.model_runs.insert_one(run)
        try:
            if not await asyncio.to_thread(runtime.registry.try_load, key):
                raise RuntimeError(f"{key} unavailable: {runtime.registry._errors.get(key, 'disabled or missing')}")
            adapter = runtime.registry.get(key)
            run["model_id"] = adapter.model_id
            if key == "florence":
                # The worker is serial in the demo profile; the adapter is reused.
                assist = await asyncio.to_thread(adapter.assist, path, asset_id=asset.id, labels=labels, goal=project.get("goal", ""))
                caption = assist.caption
                run["caption"] = caption
                run["detection_count"] = 0
            else:
                result = await asyncio.to_thread(runtime.detect, key, path, asset_id=asset.id, labels=labels)
                detections.extend(result)
                run["detection_count"] = len(result)
            run["status"] = "succeeded"
        except Exception as exc:
            run.update(status="failed", error_message=str(exc))
            errors.append(f"{key}: {exc}")
        run.update(duration_ms=int((time.perf_counter()-tick)*1000), finished_at=datetime.now(UTC))
        await db.model_runs.update_one({"id": run_id}, {"$set": run})
        runs.append(run_id)
    # Do not publish partial/empty output as successful when any required model failed.
    if errors:
        message = "; ".join(errors)
        await db.assets.update_one({"id": asset.id}, {"$set": {"inference_error": message}})
        raise RuntimeError(message)
    index = build_ontology_index(labels=labels, ontology=list(project.get("label_ontology") or []))
    merged, _ = merge_detections(detections, index, iou_threshold=settings.merge_iou_threshold,
                                 max_box_area=settings.max_box_area_pct,
                                 review_risk_threshold=settings.review_risk_confidence_threshold)
    await AnnotationService(db).replace_ai_detections(
        asset.id, merged, "yolo26+dino", project_id=project.id, job_item_id=item.id,
        batch_id=batch_id, run_provenance={"pipeline": "demo_image", "model_run_ids": runs})
    now = datetime.now(UTC)
    await db.assets.update_one({"id": asset.id}, {"$set": {
        "status": "annotated", "review_status": "needs_review", "caption": caption,
        "inference_error": None, "ai_completed_at": now, "updated_at": now}})
    await BatchService(db, settings).complete_item(
        item_id=item.id, status="succeeded", detection_count=len(merged),
        duration_ms=int((time.perf_counter()-started)*1000))
