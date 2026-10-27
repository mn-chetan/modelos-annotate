"""Dataset MCP tools — read-only project/asset/ontology context for the orchestrator."""

from __future__ import annotations

from typing import Any

from app.db.models import AssetRow, MongoSession, ProjectRow
from app.errors import NotFoundError
from app.mcp.instrumentation import mcp_tool


@mcp_tool("dataset_asset_metadata")
async def get_asset_metadata(session: MongoSession, asset_id: str) -> dict[str, Any]:
    asset = await session.get(AssetRow, asset_id)
    if asset is None:
        raise NotFoundError(f"Asset {asset_id} not found", details={"asset_id": asset_id})
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "filename": asset.filename,
        "content_type": asset.content_type,
        "width": asset.width,
        "height": asset.height,
        "content_hash": asset.content_hash,
        "perceptual_hash": asset.perceptual_hash,
        "aspect_ratio": asset.aspect_ratio,
        "cluster_id": asset.cluster_id,
        "is_outlier": asset.is_outlier,
        "is_duplicate": asset.is_duplicate,
        "review_priority": asset.review_priority,
        "review_status": asset.review_status,
        "fps": asset.fps,
    }


@mcp_tool("dataset_asset_annotations")
async def get_asset_annotation_summary(session: MongoSession, asset_id: str) -> dict[str, Any]:
    from app.services.annotations import AnnotationService

    rows = await AnnotationService(session).list_for_asset(asset_id)
    return {
        "asset_id": asset_id,
        "count": len(rows),
        "labels": sorted({r["label"] for r in rows if r.get("label")}),
    }


@mcp_tool("dataset_project_ontology")
async def get_project_ontology(session: MongoSession, project_id: str) -> dict[str, Any]:
    project = await session.get(ProjectRow, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found", details={"project_id": project_id})
    return {
        "project_id": project.id,
        "labels": list(project.labels or []),
        "label_ontology": list(project.label_ontology or []),
        "ontology_revision": project.ontology_revision,
        "label_strategy": project.label_strategy,
        "quality_policy": dict(project.quality_policy or {}),
    }
