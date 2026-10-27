import asyncio

from app.db.firebase import FirebaseDatabase, verify_database_safety_guard
from app.services.projects import ProjectService


async def main():
    verify_database_safety_guard()
    db = FirebaseDatabase()
    service = ProjectService(db)

    docs = await db.projects.find({}).to_list(length=100000)
    ids = [str(d.get("id") or d.get("_id")) for d in docs]

    print(f"Found {len(ids)} projects.")

    deleted = 0
    for project_id in ids:
        confirm = input(f"Type DELETE to remove {project_id}: ")
        if confirm != "DELETE":
            print(f"Skipped {project_id}")
            continue

        await service.delete(project_id)
        deleted += 1
        print(f"Deleted {project_id}")

    remaining = await db.projects.find({}).to_list(length=100000)
    print(f"Deleted: {deleted}")
    print(f"Remaining: {len(remaining)}")

    await db.close()


asyncio.run(main())