"""Immutable Audit Trail Service for Human-in-the-Loop actions and AI provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from app.db.firebase import AsyncIOMotorDatabase
from app.db.models import MongoDoc, to_mongo_docs
from app.logging import get_logger

logger = get_logger(__name__)


async def record_audit_event(
    db: AsyncIOMotorDatabase,
    *,
    asset_id: str,
    action: str,
    actor_type: str = "human",
    actor_id: str | None = None,
    actor_role: str | None = None,
    annotation_id: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    reason: str | None = None,
    project_id: str | None = None,
    batch_id: str | None = None,
    job_id: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store an immutable audit event in the audit_events collection."""
    doc = {
        "event_id": str(uuid.uuid4()),
        "asset_id": str(asset_id),
        "annotation_id": str(annotation_id) if annotation_id else None,
        "action": str(action),
        "actor_type": str(actor_type),
        "actor_id": str(actor_id) if actor_id else None,
        "actor_role": str(actor_role) if actor_role else "Reviewer",
        "user_role": str(actor_role) if actor_role else "Reviewer",
        "user": str(actor_id) if actor_id else "reviewer_1",
        "role": str(actor_role) if actor_role else "Reviewer",
        "before_state": before_state or {},
        "after_state": after_state or {},
        "reason": str(reason or ""),
        "project_id": str(project_id) if project_id else None,
        "batch_id": str(batch_id) if batch_id else None,
        "job_id": str(job_id) if job_id else None,
        "request_id": str(request_id) if request_id else None,
        "metadata": metadata or {},
        "timestamp": datetime.now(UTC).isoformat(),
    }
    collection = getattr(db, "audit_events", None) if hasattr(db, "audit_events") else db["audit_events"]
    await collection.insert_one(doc)
    doc.pop("_id", None)
    logger.info(
        "hitl_audit_event_recorded",
        event_id=doc["event_id"],
        asset_id=asset_id,
        action=action,
        actor_type=actor_type,
        annotation_id=annotation_id,
    )
    return doc


async def get_asset_audit_trail(
    db: AsyncIOMotorDatabase,
    asset_id: str,
    *,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Retrieve immutable audit events for an asset ordered chronologically."""
    cursor = db["audit_events"].find({"asset_id": asset_id}).sort("timestamp", 1).limit(limit)
    raw_events = await cursor.to_list(length=limit)
    docs = to_mongo_docs(raw_events)
    return [dict(d) for d in docs]


async def get_project_audit_trail(
    db: AsyncIOMotorDatabase,
    project_id: str,
    *,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Retrieve immutable audit events for a project."""
    cursor = db["audit_events"].find({"project_id": project_id}).sort("timestamp", 1).limit(limit)
    raw_events = await cursor.to_list(length=limit)
    docs = to_mongo_docs(raw_events)
    return [dict(d) for d in docs]
