from __future__ import annotations

import pytest

from app.errors import NotFoundError
from app.api.schemas import ProjectUpdate
from app.services.projects import ProjectService


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return self.docs[:length] if length is not None else list(self.docs)


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.deleted = []

    async def find_one(self, query):
        key, value = next(iter(query.items()))
        return next((doc for doc in self.docs if doc.get(key) == value), None)

    def find(self, _query):
        return _Cursor(self.docs)

    async def delete_many(self, query):
        self.deleted.append(query)

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return


class _Database:
    provider = "firebase"
    connection_status = "healthy"
    is_healthy = True
    client = object()

    def __init__(self):
        self.projects = _Collection([{"id": "project-1", "name": "Test"}])
        self.assets = _Collection([{"id": "asset-1", "project_id": "project-1"}])
        for name in ("annotations", "decisions", "audit_events", "review_notes", "model_runs", "batch_jobs", "job_items", "color_maps", "batches", "masks", "project_recons", "taxonomies", "cloud_imports"):
            setattr(self, name, _Collection())


@pytest.mark.asyncio
async def test_delete_existing_project_completes_cascade():
    db = _Database()
    assert await ProjectService(db).delete("project-1") is True
    assert db.projects.deleted == [{"id": "project-1"}]
    assert {"project_id": "project-1"} in db.assets.deleted
    assert {"asset_id": {"$in": ["asset-1"]}} in db.annotations.deleted


@pytest.mark.asyncio
async def test_delete_nonexistent_project_preserves_not_found():
    with pytest.raises(NotFoundError):
        await ProjectService(_Database()).delete("missing-project")


@pytest.mark.asyncio
async def test_update_project_uses_supported_equality_queries_and_preserves_fields(monkeypatch):
    db = _Database()
    db.projects.docs[0].update({"goal": "keep", "labels": ["person"]})
    service = ProjectService(db)

    async def read_updated(project_id):
        return next(doc for doc in db.projects.docs if doc["id"] == project_id)

    monkeypatch.setattr(service, "get", read_updated)
    updated = await service.update("project-1", ProjectUpdate(name="Renamed"))

    assert updated["name"] == "Renamed"
    assert updated["goal"] == "keep"
    assert updated["labels"] == ["person"]


@pytest.mark.asyncio
async def test_update_nonexistent_project_preserves_not_found():
    with pytest.raises(NotFoundError):
        await ProjectService(_Database()).update("missing-project", ProjectUpdate(name="Renamed"))
