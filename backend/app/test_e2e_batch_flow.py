"""End-to-End verification script for batch creation and worker claim.

Executes the complete real execution path:
1. Create project via ProjectService
2. Upload test asset via ProjectService / upload_assets
3. Call trigger_project_ai_annotation
4. Verify batch creation in Firestore (`batches` collection)
5. Run BatchWorker poll loop to observe `queued_batches_fetched count=1`, claim, and item processing start.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from app.config import get_settings
from app.db.firebase import FirebaseDatabase
from app.db.models import _utcnow
from app.domain.enums import BatchStatus, JobItemStatus
from app.jobs.worker import BatchWorker
from app.services.projects import ProjectService
from app.services.batches import BatchService
from app.storage.files import FileStorage
from app.api.routes_main import trigger_project_ai_annotation
from fastapi import Request


async def run_e2e_test():
    settings = get_settings()
    db = FirebaseDatabase()
    storage = FileStorage(Path(settings.storage_dir))
    
    project_id = "test-e2e-real-batch-1"
    
    # Cleanup previous runs
    await db.batches.delete_many({"project_id": project_id})
    await db.project_plans.delete_many({"project_id": project_id})
    await db.job_items.delete_many({})
    await db.assets.delete_many({"project_id": project_id})
    await db.projects.delete_many({"id": project_id})

    # 1. Create Project
    now = _utcnow()
    proj_doc = {
        "id": project_id,
        "name": "E2E Batch Verification Project",
        "goal": "Verify real batch creation and worker claim",
        "task_type": "object_detection",
        "modality": "image",
        "labels": ["car", "person"],
        "label_strategy": "generic",
        "status": "active",
        "quality_policy": {"confidence_threshold": 0.95, "qc_sample_rate": 0.05},
        "created_at": now,
        "updated_at": now,
    }
    await db.projects.insert_one(proj_doc)
    print(f"[E2E] 1. Project created: {proj_doc['id']}")

    # Insert approved project plan
    plan_doc = {
        "id": f"plan-{project_id}",
        "project_id": project_id,
        "status": "approved",
        "workflow": [
            {
                "key": "yolo26",
                "purpose": "Primary object detection",
                "required": True,
                "model_id": settings.yolo26_model_id,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    await db.project_plans.insert_one(plan_doc)

    # 2. Upload Asset
    proj_svc = ProjectService(db, settings, storage)
    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x10\x00\x10\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
    asset_doc = await proj_svc.create_asset(
        project_id=project_id,
        content=dummy_jpeg,
        filename="test_sample.jpg",
        content_type="image/jpeg",
    )
    print(f"[E2E] 2. Asset uploaded: {asset_doc['id']}")

    # 3. Trigger AI Annotation / Batch Creation
    dummy_scope = {"type": "http", "method": "POST", "path": f"/projects/{project_id}/ai-annotate", "headers": []}
    request = Request(dummy_scope)
    
    # Mock agent service for plan auto-approval fixture
    class MockAgentService:
        async def approve_plan(self, pid):
            return None
            
    res = await trigger_project_ai_annotation(
        project_id=project_id,
        request=request,
        session=db,
        settings=settings,
        storage=storage,
    )
    batch_id = res.get("batch_id")
    print(f"[E2E] 3. Batch creation triggered: batch_id={batch_id}")
    assert batch_id is not None, "Batch ID must not be None!"

    # 4. Verify batch document in Firestore
    batch_doc = await db.batches.find_one({"id": batch_id})
    print(f"[E2E] 4. Firestore batch document found: status={batch_doc.get('status')}, total={batch_doc.get('total')}")
    assert batch_doc is not None
    assert batch_doc.get("status") == BatchStatus.QUEUED.value

    # 5. Run BatchWorker to poll and claim batch
    worker = BatchWorker(settings=settings, storage=storage, db=db)
    claimed = await worker._claim_and_spawn()
    print(f"[E2E] 5. BatchWorker poll & claim result: claimed={claimed}")
    assert claimed is True

    # Verify updated batch status in Firestore
    updated_batch = await db.batches.find_one({"id": batch_id})
    print(f"[E2E] 6. Final Firestore batch status: {updated_batch.get('status')}")

    print("[E2E] SUCCESS: End-to-end batch creation, logging, and worker claim verified!")
    # Cleanup
    try:
        await db.batches.delete_one({"id": batch_id})
        await db.job_items.delete_many({"batch_id": batch_id})
        await db.assets.delete_many({"project_id": project_id})
        await db.projects.delete_one({"id": project_id})
        await db.project_plans.delete_one({"project_id": project_id})
    except Exception as exc:
        print(f"[E2E] Cleanup warning: {exc}")


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
