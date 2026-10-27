import asyncio
import traceback
from app.db.firebase import FirebaseDatabase
from app.config import get_settings
from app.storage.files import FileStorage
from app.jobs.worker import BatchWorker
from app.inference.registry import get_runtime
from app.inference.detector import create_detector_from_settings

async def main():
    db = FirebaseDatabase()
    settings = get_settings()
    storage = FileStorage(settings.storage_dir)
    detector = create_detector_from_settings(settings)
    runtime = get_runtime()
    worker = BatchWorker(settings=settings, storage=storage, runtime=runtime, detector=detector, db=db)
    
    # Try item that failed
    item_id = "19035bc5-5951-4ddf-8339-a0d44debc13d"
    batch_id = "ca52679e-0183-455a-91eb-78e5c7774927"
    try:
        await worker._process_item(item_id, batch_id)
    except Exception as exc:
        traceback.print_exc()
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
