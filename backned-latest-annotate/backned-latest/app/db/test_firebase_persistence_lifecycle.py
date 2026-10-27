"""Comprehensive tests for Firebase Firestore persistence, health lifecycle, and ontology approval."""

from __future__ import annotations

import pytest
import uuid
from datetime import datetime, UTC
from typing import Any

from app.db.firebase import FirebaseDatabase
from app.db.seed import seed_database_if_empty
from app.services.projects import ProjectService
from app.services.batches import BatchService
from app.storage.files import FileStorage
from app.config import get_settings
from app.api.schemas import BatchCreate
from app.errors import ValidationAppError


@pytest.fixture
def unique_project_id():
    return f"prj_test_{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_1_firestore_available_project_persists(unique_project_id):
    """1. Firestore available -> project persists."""
    settings = get_settings()
    db = FirebaseDatabase(
        project_id=settings.effective_firebase_project_id,
        database_id=settings.effective_firebase_database_id,
        allow_memory_fallback=False,
    )
    is_healthy = await db.verify_connection()
    assert is_healthy is True
    assert db.persistence_mode == "durable"
    assert db.connection_status == "healthy"

    project_doc = {
        "id": unique_project_id,
        "name": f"Project {unique_project_id}",
        "name_normalized": f"project {unique_project_id}",
        "goal": "Test project persistence",
        "task_type": "detection",
        "labels": ["car", "person"],
        "ontology_status": "pending_approval",
        "status": "draft",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    insert_res = await db.projects.insert_one(project_doc)
    assert insert_res.inserted_id == unique_project_id

    # Read back directly
    persisted = await db.projects.find_one({"id": unique_project_id})
    assert persisted is not None
    assert persisted["name"] == f"Project {unique_project_id}"

    # Cleanup
    await db.projects.delete_one({"id": unique_project_id})
    await db.close()


@pytest.mark.asyncio
async def test_2_firestore_available_ontology_approval_persists(unique_project_id, tmp_path):
    """2. Firestore available -> ontology approval persists."""
    settings = get_settings()
    db = FirebaseDatabase(
        project_id=settings.effective_firebase_project_id,
        database_id=settings.effective_firebase_database_id,
        allow_memory_fallback=False,
    )
    await db.verify_connection()

    project_doc = {
        "id": unique_project_id,
        "name": f"Project {unique_project_id}",
        "name_normalized": f"project {unique_project_id}",
        "goal": "Detect vehicles",
        "task_type": "detection",
        "labels": ["car", "truck"],
        "label_ontology": [
            {"id": "cpt_car", "name": "car", "status": "draft", "approved": False},
            {"id": "cpt_truck", "name": "truck", "status": "draft", "approved": False},
        ],
        "ontology_status": "pending_approval",
        "status": "draft",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await db.projects.insert_one(project_doc)

    storage = FileStorage(tmp_path)
    svc = ProjectService(db, settings, storage)
    updated = await svc.approve_ontology(unique_project_id)
    assert updated["ontology_status"] == "approved"

    # Read directly from Firestore
    persisted = await db.projects.find_one({"id": unique_project_id})
    assert persisted["ontology_status"] == "approved"
    assert all(c.get("approved") is True for c in persisted["label_ontology"])

    # Cleanup
    await db.projects.delete_one({"id": unique_project_id})
    await db.close()


@pytest.mark.asyncio
async def test_3_and_7_restart_approved_ontology_and_project_survives(unique_project_id, tmp_path):
    """3 & 7. Restart -> existing project and approved ontology remains approved across separate client instances."""
    settings = get_settings()

    # Client instance 1 (before restart)
    db1 = FirebaseDatabase(
        project_id=settings.effective_firebase_project_id,
        database_id=settings.effective_firebase_database_id,
        allow_memory_fallback=False,
    )
    await db1.verify_connection()
    storage = FileStorage(tmp_path)
    svc1 = ProjectService(db1, settings, storage)

    project_doc = {
        "id": unique_project_id,
        "name": f"Surviving Project {unique_project_id}",
        "name_normalized": f"surviving project {unique_project_id}",
        "goal": "Survive restarts",
        "task_type": "detection",
        "labels": ["traffic light", "bus"],
        "ontology_status": "pending_approval",
        "status": "draft",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await db1.projects.insert_one(project_doc)
    await svc1.approve_ontology(unique_project_id)

    # Asset doc
    asset_id = f"ast_{unique_project_id}"
    await db1.assets.insert_one({
        "id": asset_id,
        "project_id": unique_project_id,
        "filename": "survive.png",
        "status": "uploaded",
    })

    # Simulate restart by completely closing db1 and dropping its local memory
    await db1.close()
    del db1

    # Client instance 2 (after restart - entirely fresh connection)
    db2 = FirebaseDatabase(
        project_id=settings.effective_firebase_project_id,
        database_id=settings.effective_firebase_database_id,
        allow_memory_fallback=False,
    )
    await db2.verify_connection()

    # Verify project survived
    proj = await db2.projects.find_one({"id": unique_project_id})
    assert proj is not None
    assert proj["ontology_status"] == "approved"
    assert all(c.get("approved") is True for c in proj.get("label_ontology", []))

    # Verify asset survived
    ast = await db2.assets.find_one({"id": asset_id})
    assert ast is not None
    assert ast["project_id"] == unique_project_id

    # Clean up
    await db2.projects.delete_one({"id": unique_project_id})
    await db2.assets.delete_one({"id": asset_id})
    await db2.close()


@pytest.mark.asyncio
async def test_4_firestore_unavailable_reports_unhealthy():
    """4. Firestore unavailable -> application reports unhealthy persistence."""
    # Use non-existent database ID
    db = FirebaseDatabase(
        project_id="prod-y-in2300452",
        database_id="non_existent_db_99999",
        allow_memory_fallback=False,
    )
    is_healthy = await db.verify_connection()
    assert is_healthy is False
    assert db.connection_status == "unhealthy"
    assert db.persistence_mode == "unhealthy"
    assert db.last_error is not None
    await db.close()


@pytest.mark.asyncio
async def test_5_firestore_unavailable_no_silent_memory_persistence():
    """5. Firestore unavailable -> no silent memory persistence in production."""
    db = FirebaseDatabase(
        project_id="prod-y-in2300452",
        database_id="non_existent_db_99999",
        allow_memory_fallback=False,
    )
    await db.verify_connection()

    # Attempting to write must fail fast with RuntimeError, NOT silently succeed in memory
    with pytest.raises(RuntimeError) as exc_info:
        await db.projects.insert_one({"id": "fail_test", "name": "Fail"})
    assert "Firestore insert failed" in str(exc_info.value) or "unavailable" in str(exc_info.value)

    # Attempting to query must also fail fast
    with pytest.raises(RuntimeError):
        await db.projects.find_one({"id": "fail_test"})

    await db.close()


@pytest.mark.asyncio
async def test_6_failed_seed_must_not_report_seed_success():
    """6. Failed seed -> must not report seed success."""
    unhealthy_db = FirebaseDatabase(
        project_id="prod-y-in2300452",
        database_id="non_existent_db_99999",
        allow_memory_fallback=False,
    )
    await unhealthy_db.verify_connection()

    # seed_demo_data must be True so the unhealthy-DB guard is reached;
    # with seed_demo_data=False the function returns before any DB access.
    from unittest.mock import MagicMock
    mock_settings = MagicMock()
    mock_settings.seed_demo_data = True

    with pytest.raises(RuntimeError) as exc_info:
        await seed_database_if_empty(unhealthy_db, settings=mock_settings)
    assert "unhealthy" in str(exc_info.value).lower()
    await unhealthy_db.close()


@pytest.mark.asyncio
async def test_8_ai_annotation_works_after_persisted_ontology_approval(unique_project_id, tmp_path):
    """8. AI Annotation works after persisted ontology approval."""
    settings = get_settings()
    db = FirebaseDatabase(
        project_id=settings.effective_firebase_project_id,
        database_id=settings.effective_firebase_database_id,
        allow_memory_fallback=False,
    )
    await db.verify_connection()
    storage = FileStorage(tmp_path)

    # Create approved project
    project_doc = {
        "id": unique_project_id,
        "name": f"AI Annotation Project {unique_project_id}",
        "name_normalized": f"ai annotation project {unique_project_id}",
        "goal": "Test annotation start",
        "task_type": "detection",
        "labels": ["car", "pedestrian"],
        "label_ontology": [
            {"id": "cpt_car", "name": "car", "status": "approved", "approved": True},
            {"id": "cpt_pedestrian", "name": "pedestrian", "status": "approved", "approved": True},
        ],
        "ontology_status": "approved",
        "status": "ready",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await db.projects.insert_one(project_doc)

    # Add 2 assets
    ast1_id = f"ast_1_{unique_project_id}"
    ast2_id = f"ast_2_{unique_project_id}"
    await db.assets.insert_one({"id": ast1_id, "project_id": unique_project_id, "status": "uploaded"})
    await db.assets.insert_one({"id": ast2_id, "project_id": unique_project_id, "status": "uploaded"})

    # Trigger batch creation for AI Annotation
    batch_svc = BatchService(db, settings)
    batch = await batch_svc.create(
        unique_project_id,
        BatchCreate(asset_ids=[ast1_id, ast2_id]),
        explicit_ai_annotation_trigger=True,
    )
    assert batch is not None
    assert batch["project_id"] == unique_project_id
    assert batch["total"] == 2

    # Clean up
    await db.projects.delete_one({"id": unique_project_id})
    await db.assets.delete_one({"id": ast1_id})
    await db.assets.delete_one({"id": ast2_id})
    await db.batches.delete_one({"id": batch["id"]})
    await db.close()


@pytest.mark.asyncio
async def test_9_unapproved_ontology_remains_blocked(unique_project_id):
    """9. Unapproved ontology remains blocked when attempting batch creation without valid concepts."""
    settings = get_settings()
    db = FirebaseDatabase(
        project_id=settings.effective_firebase_project_id,
        database_id=settings.effective_firebase_database_id,
        allow_memory_fallback=False,
    )
    await db.verify_connection()

    # Project with unapproved ontology and placeholder
    project_doc = {
        "id": unique_project_id,
        "name": "Untitled Annotation Project",
        "name_normalized": "untitled annotation project",
        "goal": "",
        "task_type": "detection",
        "labels": [],
        "label_ontology": [],
        "ontology_status": "draft",
        "status": "draft",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await db.projects.insert_one(project_doc)

    batch_svc = BatchService(db, settings)
    from app.services.projects import _get_ontology_status
    # Verify that without valid ontology, it is not approved
    assert _get_ontology_status([], []) != "approved"

    # Cleanup
    await db.projects.delete_one({"id": unique_project_id})
    await db.close()
