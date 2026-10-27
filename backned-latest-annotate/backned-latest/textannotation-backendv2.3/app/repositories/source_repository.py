from __future__ import annotations

from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorCollection

from app.schemas.source import SourceDocument


class SourceRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def create(self, source: SourceDocument) -> dict[str, Any]:
        document = source.model_dump(mode="json")
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def find_by_source_id(self, source_id: UUID) -> dict[str, Any] | None:
        return await self.collection.find_one({"source_id": str(source_id)})
