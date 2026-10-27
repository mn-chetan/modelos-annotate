import asyncio
import time
from app.db.firebase import FirebaseDatabase
from app.config import get_settings
from app.storage.files import FileStorage
from app.jobs.worker import BatchWorker
from app.services.batches import BatchService
from app.api.schemas import BatchCreate
from app.domain.enums import BatchStatus, JobItemStatus
from app.inference.registry import get_runtime
from app.inference.detector import create_detector_from_settings
from app.services.annotations import AnnotationService

async def main():
    print("=== STARTING FULL END-TO-END BATCH EXECUTION TEST ===")
    db = FirebaseDatabase()
    settings = get_settings()
    storage = FileStorage(settings.storage_dir)
    detector = create_detector_from_settings(settings)
    runtime = get_runtime()
    
    project_id = "6024d9a4-cdb0-4334-8361-06e27e315954"
    assets = await db.assets.find({"project_id": project_id}).to_list(10)
    asset_ids = [a["id"] for a in assets[:3]]
    print(f"1. Target Project: {project_id}, Assets: {asset_ids}")
    assert len(asset_ids) == 3, f"Expected 3 assets, got {len(asset_ids)}"

    # Clean any stale active batches for this project to test cleanly
    await db.batches.delete_many({"project_id": project_id})
    await db.job_items.delete_many({"asset_id": {"$in": asset_ids}})
    
    # 2. Create batch
    batch_svc = BatchService(db, settings)
    batch_out = await batch_svc.create(project_id, BatchCreate(asset_ids=asset_ids))
    batch_id = batch_out["id"]
    print(f"2. Batch created: {batch_id}, total={batch_out['total']}, status={batch_out['status']}")
    assert batch_out["status"] == BatchStatus.QUEUED.value
    assert batch_out["total"] == 3

    # Check job_items created in status=queued
    queued_in_db = await db.job_items.find({"batch_id": batch_id, "status": JobItemStatus.QUEUED.value}).to_list(10)
    print(f"3. Job items created with status=queued: count={len(queued_in_db)}")
    assert len(queued_in_db) == 3

    # 4. Start BatchWorker
    worker = BatchWorker(settings=settings, storage=storage, runtime=runtime, detector=detector, db=db)
    print(f"4. BatchWorker initialized: {worker.worker_identity}")
    
    # 5. Execute worker claim and spawn
    claimed = await worker._claim_and_spawn()
    print(f"5. Worker claim result: claimed={claimed}, active_tasks={len(worker._job_tasks)}")
    assert claimed is True
    assert len(worker._job_tasks) == 3

    # 6. Wait for all 3 job tasks to finish
    tasks = [entry[2] for entry in worker._job_tasks.values()]
    print(f"6. Waiting for {len(tasks)} inference tasks to complete...")
    start_wait = time.perf_counter()
    await asyncio.gather(*tasks, return_exceptions=True)
    wait_duration = time.perf_counter() - start_wait
    print(f"7. All tasks finished in {wait_duration:.1f}s")

    # 7. Check database state
    batch_final = await db.batches.find_one({"id": batch_id})
    print(f"8. Final Batch Document: status={batch_final.get('status')}, completed={batch_final.get('completed')}, failed={batch_final.get('failed')}, total={batch_final.get('total')}")

    job_items_final = await db.job_items.find({"batch_id": batch_id}).to_list(10)
    for it in job_items_final:
        print(f"   Job Item: {it.get('id')} asset={it.get('asset_id')} status={it.get('status')} detections={it.get('detection_count')} error={it.get('error_message')}")

    # 8. Check annotations via AnnotationService
    ann_svc = AnnotationService(db)
    for aid in asset_ids:
        anns = await ann_svc.list_for_asset(aid)
        print(f"9. Asset {aid} persisted annotations: count={len(anns)}")
        if len(anns) > 0:
            print(f"   Sample: label={anns[0].get('label')}, confidence={anns[0].get('confidence')}, bbox/geom={anns[0].get('geometry')}")

    await db.close()
    print("=== END-TO-END TEST COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(main())
