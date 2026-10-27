import asyncio
from app.db.firebase import FirebaseDatabase
from app.services.annotations import AnnotationService

async def main():
    db = FirebaseDatabase()
    svc = AnnotationService(db)
    anns = await svc.list_for_asset("b6fd39e5-4d8b-4bf0-8527-1896df1ecd14")
    print("ANNOTATIONS COUNT FOR ASSET:", len(anns))
    for a in anns[:5]:
        print("  ANN:", a.get("id"), a.get("label"), a.get("confidence"), a.get("geometry_type"), a.get("geometry"))
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
