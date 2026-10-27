"""Annotation MCP tools — thin async wrappers around the existing services.

No annotation schema, persistence, or business rule is duplicated; every
tool delegates directly to :class:`app.services.annotations.AnnotationService`
or :class:`app.services.masks.MaskService`.
"""

from __future__ import annotations

from typing import Any

from app.db.models import MongoSession

from app.api.schemas import AnnotationCreate, AnnotationUpdate
from app.inference.contracts import NormalizedMask
from app.mcp.instrumentation import mcp_tool
from app.services.annotations import AnnotationService
from app.services.masks import MaskService
from app.storage.files import FileStorage


@mcp_tool("annotation_create")
async def create_annotation(
    session: MongoSession, asset_id: str, payload: AnnotationCreate
) -> dict[str, Any]:
    return await AnnotationService(session).create(asset_id, payload)


@mcp_tool("annotation_update")
async def update_annotation(
    session: MongoSession, annotation_id: str, payload: AnnotationUpdate
) -> dict[str, Any]:
    return await AnnotationService(session).update(annotation_id, payload)


@mcp_tool("annotation_delete")
async def delete_annotation(
    session: MongoSession, annotation_id: str, *, version: int | None = None
) -> dict[str, Any]:
    await AnnotationService(session).delete(annotation_id, version=version)
    return {"annotation_id": annotation_id, "deleted": True}


@mcp_tool("annotation_verify")
async def verify_annotation(
    session: MongoSession, asset_id: str, status: str, reason: str = ""
) -> dict[str, Any]:
    """Set the asset-level review disposition (approved / flagged / review)."""
    return await AnnotationService(session).set_review(asset_id, status, reason)


@mcp_tool("annotation_save")
async def save_annotations(
    session: MongoSession,
    asset_id: str,
    detections: list[Any],
    *,
    ontology_index: Any | None = None,
) -> dict[str, Any]:
    """Persist a batch of AI detections, replacing prior AI-origin annotations."""
    anns, _ = await AnnotationService(session).replace_ai_detections(
        asset_id, detections, model_id="mcp_tool"
    )
    count = len(anns)
    return {"asset_id": asset_id, "annotations_saved": count}


@mcp_tool("annotation_save_masks")
async def save_masks(
    session: MongoSession,
    storage: FileStorage,
    asset_id: str,
    masks: list[NormalizedMask],
) -> dict[str, Any]:
    """Persist a batch of masks, replacing prior AI-origin masks for the asset."""
    count = await MaskService(session, storage).replace_ai_masks(asset_id, masks)
    return {"asset_id": asset_id, "masks_saved": count}


@mcp_tool("annotation_get")
async def get_annotations(
    session: MongoSession, asset_id: str, frame_index: int | None = None
) -> list[dict[str, Any]]:
    return await AnnotationService(session).list_for_asset(asset_id, frame_index)
