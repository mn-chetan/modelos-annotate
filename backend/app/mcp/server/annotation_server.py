"""Annotation MCP server: groups annotation/mask CRUD + review capabilities.

In-process only — bound to the caller's existing MongoDB
``MongoSession``/``FileStorage`` so no new persistence path is introduced.
"""

from __future__ import annotations

from typing import Any

from app.db.models import MongoSession
from app.api.schemas import AnnotationCreate, AnnotationUpdate
from app.inference.contracts import NormalizedMask
from app.mcp.contracts import MCPResult
from app.mcp.tools import annotation
from app.storage.files import FileStorage


class AnnotationMCPServer:
    def __init__(self, session: MongoSession, storage: FileStorage) -> None:
        self.session = session
        self.storage = storage

    async def create_annotation(self, asset_id: str, payload: AnnotationCreate) -> MCPResult[dict[str, Any]]:
        return await annotation.create_annotation(self.session, asset_id, payload)

    async def update_annotation(
        self, annotation_id: str, payload: AnnotationUpdate
    ) -> MCPResult[dict[str, Any]]:
        return await annotation.update_annotation(self.session, annotation_id, payload)

    async def delete_annotation(
        self, annotation_id: str, *, version: int | None = None
    ) -> MCPResult[dict[str, Any]]:
        return await annotation.delete_annotation(self.session, annotation_id, version=version)

    async def verify_annotation(self, asset_id: str, status: str, reason: str = "") -> MCPResult[dict[str, Any]]:
        return await annotation.verify_annotation(self.session, asset_id, status, reason)

    async def save_annotations(
        self, asset_id: str, detections: list[Any], *, ontology_index: Any | None = None
    ) -> MCPResult[dict[str, Any]]:
        return await annotation.save_annotations(
            self.session, asset_id, detections, ontology_index=ontology_index
        )

    async def save_masks(self, asset_id: str, masks: list[NormalizedMask]) -> MCPResult[dict[str, Any]]:
        return await annotation.save_masks(self.session, self.storage, asset_id, masks)

    async def get_annotations(
        self, asset_id: str, frame_index: int | None = None
    ) -> MCPResult[list[dict[str, Any]]]:
        return await annotation.get_annotations(self.session, asset_id, frame_index)
