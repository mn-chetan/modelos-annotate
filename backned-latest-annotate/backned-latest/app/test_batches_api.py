"""Regression tests for batch endpoints, prefix mounting, and trailing-slash routing.

Verifies:
1. /api/v1/projects/{project_id}/batches returns 200 OK
2. /api/v1/projects/{project_id}/batches/ returns 200 OK directly without 307 redirect
3. /app1/api/v1/projects/{project_id}/batches returns 200 OK
4. /app1/api/v1/projects/{project_id}/batches/ returns 200 OK
5. /api/v1/batches/{batch_id} returns 200 OK
6. /api/v1/batches/{batch_id}/ returns 200 OK
7. Proper BatchOut schema serialization
"""

import pytest
from httpx import ASGITransport, AsyncClient
from datetime import datetime, timezone
from app.main import app
from app.api import deps
from app.config import get_settings


class MockCursor:
    def __init__(self, items):
        self._items = items

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self._items)


class MockCollection:
    def __init__(self, initial_docs=None):
        self.docs = list(initial_docs or [])

    def find(self, filter_dict=None):
        res = []
        for d in self.docs:
            match = True
            for k, v in (filter_dict or {}).items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                res.append(d)
        return MockCursor(res)

    async def find_one(self, filter_dict=None):
        for d in self.docs:
            match = True
            for k, v in (filter_dict or {}).items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                return d
        return None


class MockDatabase:
    def __init__(self, batches):
        self.batches = MockCollection(batches)
        self.job_items = MockCollection([])
        self.model_runs = MockCollection([])
        self.projects = MockCollection([])
        self.provider = "mock"
        self.is_healthy = True


@pytest.fixture
def mock_db():
    now = datetime.now(timezone.utc)
    batch_doc = {
        "id": "batch-regression-1",
        "project_id": "test-batches-regression-project",
        "status": "completed",
        "idempotency_key": None,
        "total": 1,
        "completed": 1,
        "failed": 0,
        "running": 0,
        "model_id": "yolo26n",
        "workflow": [],
        "metrics": {},
        "error_summary": "",
        "items": [],
        "created_at": now,
        "updated_at": now,
        "started_at": now,
        "finished_at": now,
    }
    return MockDatabase([batch_doc])


@pytest.mark.asyncio
async def test_batch_routes_prefix_and_trailing_slash(mock_db):
    project_id = "test-batches-regression-project"
    settings = get_settings()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_app_settings] = lambda: settings
    app.state.settings = settings

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            # Test 1: Canonical /api/v1 endpoint without trailing slash
            resp1 = await client.get(f"/api/v1/projects/{project_id}/batches")
            assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}"
            data1 = resp1.json()
            assert isinstance(data1, list)
            assert len(data1) == 1
            assert data1[0]["id"] == "batch-regression-1"
            assert data1[0]["project_id"] == project_id
            assert data1[0]["status"] == "completed"

            # Test 2: Canonical /api/v1 endpoint with trailing slash (must be 200, not 307 redirect)
            resp2 = await client.get(f"/api/v1/projects/{project_id}/batches/", follow_redirects=False)
            assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}"
            data2 = resp2.json()
            assert isinstance(data2, list)
            assert len(data2) == 1
            assert data2[0]["id"] == "batch-regression-1"

            # Test 3: Reverse-proxy /app1 prefix without trailing slash
            resp3 = await client.get(f"/app1/api/v1/projects/{project_id}/batches")
            assert resp3.status_code == 200, f"Expected 200, got {resp3.status_code}"
            data3 = resp3.json()
            assert isinstance(data3, list)
            assert len(data3) == 1
            assert data3[0]["id"] == "batch-regression-1"

            # Test 4: Reverse-proxy /app1 prefix with trailing slash
            resp4 = await client.get(f"/app1/api/v1/projects/{project_id}/batches/", follow_redirects=False)
            assert resp4.status_code == 200, f"Expected 200, got {resp4.status_code}"
            data4 = resp4.json()
            assert isinstance(data4, list)
            assert len(data4) == 1
            assert data4[0]["id"] == "batch-regression-1"

            # Test 5: Single batch detail with and without trailing slash
            resp5a = await client.get("/api/v1/batches/batch-regression-1")
            assert resp5a.status_code == 200
            assert resp5a.json()["id"] == "batch-regression-1"

            resp5b = await client.get("/api/v1/batches/batch-regression-1/", follow_redirects=False)
            assert resp5b.status_code == 200
            assert resp5b.json()["id"] == "batch-regression-1"

            resp5c = await client.get("/app1/api/v1/batches/batch-regression-1")
            assert resp5c.status_code == 200
            assert resp5c.json()["id"] == "batch-regression-1"

            resp5d = await client.get("/app1/api/v1/batches/batch-regression-1/", follow_redirects=False)
            assert resp5d.status_code == 200
            assert resp5d.json()["id"] == "batch-regression-1"
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        app.dependency_overrides.pop(deps.get_app_settings, None)
