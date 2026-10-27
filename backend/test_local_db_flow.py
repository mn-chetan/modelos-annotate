import asyncio
import httpx
from app.main import create_app

async def verify():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/health")
            print("Health check status:", resp.status_code, resp.json())
            assert resp.status_code == 200

            resp = await client.get("/api/v1/projects")
            print("Projects list status:", resp.status_code)
            projects = resp.json()
            print("Projects count in local DB:", len(projects))

            payload = {
                "name": "Local Isolated Test Project",
                "goal": "Testing local DB write flow",
                "task_type": "object_detection",
                "labels": ["cat", "dog"],
            }
            create_resp = await client.post("/api/v1/projects", json=payload)
            print("Create project status:", create_resp.status_code)
            assert create_resp.status_code == 201
            created_id = create_resp.json()["id"]
            print("Created local project ID:", created_id)

            get_resp = await client.get(f"/api/v1/projects/{created_id}")
            print("Get created project status:", get_resp.status_code)
            assert get_resp.status_code == 200
            assert get_resp.json()["name"] == "Local Isolated Test Project"
            print("ALL READ AND WRITE FLOWS VERIFIED ON LOCAL DATABASE!")

if __name__ == "__main__":
    asyncio.run(verify())
