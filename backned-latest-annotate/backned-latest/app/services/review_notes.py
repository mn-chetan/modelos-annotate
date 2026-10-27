"""Asset review notes and lightweight issues."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.api.schemas import ReviewNoteCreate, ReviewNoteUpdate
from app.db.models import MongoDoc
from app.errors import NotFoundError, ValidationAppError


def _note_out(row: MongoDoc) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "asset_id": row.get("asset_id"),
        "annotation_id": row.get("annotation_id"),
        "kind": row.get("kind"),
        "status": row.get("status"),
        "body": row.get("body"),
        "author": row.get("author"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "resolved_at": row.get("resolved_at"),
    }


class ReviewNoteService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def list_for_asset(self, asset_id: str) -> list[dict[str, Any]]:
        await self._require_asset(asset_id)
        cursor = self.db["review_notes"].find({"asset_id": asset_id}).sort("created_at", 1)
        docs = [MongoDoc(d) async for d in cursor]
        return [_note_out(r) for r in docs]

    async def create(self, asset_id: str, payload: ReviewNoteCreate) -> dict[str, Any]:
        await self._require_asset(asset_id)
        body = payload.body.strip()
        if not body:
            raise ValidationAppError("Note body is required")
        if payload.annotation_id:
            ann = await self.db["annotations"].find_one({"id": payload.annotation_id})
            if ann is None or ann.get("asset_id") != asset_id:
                raise ValidationAppError(
                    "annotation_id must belong to this asset",
                    details={"annotation_id": payload.annotation_id},
                )
        now = datetime.now(UTC)
        row = MongoDoc({
            "id": str(uuid.uuid4()),
            "asset_id": asset_id,
            "annotation_id": payload.annotation_id,
            "kind": payload.kind,
            "status": "open",
            "body": body,
            "author": (payload.author or "local").strip() or "local",
            "created_at": now,
            "updated_at": now,
            "resolved_at": None,
        })
        await self.db["review_notes"].insert_one(dict(row))
        return _note_out(row)

    async def update(self, note_id: str, payload: ReviewNoteUpdate) -> dict[str, Any]:
        row_doc = await self.db["review_notes"].find_one({"id": note_id})
        if row_doc is None:
            raise NotFoundError("Review note not found", details={"note_id": note_id})
        row = MongoDoc(row_doc)
        data = payload.model_dump(exclude_unset=True)
        updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if "body" in data and data["body"] is not None:
            body = data["body"].strip()
            if not body:
                raise ValidationAppError("Note body is required")
            updates["body"] = body
        if "status" in data and data["status"] is not None:
            updates["status"] = data["status"]
            updates["resolved_at"] = datetime.now(UTC) if data["status"] == "resolved" else None

        await self.db["review_notes"].update_one({"id": note_id}, {"$set": updates})
        row.update(updates)
        return _note_out(row)

    async def _require_asset(self, asset_id: str) -> MongoDoc:
        row = await self.db["assets"].find_one({"id": asset_id})
        if row is None:
            raise NotFoundError("Asset not found", details={"asset_id": asset_id})
        return MongoDoc(row)

