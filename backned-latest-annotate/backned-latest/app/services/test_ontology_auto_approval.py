"""Tests for ontology auto-approval and batch creation resiliency."""

import pytest
from app.db.models import _uuid, _utcnow, init_database
from app.config import get_settings
from app.storage.files import FileStorage
from app.services.projects import ProjectService, _get_ontology_status
from app.services.batches import BatchService
from app.api.schemas import BatchCreate


@pytest.mark.asyncio
async def test_ontology_auto_approval_on_batch_creation(tmp_path):
    settings = get_settings()
    db = await init_database(settings=settings)
    storage = FileStorage(tmp_path / "storage")

    proj_id = _uuid()
    now = _utcnow()
    await db.projects.insert_one({
        "id": proj_id,
        "name": "Test Project",
        "labels": ["car", "pedestrian"],
        "label_ontology": [],
        "ontology_status": "unconfigured",
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    })

    asset_id = _uuid()
    await db.assets.insert_one({
        "id": asset_id,
        "project_id": proj_id,
        "filename": "test.jpg",
        "storage_path": "test.jpg",
        "status": "ready",
        "created_at": now,
        "updated_at": now,
    })

    batch_svc = BatchService(db, settings)
    batch_svc.storage = storage

    # Explicit AI annotation trigger automatically approves the ontology from labels and creates the batch successfully
    batch = await batch_svc.create(
        proj_id,
        BatchCreate(asset_ids=[asset_id]),
        explicit_ai_annotation_trigger=True,
    )
    assert batch is not None
    assert batch["project_id"] == proj_id

    # Verify project ontology was updated to approved and persisted
    updated_proj = await db.projects.find_one({"id": proj_id})
    assert updated_proj["ontology_status"] == "approved"
    assert len(updated_proj["label_ontology"]) == 2
    assert all(c["approved"] is True for c in updated_proj["label_ontology"])
    assert all(c["status"] == "approved" for c in updated_proj["label_ontology"])

    # Clean up
    await db.projects.delete_many({"id": proj_id})
    await db.assets.delete_many({"project_id": proj_id})
    await db.batches.delete_many({"project_id": proj_id})
    await db.job_items.delete_many({"batch_id": batch["id"]})


@pytest.mark.asyncio
async def test_ontology_auto_approval_fails_safe_on_invalid_ontology(tmp_path):
    settings = get_settings()
    db = await init_database(settings=settings)
    storage = FileStorage(tmp_path / "storage")

    proj_id = _uuid()
    now = _utcnow()
    # Project with no labels and no ontology concepts
    await db.projects.insert_one({
        "id": proj_id,
        "name": "Empty Ontology Project",
        "labels": [],
        "label_ontology": [],
        "ontology_status": "unconfigured",
        "status": "draft",
        "modality": "image",
        "created_at": now,
        "updated_at": now,
    })

    asset_id = _uuid()
    await db.assets.insert_one({
        "id": asset_id,
        "project_id": proj_id,
        "filename": "test.jpg",
        "storage_path": "test.jpg",
        "status": "ready",
        "created_at": now,
        "updated_at": now,
    })

    batch_svc = BatchService(db, settings)
    batch_svc.storage = storage

    from app.errors import ValidationAppError
    with pytest.raises(ValidationAppError):
        await batch_svc.create(
            proj_id,
            BatchCreate(asset_ids=[asset_id]),
            explicit_ai_annotation_trigger=True,
        )

    # Verify no batch was created
    batches = await db.batches.find({"project_id": proj_id}).to_list(length=10)
    assert len(batches) == 0

    # Clean up
    await db.projects.delete_many({"id": proj_id})
    await db.assets.delete_many({"project_id": proj_id})


@pytest.mark.asyncio
async def test_ontology_auto_approval_when_label_equals_project_name(tmp_path):
    settings = get_settings()
    db = await init_database(settings=settings)
    storage = FileStorage(tmp_path / "storage")

    proj_id = _uuid()
    now = _utcnow()
    proj_name = "TrafficVision AI2333"
    await db.projects.insert_one({
        "id": proj_id,
        "name": proj_name,
        "labels": [proj_name],
        "label_ontology": [],
        "ontology_status": "unconfigured",
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    })

    asset_id = _uuid()
    await db.assets.insert_one({
        "id": asset_id,
        "project_id": proj_id,
        "filename": "test.jpg",
        "storage_path": "test.jpg",
        "status": "ready",
        "created_at": now,
        "updated_at": now,
    })

    batch_svc = BatchService(db, settings)
    batch_svc.storage = storage

    batch = await batch_svc.create(
        proj_id,
        BatchCreate(asset_ids=[asset_id]),
        explicit_ai_annotation_trigger=True,
    )
    assert batch is not None
    assert batch["project_id"] == proj_id

    updated_proj = await db.projects.find_one({"id": proj_id})
    assert updated_proj["ontology_status"] == "approved"
    assert len(updated_proj["label_ontology"]) == 1
    assert updated_proj["label_ontology"][0]["name"] == proj_name
    assert updated_proj["label_ontology"][0]["status"] == "approved"

    # Clean up
    await db.projects.delete_many({"id": proj_id})
    await db.assets.delete_many({"project_id": proj_id})
    await db.batches.delete_many({"project_id": proj_id})
    await db.job_items.delete_many({"batch_id": batch["id"]})

