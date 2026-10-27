"""Tests for Firebase Firestore database adapter and SQLite-to-Firebase migration."""

from __future__ import annotations

import pytest
from pathlib import Path

from app.db.firebase import FirebaseDatabase
from app.db.migration import migrate_sqlite_to_firebase


@pytest.mark.asyncio
async def test_firebase_collection_crud_operations():
    db = FirebaseDatabase()
    col = db["test_projects"]
    await col.delete_many({})

    # 1. Insert document
    res = await col.insert_one({"id": "proj-1", "name": "Vision AI", "status": "draft"})
    assert res.acknowledged is True
    assert res.inserted_id == "proj-1"

    # 2. Find one
    doc = await col.find_one({"id": "proj-1"})
    assert doc is not None
    assert doc["name"] == "Vision AI"

    # 3. Update one
    up_res = await col.update_one({"id": "proj-1"}, {"$set": {"status": "ready"}})
    assert up_res.acknowledged is True

    updated = await col.find_one({"id": "proj-1"})
    assert updated is not None
    assert updated["status"] == "ready"

    # 4. Count documents
    count = await col.count_documents({"status": "ready"})
    assert count == 1

    # 5. Find with cursor & sort
    await col.insert_one({"id": "proj-2", "name": "Traffic AI", "status": "ready"})
    items = await col.find({"status": "ready"}).sort("name", 1).to_list()
    assert len(items) == 2
    assert items[0]["name"] == "Traffic AI"
    assert items[1]["name"] == "Vision AI"

    # 6. Delete one
    del_res = await col.delete_one({"id": "proj-1"})
    assert del_res.deleted_count == 1
    assert await col.find_one({"id": "proj-1"}) is None
    await col.delete_many({})


@pytest.mark.asyncio
async def test_sqlite_to_firebase_migration(tmp_path: Path):
    import sqlite3
    import json

    sqlite_file = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(str(sqlite_file))
    conn.execute("CREATE TABLE documents (collection TEXT, doc_id TEXT, payload TEXT, PRIMARY KEY (collection, doc_id))")
    conn.execute("INSERT INTO documents VALUES (?, ?, ?)", ("projects", "migrated-proj", json.dumps({"id": "migrated-proj", "name": "Migrated Traffic Vision"})))
    conn.execute("INSERT INTO documents VALUES (?, ?, ?)", ("assets", "migrated-asset", json.dumps({"id": "migrated-asset", "filename": "traffic.jpg"})))
    conn.commit()
    conn.close()

    # Clean up any existing documents from previous test runs
    fb_db = FirebaseDatabase()
    await fb_db.projects.delete_one({"id": "migrated-proj"})
    await fb_db.assets.delete_one({"id": "migrated-asset"})

    # Migrate to Firebase Database
    summary = await migrate_sqlite_to_firebase(sqlite_file, fb_db)

    assert "projects" in summary
    assert "assets" in summary
    assert summary["projects"] == 1
    assert summary["assets"] == 1

    # Verify documents in Firebase Database
    proj = await fb_db.projects.find_one({"id": "migrated-proj"})
    assert proj is not None
    assert proj["name"] == "Migrated Traffic Vision"

    asset = await fb_db.assets.find_one({"id": "migrated-asset"})
    assert asset is not None
    assert asset["filename"] == "traffic.jpg"

    # Cleanup after test
    await fb_db.projects.delete_one({"id": "migrated-proj"})
    await fb_db.assets.delete_one({"id": "migrated-asset"})
    await fb_db.close()
