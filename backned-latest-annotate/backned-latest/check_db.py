import asyncio
from app.db.firebase import FirebaseDatabase

async def main():
    db = FirebaseDatabase()
    b = await db.batches.find_one({"id": "6d1b6d4b-3370-49e7-b5cd-ea9729e98c0e"})
    print("BATCH:", b)
    items = await db.job_items.find({"batch_id": "6d1b6d4b-3370-49e7-b5cd-ea9729e98c0e"}).to_list(10)
    for it in items:
        print("  ITEM:", it.get("id"), "STATUS:", it.get("status"), "ATTEMPT:", it.get("attempt"), "ERROR:", it.get("error_message"))
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
