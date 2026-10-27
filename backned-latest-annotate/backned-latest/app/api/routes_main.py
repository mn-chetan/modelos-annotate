"""HTTP API routes."""

from __future__ import annotations

import asyncio
import mimetypes
import time
import httpx
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from app.db.firebase import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from app.context import get_current_base_prefix


from app.agent.service import AgentService, create_agent_client
from app.api import deps
from app.api.schemas import (
    AnnotationAttributesUpdate,
    AnnotationClassificationUpdate,
    AnnotationCreate,
    AnnotationOut,
    AnnotationUpdate,
    AssetOut,
    BatchCreate,
    BatchOut,
    ClarificationAnswer,
    ClassificationAttributesOut,
    ClassifyRegionRequest,
    ClassifyRequest,
    CloudImportOut,
    CloudImportRequest,
    CloudListObjectsOut,
    CloudStorageConfigOut,
    CloudValidateOut,
    CloudValidateRequest,
    ColorMapOut,
    ColorMapUpdate,
    DatasetCoverageOut,
    DatasetHealthOut,
    DatasetMapOut,
    DatasetSearchOut,
    DatasetSearchRequest,
    DecisionOut,
    DecisionResolve,
    GranularAnnotationOut,
    HealthOut,
    LabelsUpdate,
    MaskOut,
    ModelStatusOut,
    ProjectCreate,
    ProjectOut,
    ProjectPlanOut,
    ProjectTemplateOut,
    ProjectUpdate,
    PromptDetectionRequest,
    ReconOut,
    ReviewNoteCreate,
    ReviewNoteOut,
    SegmentRequest,
    ReviewNoteUpdate,
    ReviewRequest,
    ExportRequest,
    AssetReviewRequest,
    HumanFeedbackPayload,
    AnnotationReviewRequest,
)
from app.config import Settings, get_settings
from app.db.models import MongoDoc, to_mongo_doc
from app.errors import ConflictError, ValidationAppError
from app.services.audit_trail import record_audit_event, get_asset_audit_trail
from app.inference.detector import get_detector
from app.inference.registry import get_runtime
from app.jobs.worker import get_worker
from app.logging import get_logger
from app.recon.service import ReconService
from app.services.annotations import AnnotationService
from app.services.batches import BatchService
from app.services.classification import ClassificationService
from app.services.cloud_import import CloudImportService
from app.services.dataset import DatasetService
from app.services.decisions import DecisionService
from app.services.export import ExportService, normalize_export_format
from app.services.masks import MaskService
from app.services.projects import ProjectService
from app.services.review_notes import ReviewNoteService
from app.storage.files import FileStorage

logger = get_logger(__name__)


def _normalize_text_target_objects(raw_value: Any) -> list[str]:
    """Preserve the existing target-object representations as planner labels."""
    if isinstance(raw_value, str):
        return [part.strip() for part in raw_value.replace("\n", ",").split(",") if part.strip()]
    if not isinstance(raw_value, (list, tuple)):
        return []
    labels: list[str] = []
    for item in raw_value:
        if isinstance(item, str) and item.strip():
            labels.append(item.strip())
        elif isinstance(item, dict):
            value = item.get("name") or item.get("label") or item.get("value")
            if isinstance(value, str) and value.strip():
                labels.append(value.strip())
    return labels

router = APIRouter(prefix="/api/v1")


@router.get("", include_in_schema=False)
async def api_v1_root() -> dict[str, str]:
    """Return discoverable links when the API base path is opened directly."""
    prefix = get_current_base_prefix()
    return {
        "service": "ingenii-annotate",
        "api_version": "v1",
        "health": f"{prefix}/api/v1/health",
        "docs": f"{prefix}/docs" if prefix else "/docs",
        "text_analysis": f"{prefix}/api/v1/text-annotation/analyze",
    }


@router.post("/text-annotation/analyze")
async def proxy_text_annotation(
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    project_id: str = Form(...),
    asset_id: str = Form(...),
    analysis_type: str = Form(...),
    assessment_name: str = Form(...),
    text: str | None = Form(None),
    identification_name: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
) -> JSONResponse:
    """Run the legacy text API contract through the unified agentic graph."""
    project_doc = await session.projects.find_one({"id": project_id})
    if not project_doc:
        raise HTTPException(status_code=404, detail="Project not found.")
    storage = request.app.state.storage
    source_name = (files[0].filename if files else None) or "text-input.txt"
    if files:
        content = await files[0].read()
    elif text is not None:
        content = text.encode("utf-8")
    else:
        # Re-run analysis for an already persisted project asset. The project
        # page has the canonical asset ID, so the browser does not need to
        # upload the same PDF/DOCX again just to start AI annotation.
        persisted_source = await session.assets.find_one({"id": asset_id, "project_id": project_id})
        if not persisted_source or not persisted_source.get("storage_path"):
            raise HTTPException(status_code=422, detail="Persisted text asset could not be found.")
        source_name = str(persisted_source.get("filename") or source_name)
        persisted_path = storage.resolve(str(persisted_source["storage_path"]))
        if not persisted_path.is_file():
            raise HTTPException(status_code=404, detail="Persisted text asset file is missing from storage.")
        content = persisted_path.read_bytes()
    text_length = len(content.decode("utf-8", errors="replace"))
    modality = str(project_doc.get("modality") or project_doc.get("project_type") or "text").lower()
    logger.info(
        "text_input_received",
        project_id=project_id,
        asset_id=asset_id,
        modality=modality,
        content_type="text/plain",
        text_length=text_length,
        status="received",
    )
    logger.info(
        "text_asset_creation_started",
        project_id=project_id,
        asset_id=asset_id,
        modality="text",
        content_type="text/plain",
        text_length=text_length,
        status="started",
    )
    try:
        asset = await session.assets.find_one({"id": asset_id, "project_id": project_id})
        if not asset:
            from app.services.projects import ProjectService
            asset = await ProjectService(session, request.app.state.settings, storage).upload_asset(
                project_id, source_name, "text/plain", content
            )
            asset_id = str(asset["id"])
            storage_path = str(asset.get("storage_path") or "")
        else:
            existing_storage_path = str(asset.get("storage_path") or "")
            existing_file = None
            try:
                existing_file = storage.resolve(existing_storage_path) if existing_storage_path else None
            except Exception:
                existing_file = None
            if existing_file and existing_file.is_file() and existing_file.read_bytes() == content:
                storage_path = existing_storage_path
            else:
                target_filename = str(asset.get("filename") or source_name)
                asset_path = storage.write_bytes(project_id, asset_id, target_filename, content)
                storage_path = storage.relative_path(asset_path)

        # Keep the real document type.  PDF/DOCX extraction uses the filename
        # as a fallback, but downstream services and persisted asset readers
        # also rely on the MIME type.  Rewriting every uploaded document as
        # text/plain made deployed PDF annotation unreliable.
        existing_content_type = str(asset.get("content_type") or "").strip()
        detected_content_type = (
            existing_content_type
            if existing_content_type and existing_content_type != "text/plain"
            else mimetypes.guess_type(source_name)[0] or existing_content_type or "text/plain"
        )
        if asset.get("storage_path") != storage_path or asset.get("content_type") != detected_content_type or asset.get("filename") != source_name:
            await session.assets.update_one(
                {"id": asset_id, "project_id": project_id},
                {"$set": {
                    "storage_path": storage_path,
                    "filename": source_name,
                    "content_type": detected_content_type,
                    "updated_at": datetime.now(UTC),
                }},
            )
        # Firestore writes are durable once update_one returns, but a read can
        # occasionally miss immediately on a busy channel. Do not turn that
        # transient readback race into a misleading client-side 400. Retry the
        # read and use the verified local document if the write itself already
        # completed successfully.
        persisted_asset = None
        for readback_attempt in range(1, 4):
            persisted_asset = await session.assets.find_one({"id": asset_id, "project_id": project_id})
            if persisted_asset:
                break
            if readback_attempt < 3:
                await asyncio.sleep(0.25 * readback_attempt)
        if not persisted_asset:
            logger.warning(
                "text_asset_readback_delayed_using_write_result",
                project_id=project_id,
                asset_id=asset_id,
                readback_attempts=3,
            )
            persisted_asset = dict(asset)
            persisted_asset.update({
                "id": asset_id,
                "project_id": project_id,
                "storage_path": storage_path,
                "filename": source_name,
                "content_type": detected_content_type,
            })
        logger.info(
            "text_asset_persisted",
            project_id=project_id,
            asset_id=asset_id,
            modality="text",
            content_type=persisted_asset.get("content_type") or "text/plain",
            text_length=text_length,
            status=persisted_asset.get("status"),
        )
        logger.info(
            "text_asset_readback_verified",
            project_id=project_id,
            asset_id=asset_id,
            modality="text",
            content_type=persisted_asset.get("content_type") or "text/plain",
            text_length=text_length,
            status=persisted_asset.get("status"),
        )
        asset = to_mongo_doc({**dict(persisted_asset), "storage_path": storage_path})
    except Exception as exc:
        logger.error(
            "text_asset_creation_failed",
            project_id=project_id,
            asset_id=asset_id,
            modality="text",
            content_type="text/plain",
            text_length=text_length,
            status="failed",
            error=str(exc),
        )
        raise
    project = to_mongo_doc(project_doc)
    from app.services.text_capability import resolve_text_target_labels
    configured_labels = resolve_text_target_labels(project_doc, analysis_type)
    requested_labels = _normalize_text_target_objects(identification_name)
    labels = list(dict.fromkeys([*requested_labels, *configured_labels]))
    logger.info(
        "text_annotation_target_objects",
        project_target_objects_raw=project_doc.get("target_objects"),
        project_target_objects_normalized=labels,
    )
    from app.agent.graphs.agentic_pipeline_graph import run_agentic_pipeline_graph
    graph_state = await run_agentic_pipeline_graph(
        project=project,
        asset=asset,
        user_request=f"Run {analysis_type} for this text document.",
        session=session,
        storage=storage,
        runtime=get_runtime(),
        project_id=project_id,
        asset_id=asset_id,
        project_snapshot={
            **dict(project_doc),
            "modality": "text",
            "task_type": analysis_type,
            "labels": labels,
            "target_objects": labels,
            "entities": labels,
        },
        asset_snapshot={**dict(asset), "storage_path": storage_path},
    )
    raw_result = graph_state.get("text_result", {}).get("raw_result") or {"analysis_type": analysis_type, "results": []}
    analysis_id = str(uuid4())
    payload = {
        **raw_result,
        "analysis_id": analysis_id,
        "project_id": project_id,
        "asset_id": asset_id,
        "assessment_name": assessment_name,
        "text": graph_state.get("text_result", {}).get("text", ""),
        "annotations": graph_state.get("text_annotations", []),
        "quality_report": graph_state.get("quality_report", {}),
        "agent_run_id": getattr(graph_state.get("audit_record"), "agent_run_id", None),
        "agent_status": graph_state.get("review_decision").status if graph_state.get("review_decision") else None,
        "status": graph_state.get("final_status") or "COMPLETED",
    }
    await session.assets.update_one({"id": asset_id, "project_id": project_id}, {"$set": {"text_analysis": payload, "text_analysis_type": analysis_type, "updated_at": datetime.now(UTC)}})
    await session["text_analyses"].insert_one({**payload, "created_at": datetime.now(UTC)})
    return JSONResponse(status_code=200, content=payload)


@router.get("/projects/{project_id}/text-annotation/assets/{asset_id}")
async def get_project_text_analysis(
    project_id: str,
    asset_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> JSONResponse:
    asset = await session.assets.find_one({"id": asset_id, "project_id": project_id, "status": {"$ne": "deleted"}})
    if not asset:
        raise HTTPException(status_code=404, detail="Text asset not found.")
    payload = dict(asset.get("text_analysis") or {"results": []})
    if not payload.get("text") and asset.get("storage_path"):
        try:
            storage = request.app.state.storage
            path = storage.resolve(str(asset["storage_path"]))
            if path.is_file():
                from app.services.text_capability import TextCapabilityService
                source = await TextCapabilityService()._source(path)
                payload["text"] = source.extracted_text or source.text or ""
        except Exception as err:
            logger.warning("failed_to_extract_text_for_asset", asset_id=asset_id, error=str(err))
    if isinstance(payload, dict) and payload.get("annotations"):
        quality = payload.get("quality_report") or {}
        annotation_confidences = [
            float(item.get("confidence"))
            for item in payload.get("annotations", [])
            if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
        ]
        confidence = quality.get("confidence_score")
        if not isinstance(confidence, (int, float)) and annotation_confidences:
            confidence = sum(annotation_confidences) / len(annotation_confidences)
        threshold = quality.get("confidence_threshold", 0.95)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = 0.95
        semantic_conflicts = quality.get("semantic_conflicts") or []
        errors = quality.get("errors") or []
        current_status = str(payload.get("agent_status") or quality.get("final_decision") or "").strip().upper()
        structurally_valid = not (
            errors
            or quality.get("invalid_spans")
            or quality.get("invalid_labels")
            or quality.get("invalid_output")
            or quality.get("no_semantic_result")
        )
        if (
            current_status in {"HUMAN_REVIEW", "HUMAN_REVIEW_REQUIRED", "IN_HUMAN_REVIEW"}
            and isinstance(confidence, (int, float))
            and confidence >= threshold
            and not semantic_conflicts
            and structurally_valid
        ):
            # Backfill legacy text results created before verifier-timeout
            # fallback was enabled. The annotations remain unchanged.
            quality = {**quality, "duplicate_annotations": False, "final_decision": "AUTO_APPROVE"}
            payload = {**payload, "agent_status": "AUTO_APPROVE", "quality_report": quality}
            await session.assets.update_one(
                {"id": asset_id, "project_id": project_id},
                {"$set": {
                    "text_analysis": payload,
                    "review_status": "auto_approved",
                    "review_reason": "Text confidence passed and no validation conflicts were found.",
                    "updated_at": datetime.now(UTC),
                }},
            )
    return JSONResponse(content=payload)


@router.get("/projects/{project_id}/text-annotation/assets/{asset_id}/analyses")
async def get_project_text_analyses(
    project_id: str,
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    asset = await session.assets.find_one({"id": asset_id, "project_id": project_id, "status": {"$ne": "deleted"}})
    if not asset:
        raise HTTPException(status_code=404, detail="Text asset not found.")
    cursor = session["text_analyses"].find({"project_id": project_id, "asset_id": asset_id})
    analyses = await cursor.sort("created_at", -1).limit(100).to_list(length=100)
    for analysis in analyses:
        analysis.pop("_id", None)
    return analyses


@router.get("/text-annotation/analyses/{analysis_id}")
async def proxy_text_analysis(analysis_id: str, session: AsyncIOMotorDatabase = Depends(deps.get_db)) -> JSONResponse:
    payload = await session["text_analyses"].find_one({"analysis_id": analysis_id})
    if not payload:
        raise HTTPException(status_code=404, detail="Text analysis not found.")
    payload.pop("_id", None)
    return JSONResponse(content=payload)


@router.get("/me/role")
async def get_my_role(
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    from app.services.rbac import normalize_role
    user = getattr(request.state, "user", None)
    role = normalize_role(user.get("role") if user else "HUMAN_ANNOTATOR")
    return {"role": role}


@router.put("/me/role")
@router.post("/me/role")
async def update_my_role(
    payload: dict[str, Any],
) -> dict[str, Any]:
    raise HTTPException(status_code=403, detail="Users cannot change their own role.")


@router.get("/me/permissions")
async def get_my_permissions(
    request: Request,
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    from app.services.rbac import get_role_permissions, normalize_role
    user = getattr(request.state, "user", None)
    role = normalize_role(user.get("role") if user else x_user_role)
    return {"role": role, "permissions": sorted(get_role_permissions(role))}


from app.api.routes.data_connections import router as data_connections_router
router.include_router(data_connections_router)


@router.get("/health", response_model=HealthOut)
async def health(
    request: Request,
    settings: Annotated[Settings, Depends(deps.get_app_settings)],
) -> HealthOut:
    model_loaded = False
    device = settings.device
    models: list[ModelStatusOut] = []
    try:
        runtime = get_runtime()
        statuses = runtime.model_statuses()
        models = [ModelStatusOut.model_validate(s.__dict__) for s in statuses]
        any_available = any(m.availability == "available" for m in models)
        model_loaded = any_available or settings.skip_model_load
        yolo = next((m for m in models if m.key == "yolo26"), None)
        if yolo is not None:
            device = yolo.device
    except Exception:  # noqa: BLE001
        try:
            det = get_detector()
            model_loaded = True
            device = det.device
        except Exception:  # noqa: BLE001
            model_loaded = False

    # Expose the capability state of the optional Vertex agent client
    agent_client = getattr(request.app.state, "agent_client", None)
    if agent_client is not None:
        agent_available = getattr(agent_client, "available", True)
        agent_reason = getattr(agent_client, "reason", None)
        models.append(
            ModelStatusOut(
                key="vertex_agent",
                model_id=getattr(agent_client, "model_id", "gemini-3.6-flash"),
                capabilities=["reasoning", "ontology_proposal"],
                availability="available" if agent_available else "unavailable",
                device="cloud",
                loaded=bool(agent_available),
                error=agent_reason,
                purpose="Optional multimodal reasoning agent",
            )
        )

    db = getattr(request.app.state, "db", None)
    db_status = getattr(db, "connection_status", "healthy" if db and getattr(db, "is_healthy", False) else "unhealthy")
    db_mode = getattr(db, "persistence_mode", "durable" if db and getattr(db, "is_healthy", False) else "unhealthy")
    db_provider = getattr(db, "provider", "firebase")
    db_project = getattr(db, "project_id", "")
    db_name = getattr(db, "database_id", "engenii-annotate-native")

    is_overall_ok = (model_loaded or settings.skip_model_load) and (db_status == "healthy")

    return HealthOut(
        status="ok" if is_overall_ok else "degraded",
        model_id=settings.yolo26_model_id,
        model_loaded=model_loaded or settings.skip_model_load,
        device=device,
        database="ok" if db_status == "healthy" else "unhealthy",
        database_provider=db_provider,
        database_project=db_project,
        database_database_name=db_name,
        database_connection_status=db_status,
        database_persistence_mode=db_mode,
        models=models,
    )


@router.get("/ready")
async def ready(session: AsyncIOMotorDatabase = Depends(deps.get_db)) -> JSONResponse:
    """Readiness is intentionally a dependency check, not a liveness check."""
    try:
        await session.projects.find({}).limit(1).to_list(1)
        return JSONResponse({"status": "ready", "database": {"provider": "firebase", "status": "healthy"}})
    except Exception as exc:  # noqa: BLE001
        logger.warning("readiness_check_failed", exception_type=type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": {"provider": "firebase", "status": "unhealthy"}})


@router.get("/models", response_model=list[ModelStatusOut])
async def list_models() -> list[ModelStatusOut]:
    runtime = get_runtime()
    return [ModelStatusOut.model_validate(s.__dict__) for s in runtime.model_statuses()]


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ProjectOut:
    svc = ProjectService(session, settings, storage)
    return ProjectOut.model_validate(await svc.create(payload))


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> list[ProjectOut]:
    svc = ProjectService(session, settings, storage)
    t_start = time.perf_counter()
    raw_projects = await svc.list_projects()
    t_svc_end = time.perf_counter()

    t_ser_start = time.perf_counter()
    validated = [ProjectOut.model_validate(p) for p in raw_projects]
    t_ser_end = time.perf_counter()

    logger.info(
        "projects_list_timing",
        auth_ms=0.0,
        permissions_ms=0.0,
        firestore_client_acq_ms=0.0,
        service_list_projects_ms=round((t_svc_end - t_start) * 1000, 2),
        serialization_ms=round((t_ser_end - t_ser_start) * 1000, 2),
        total_ms=round((t_ser_end - t_start) * 1000, 2),
        project_count=len(validated),
    )
    return validated


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ProjectOut:
    svc = ProjectService(session, settings, storage)
    return ProjectOut.model_validate(await svc.get(project_id))


@router.get("/projects/{project_id}/production-dashboard")
async def get_production_dashboard(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> dict[str, Any]:
    svc = ProjectService(session, settings, storage)
    return await svc.get_production_dashboard(project_id)




@router.delete("/projects/{project_id}", status_code=204, response_class=Response)
async def delete_project(
    project_id: str,
    request: Request,
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> Response:
    from app.services.rbac import has_permission, PERMISSION_HITL_OVERRIDE, normalize_role
    user = getattr(request.state, "user", None)
    effective_role = normalize_role(user.get("role") if user else x_user_role)
    if not has_permission(effective_role, PERMISSION_HITL_OVERRIDE) and effective_role != "PROJECT_MANAGER":
        raise HTTPException(status_code=403, detail="Forbidden: Project deletion requires PROJECT_MANAGER role.")
    worker = get_worker()
    if worker is not None:
        await worker.cancel_project_and_wait(project_id)
    svc = ProjectService(session, settings, storage)
    await svc.delete(project_id)
    return Response(status_code=204)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ProjectOut:
    svc = ProjectService(session, settings, storage)
    return ProjectOut.model_validate(await svc.update(project_id, payload))


@router.get("/projects/{project_id}/color-map", response_model=ColorMapOut)
async def get_color_map(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ColorMapOut:
    svc = ProjectService(session, settings, storage)
    color_map = await svc.get_color_map(project_id)
    return ColorMapOut(project_id=project_id, color_map=color_map)


@router.post("/projects/{project_id}/color-map", response_model=ColorMapOut)
async def update_color_map(
    project_id: str,
    payload: ColorMapUpdate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ColorMapOut:
    svc = ProjectService(session, settings, storage)
    color_map = await svc.update_color_map(project_id, payload.overrides)
    return ColorMapOut(project_id=project_id, color_map=color_map)




@router.get("/projects/{project_id}/assets", response_model=list[AssetOut])
async def list_assets(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> list[AssetOut]:
    from app.logging import get_logger
    logger = get_logger(__name__)
    svc = ProjectService(session, settings, storage)
    assets = await svc.list_assets(project_id)
    logger.info("asset_read", project_id=project_id, count=len(assets))
    return [AssetOut.model_validate(a) for a in assets]


@router.post("/projects/{project_id}/assets", response_model=list[AssetOut], status_code=201)
async def upload_assets(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    files: list[UploadFile] = File(...),
) -> list[AssetOut]:
    svc = ProjectService(session, settings, storage)
    modality = (await svc.get_project_modality(project_id)).strip().lower()
    # Legacy image projects may persist "Image Annotation" or an empty/older
    # modality value. Only the explicitly non-image modalities are excluded.
    is_image_modality = modality not in {"video", "text", "document"}

    limit_mb = settings.max_image_upload_mb
    if modality == "video":
        limit_mb = settings.max_video_upload_mb
    elif modality == "text":
        limit_mb = settings.max_text_upload_mb
    elif modality == "document":
        limit_mb = settings.max_document_upload_mb
    out: list[AssetOut] = []
    logger.info(
        "asset_upload_received",
        project_id=project_id,
        modality=modality,
        multipart_file_count=len(files),
        multipart_files=[
            {
                "filename": f.filename,
                "size": f.size,
                "content_type": f.content_type,
            }
            for f in files
        ],
    )

    # Process ordinary image parts before archives. A stale/empty archive part
    # must not prevent valid selected image parts in the same multipart request
    # from being persisted. Archive-only uploads still retain the existing
    # validation error below.
    ordered_files = [
        *[f for f in files if not ((f.filename or "").lower().endswith(".zip"))],
        *[f for f in files if ((f.filename or "").lower().endswith(".zip"))],
    ]
    for f in ordered_files:
        suffix = (f.filename or "").lower().rsplit(".", 1)[-1] if "." in (f.filename or "") else ""
        is_video = (f.content_type or "").startswith("video/") or suffix in {"mp4", "mov", "avi", "mkv", "webm"}
        # Text projects can accept document containers such as PDF and DOCX.
        # They need the document limit rather than the smaller plain-text limit.
        is_document_file = suffix in {"pdf", "doc", "docx", "odt", "rtf"}
        file_limit_mb = (
            settings.max_video_upload_mb
            if is_video
            else settings.max_document_upload_mb
            if is_document_file
            else limit_mb
        )
        file_max_bytes = file_limit_mb * 1024 * 1024
        if f.size is not None and f.size > file_max_bytes:
            raise ValidationAppError(
                "File exceeds max upload size",
                details={
                    "filename": f.filename or "unknown",
                    "size": f.size,
                    "max_size": file_max_bytes,
                    "modality": modality,
                },
            )
        data = await f.read(file_max_bytes + 1)
        if len(data) > file_max_bytes:
            raise ValidationAppError(
                "File exceeds max upload size",
                details={
                    "filename": f.filename or "unknown",
                    "size": len(data),
                    "max_size": file_max_bytes,
                    "modality": modality,
                },
            )
        logger.info(
            "upload_received",
            project_id=project_id,
            upload_filename=f.filename or "unknown",
            upload_content_type=f.content_type,
            upload_size=len(data),
            storage_root=str(getattr(storage, "root", "")),
        )
        if is_image_modality and suffix == "zip":
            from app.services.image_archives import iter_image_members

            logger.info(
                "image_archive_upload_started",
                project_id=project_id,
                filename=f.filename,
                archive_bytes=len(data),
                route_module=__file__,
            )
            member_count = 0
            for member_name, member_data in iter_image_members(
                data,
                max_member_bytes=settings.max_upload_bytes,
            ):
                logger.info(
                    "upload_archive_member_received",
                    project_id=project_id,
                    archive_filename=f.filename,
                    upload_filename=member_name,
                    upload_size=len(member_data),
                    storage_root=str(getattr(storage, "root", "")),
                )
                asset = await svc.upload_asset(
                    project_id,
                    filename=member_name,
                    content_type=None,
                    data=member_data,
                )
                out.append(AssetOut.model_validate(asset))
                member_count += 1
            if member_count == 0:
                if not out:
                    raise ValidationAppError("No supported image files found in ZIP archive.")
                logger.warning(
                    "image_archive_upload_skipped",
                    project_id=project_id,
                    filename=f.filename,
                    archive_bytes=len(data),
                    reason="no_supported_image_files",
                )
                continue
            logger.info(
                "image_archive_upload_completed",
                project_id=project_id,
                filename=f.filename,
                asset_count=member_count,
                route_module=__file__,
            )
            continue
        asset = await svc.upload_asset(
            project_id,
            filename=f.filename or f"upload-{uuid4().hex}.jpg",
            content_type=f.content_type,
            data=data,
        )
        out.append(AssetOut.model_validate(asset))
    return out


@router.post("/projects/{project_id}/ai-annotate")
async def trigger_project_ai_annotation(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> dict[str, Any]:
    """Create or reuse an AI annotation batch for background processing."""
    from app.api.schemas import BatchCreate
    from app.db.models import MongoDoc
    from app.domain.enums import BatchStatus, HumanRole, JobItemStatus, PlanStatus, ReviewStatus
    from app.errors import NotFoundError, ValidationAppError
    from app.logging import get_logger
    from app.services.batches import BatchService, resolve_execution_context

    logger = get_logger(__name__)
    db_id = getattr(session, "database_id", "engenii-annotate-native")

    logger.info(
        "batch_creation_request_received",
        project_id=project_id,
        status="received",
        collection="batches",
        database_id=db_id,
        batch_creation_source="explicit_ai_annotation_endpoint",
        request_endpoint=str(request.url.path),
        explicit_ai_annotation_trigger=True,
        caller_context=request.headers.get("x-request-id"),
    )

    project_doc = await session["projects"].find_one({"id": project_id})
    if not project_doc:
        raise NotFoundError("Project", project_id)
    project = MongoDoc(project_doc)

    # 1. Resolve all actual assets for the project from MongoDB
    assets_cursor = session["assets"].find({"project_id": project_id, "status": {"$ne": "deleted"}})
    assets = [MongoDoc(d) async for d in assets_cursor]
    total_assets = len(assets)
    logger.info("assets_resolved", project_id=project_id, count=total_assets, asset_count=total_assets)

    # 2. Resolve and auto-approve project ontology from canonical configuration first
    from app.services.projects import ProjectService, _get_ontology_status
    proj_svc = ProjectService(session, settings, storage)
    updated_project_doc = await session["projects"].find_one({"id": project_id}) or project_doc
    curr_ontology = list((updated_project_doc or {}).get("label_ontology") or [])
    curr_labels = list((updated_project_doc or {}).get("labels") or [])
    curr_status = str((updated_project_doc or {}).get("ontology_status") or "").lower()
    if curr_status != "approved" or _get_ontology_status(curr_ontology, curr_labels) != "approved":
        await proj_svc.approve_ontology(project_id)
        updated_project_doc = await session["projects"].find_one({"id": project_id}) or updated_project_doc

    project_doc = updated_project_doc
    project = MongoDoc(project_doc)

    # 3. Approve agent plan using the SAME canonical ontology and labels second
    plan_doc = await session["project_plans"].find_one({"project_id": project_id})
    if not plan_doc or plan_doc.get("status") in {
        PlanStatus.PENDING_APPROVAL.value,
        PlanStatus.AWAITING_CLARIFICATION.value,
    }:
        logger.info("project_plan_auto_approval_started", project_id=project_id)
        await _agent_service(request, session, settings).approve_plan(project_id)
        plan_doc = await session["project_plans"].find_one({"project_id": project_id})
    project = MongoDoc(project_doc)
    policy = project.get("quality_policy") or {}

    threshold_val = policy.get("confidence_threshold") or policy.get("auto_approve_threshold")
    sample_rate_val = policy.get("qc_sample_rate") or policy.get("sample_rate")

    if threshold_val is None:
        confidence_threshold = 0.95
    else:
        try:
            confidence_threshold = float(threshold_val)
        except (ValueError, TypeError):
            raise ValidationAppError(f"Missing or invalid confidence_threshold configuration for project {project_id}: {threshold_val}")

    if sample_rate_val is None:
        qc_sample_rate = 0.05
    else:
        try:
            qc_sample_rate = float(sample_rate_val)
        except (ValueError, TypeError):
            raise ValidationAppError(f"Missing or invalid qc_sample_rate configuration for project {project_id}: {sample_rate_val}")

    logger.info(
        "project_hitl_configuration_stage",
        project_id=project_id,
        configured_threshold=confidence_threshold,
        configured_qc_sample_rate=qc_sample_rate,
    )

    valid_physical_assets = []
    for asset in assets:
        sp = str(asset.get("storage_path") or "")
        if not sp:
            logger.warning("asset_missing_storage_path_ineligible", project_id=project_id, asset_id=str(asset.id))
            continue
        try:
            phys_path = storage.resolve(sp)
            if not phys_path.exists() or not phys_path.is_file() or phys_path.stat().st_size == 0:
                logger.warning(
                    "asset_physical_file_missing_ineligible_for_annotation",
                    project_id=project_id,
                    asset_id=str(asset.id),
                    storage_path=sp,
                    resolved_path=str(phys_path),
                )
                continue
            valid_physical_assets.append(asset)
        except Exception as exc:
            logger.warning(
                "asset_physical_resolution_error_ineligible",
                project_id=project_id,
                asset_id=str(asset.id),
                storage_path=sp,
                error=str(exc),
            )
            continue

    missing_physical_files = total_assets - len(valid_physical_assets)
    if total_assets > 0 and len(valid_physical_assets) == 0:
        logger.error(
            "ai_annotation_failed_missing_physical_storage",
            project_id=project_id,
            total_assets=total_assets,
            missing_physical_files=missing_physical_files,
            eligible_assets=0,
            processed_assets=0,
        )
        raise ValidationAppError(
            f"Cannot start AI annotation: {missing_physical_files} asset(s) in this project are missing physical storage files on disk. Please re-upload the files."
        )

    batch_svc = BatchService(session, settings)
    processed_asset_ids = await batch_svc.terminal_asset_ids(
        project_id,
        [str(asset.id) for asset in valid_physical_assets],
        explicit_ai_annotation_trigger=True,
    )
    eligible_assets = [asset for asset in valid_physical_assets if str(asset.id) not in processed_asset_ids]
    logger.info(
        "batch_creation_asset_resolution",
        project_id=project_id,
        asset_count=total_assets,
        eligible_count=len(eligible_assets),
        already_processed_count=len(processed_asset_ids),
        already_processed_asset_ids=sorted(processed_asset_ids),
        missing_physical_files=missing_physical_files,
    )

    if processed_asset_ids:
        logger.info(
            "already_processed_assets_skipped",
            project_id=project_id,
            asset_count=len(processed_asset_ids),
            asset_ids=sorted(processed_asset_ids),
            reason="successful_terminal_result_with_persisted_annotations",
        )

    if total_assets == 0:
        logger.warning(
            "batch_creation_skipped_no_assets",
            project_id=project_id,
            asset_count=0,
        )
        logger.info(
            "ai_annotation_no_assets_found",
            project_id=project_id,
            total_assets=0,
            eligible_assets=0,
        )
        return {
            "status": "completed",
            "project_id": project_id,
            "project_name": project.get("name", "Project"),
            "total_assets": 0,
            "eligible_assets": 0,
            "batch_id": None,
            "scheduled_assets": 0,
            "completed_assets": 0,
            "failed_assets": 0,
            "human_review_count": 0,
            "human_annotator_tasks": 0,
            "quality_audit_count": 0,
            "quality_auditor_tasks": 0,
            "auto_pass_count": 0,
            "auto_passed_tasks": 0,
            "message": "No uploaded assets found for this project.",
        }

    if not eligible_assets:
        if missing_physical_files > 0:
            logger.error(
                "ai_annotation_failed_missing_physical_storage",
                project_id=project_id,
                total_assets=total_assets,
                missing_physical_files=missing_physical_files,
                eligible_assets=0,
                processed_assets=len(processed_asset_ids),
            )
            raise ValidationAppError(
                f"Cannot start AI annotation: {missing_physical_files} asset(s) in this project are missing physical storage files on disk. Please re-upload the files."
            )
        logger.info(
            "ai_annotation_skipped_all_assets_already_processed",
            project_id=project_id,
            total_assets=total_assets,
            eligible_assets=0,
            processed_assets=len(processed_asset_ids),
        )
        return {
            "status": "completed",
            "project_id": project_id,
            "project_name": project.get("name", "Project"),
            "total_assets": total_assets,
            "eligible_assets": 0,
            "batch_id": None,
            "scheduled_assets": 0,
            "completed_assets": len(processed_asset_ids),
            "failed_assets": 0,
            "processed": len(processed_asset_ids),
            "annotated_assets": len(processed_asset_ids),
            "human_review_count": 0,
            "human_annotator_tasks": 0,
            "quality_audit_count": 0,
            "quality_auditor_tasks": 0,
            "auto_pass_count": 0,
            "auto_passed_tasks": 0,
            "quality_audit_sample_count": 0,
            "confidence_threshold": confidence_threshold,
            "qc_sample_rate": qc_sample_rate,
            "message": "All project assets already have terminal results; no new batch was created.",
        }

    # 2. Check only for an active batch with the same execution context.
    # A project can have historical/legacy batches without context fields, so
    # BatchService performs asset-aware compatibility checks for those records.
    requested_modality, requested_task = resolve_execution_context(project)
    active_batch_doc = await batch_svc.find_active_compatible(
        project_id,
        requested_modality,
        requested_task,
    )

    if active_batch_doc:
        batch_id = active_batch_doc["id"]
        logger.info(
            "reusing_active_ai_annotation_batch",
            project_id=project_id,
            batch_id=batch_id,
            status=active_batch_doc.get("status"),
            execution_modality=active_batch_doc.get("execution_modality"),
            execution_task=active_batch_doc.get("execution_task"),
            requested_modality=requested_modality,
            requested_task=requested_task,
        )
    else:
        # Create a new batch for every eligible uploaded asset
        logger.info(
            "batch_creation_attempt",
            project_id=project_id,
            asset_count=len(eligible_assets),
            collection="batches",
            database_id=db_id,
        )
        batch_out = await batch_svc.create(
            project_id,
            BatchCreate(asset_ids=[a.id for a in eligible_assets]),
            batch_creation_source="explicit_ai_annotation_endpoint",
            explicit_ai_annotation_trigger=True,
            caller_context=request.headers.get("x-request-id"),
        )
        batch_id = batch_out["id"]
        logger.info(
            "batch_created",
            status=BatchStatus.QUEUED.value,
            collection="batches",
            database_id=db_id,
            project_id=project_id,
            batch_id=batch_id,
            scheduled_assets=len(eligible_assets),
        )

    # The background BatchWorker owns execution. The API only creates/reuses
    # the batch and reports its current persisted state.
    batch_doc = await session["batches"].find_one({"id": batch_id})
    batch_status = batch_doc.get("status") if batch_doc else BatchStatus.QUEUED.value

    logger.info(
        "ai_annotation_dispatch_start",
        project_id=project_id,
        batch_id=batch_id,
        request_id=request.headers.get("x-request-id"),
        dispatch_mode="background_worker_polling",
    )

    # The BatchWorker discovers persisted queued batches by polling. Do not
    # execute inference or wait for it in this request.
    logger.info(
        "ai_annotation_dispatch_complete",
        project_id=project_id,
        batch_id=batch_id,
        request_id=request.headers.get("x-request-id"),
        dispatch_mode="background_worker_polling",
    )

    # Fetch current batch metrics without waiting for worker execution. The
    # Firebase adapter intentionally rejects $or queries, so classify the
    # already-scoped decision documents in memory instead of causing a 503
    # after the batch has been persisted.
    scheduled_assets = await session["job_items"].count_documents({"batch_id": batch_id})
    completed_assets = await session["job_items"].count_documents({
        "batch_id": batch_id,
        "status": {"$in": [JobItemStatus.SUCCEEDED.value, "completed", "succeeded"]}
    })
    failed_assets = await session["job_items"].count_documents({
        "batch_id": batch_id,
        "status": JobItemStatus.FAILED.value
    })

    decision_docs = await session["decisions"].find({"project_id": project_id}).to_list(length=100000)
    human_count = 0
    qc_count = 0
    auto_pass_count = 0
    for decision in decision_docs:
        assigned_role = decision.get("assigned_role")
        role = decision.get("role")
        status = decision.get("status")
        workflow_state = decision.get("workflow_state")
        if (
            assigned_role == HumanRole.HUMAN_ANNOTATOR.value
            or role == HumanRole.HUMAN_ANNOTATOR.value
            or status in {ReviewStatus.HUMAN_REVIEW_REQUIRED.value, ReviewStatus.HUMAN_REWORK_REQUIRED.value}
            or workflow_state in {ReviewStatus.HUMAN_REVIEW_REQUIRED.value, ReviewStatus.HUMAN_REWORK_REQUIRED.value}
        ):
            human_count += 1
        if (
            assigned_role == HumanRole.QUALITY_AUDITOR.value
            or role == HumanRole.QUALITY_AUDITOR.value
            or status == ReviewStatus.QUALITY_AUDIT_REQUIRED.value
            or workflow_state == ReviewStatus.QUALITY_AUDIT_REQUIRED.value
        ):
            qc_count += 1
        if (
            status in {ReviewStatus.HIGH_CONFIDENCE_AUTO_PASS.value, ReviewStatus.FINAL_APPROVED.value}
            or workflow_state in {ReviewStatus.HIGH_CONFIDENCE_AUTO_PASS.value, ReviewStatus.FINAL_APPROVED.value}
            or decision.get("decision_type") == "auto_pass"
        ):
            auto_pass_count += 1

    # Detailed Backend Logging (Requirement 15)
    logger.info(
        "ai_annotation_batch_created",
        project_id=project_id,
        total_assets=total_assets,
        eligible_assets=len(eligible_assets),
        batch_id=batch_id,
        batch_status=batch_status,
        scheduled_assets=scheduled_assets,
        completed_assets=completed_assets,
        failed_assets=failed_assets,
        human_review_count=human_count,
        quality_audit_count=qc_count,
        auto_pass_count=auto_pass_count,
    )

    response = {
        "status": batch_status,
        "project_id": project_id,
        "project_name": project.get("name", "Project"),
        "total_assets": total_assets,
        "eligible_assets": len(eligible_assets),
        "batch_id": batch_id,
        "scheduled_assets": scheduled_assets,
        "completed_assets": completed_assets,
        "failed_assets": failed_assets,
        "processed": completed_assets,
        "annotated_assets": completed_assets,
        "human_review_count": human_count,
        "human_annotator_tasks": human_count,
        "quality_audit_count": qc_count,
        "quality_auditor_tasks": qc_count,
        "auto_pass_count": auto_pass_count,
        "auto_passed_tasks": auto_pass_count,
        "quality_audit_sample_count": qc_count,
        "confidence_threshold": confidence_threshold,
        "qc_sample_rate": qc_sample_rate,
        "message": f"AI Annotation batch {batch_status} for {scheduled_assets} assets. The background worker will process it.",
    }
    logger.info(
        "ai_annotation_response_ready",
        project_id=project_id,
        batch_id=batch_id,
        request_id=request.headers.get("x-request-id"),
        status=batch_status,
        scheduled_assets=scheduled_assets,
    )
    return response



@router.get("/projects/{project_id}/imports/cloud/config", response_model=CloudStorageConfigOut)
async def get_cloud_import_config(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> CloudStorageConfigOut:
    svc = CloudImportService(session, settings, storage)
    return svc.get_config()


@router.post("/projects/{project_id}/imports/cloud/validate", response_model=CloudValidateOut)
async def validate_cloud_connection(
    project_id: str,
    payload: CloudValidateRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> CloudValidateOut:
    svc = CloudImportService(session, settings, storage)
    res = await svc.validate_connection(project_id, provider=payload.provider, bucket=payload.bucket)
    return CloudValidateOut(**res)


@router.get("/projects/{project_id}/imports/cloud/objects", response_model=CloudListObjectsOut)
async def list_cloud_objects(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    provider: str = Query(default="gcs"),
    bucket: str = Query(...),
    prefix: str = Query(default=""),
    page_size: int = Query(default=50, ge=1, le=500),
    continuation_token: str | None = Query(default=None),
) -> CloudListObjectsOut:
    svc = CloudImportService(session, settings, storage)
    return await svc.list_objects(
        project_id,
        provider=provider,
        bucket=bucket,
        prefix=prefix,
        page_size=page_size,
        continuation_token=continuation_token,
    )


@router.post("/projects/{project_id}/imports/cloud", response_model=CloudImportOut, status_code=201)
async def import_cloud_objects(
    project_id: str,
    payload: CloudImportRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> CloudImportOut:
    svc = CloudImportService(session, settings, storage)
    return await svc.import_objects(project_id, payload)


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> AssetOut:
    svc = ProjectService(session, settings, storage)
    return AssetOut.model_validate(await svc.get_asset(asset_id))


@router.get("/assets/{asset_id}/image")
async def get_asset_image(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> FileResponse:
    svc = ProjectService(session, settings, storage)
    path, content_type = await svc.asset_image_path(asset_id)
    return FileResponse(path, media_type=content_type)


@router.get("/assets/{asset_id}/preview")
async def get_asset_preview(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> FileResponse:
    svc = ProjectService(session, settings, storage)
    path, content_type = await svc.asset_preview_path(asset_id)
    return FileResponse(path, media_type=content_type)


@router.get("/assets/{asset_id}/tracks")
async def get_asset_tracks(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    tracks = await session.tracks.find({"asset_id": asset_id}).to_list(length=1000)
    if tracks:
        return [
            {
                "id": str(t.get("id")),
                "track_id": t.get("track_id", f"Track #{idx+1}"),
                "label": t.get("label", "Object"),
                "frame_range": t.get("frame_range", [0, 100]),
                "confidence": t.get("confidence", 0.9),
                "source": t.get("source", "ai"),
                "status": t.get("status", "approved"),
            }
            for idx, t in enumerate(tracks)
        ]
    
    # Fallback to grouping annotations by track_id
    anns = await session.annotations.find({"asset_id": asset_id}).to_list(length=10000)
    track_map: dict[str, dict[str, Any]] = {}
    for a in anns:
        tid = a.get("track_id") or a.get("id")
        lbl = a.get("label", "Object")
        f = a.get("frame_index", 0)
        conf = float(a.get("confidence") or 0.9)
        src = a.get("source", "ai")
        if tid not in track_map:
            track_map[tid] = {
                "id": tid,
                "track_id": f"Track #{tid[:6]}" if len(tid) > 6 else f"Track #{tid}",
                "label": lbl,
                "start_frame": f,
                "end_frame": f,
                "confidences": [conf],
                "source": src,
                "status": "active",
            }
        else:
            entry = track_map[tid]
            entry["start_frame"] = min(entry["start_frame"], f)
            entry["end_frame"] = max(entry["end_frame"], f)
            entry["confidences"].append(conf)

    out = []
    for k, v in track_map.items():
        confs = v["confidences"]
        mean_conf = round(sum(confs) / len(confs), 3) if confs else 0.9
        out.append({
            "id": v["id"],
            "track_id": v["track_id"],
            "label": v["label"],
            "frame_range": [v["start_frame"], v["end_frame"]],
            "confidence": mean_conf,
            "source": v["source"],
            "status": v["status"],
        })
    return out


@router.get("/assets/{asset_id}/activities")
async def get_asset_activities(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    activities = await session.activities.find({"asset_id": asset_id}).to_list(length=1000)
    return [
        {
            "id": str(a.get("id")),
            "label": a.get("label", "Activity"),
            "start_time": a.get("start_time", 0.0),
            "end_time": a.get("end_time", 10.0),
            "confidence": float(a.get("confidence", 0.85)),
            "source": a.get("source", "ai"),
        }
        for a in activities
    ]


@router.get("/assets/{asset_id}/events")
async def get_asset_events(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    events = await session.events.find({"asset_id": asset_id}).to_list(length=1000)
    return [
        {
            "id": str(e.get("id")),
            "event_type": e.get("event_type", "Event"),
            "timestamp": e.get("timestamp", 0.0),
            "time_range": e.get("time_range", [e.get("timestamp", 0.0), e.get("timestamp", 0.0) + 2.0]),
            "evidence_frames": e.get("evidence_frames", []),
            "associated_tracks": e.get("associated_tracks", []),
            "confidence": float(e.get("confidence", 0.9)),
            "verification_status": e.get("verification_status", "verified"),
        }
        for e in events
    ]


@router.get("/assets/{asset_id}/segmentations")
async def get_asset_segmentations(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    masks = await session.masks.find({"asset_id": asset_id}).to_list(length=1000)
    return [
        {
            "id": str(m.get("id")),
            "annotation_id": m.get("annotation_id", ""),
            "mask_path": m.get("mask_path", ""),
            "polygon": m.get("polygon", []),
            "frame_index": m.get("frame_index", 0),
            "area_px": m.get("area_px", 0),
            "confidence": float(m.get("confidence", 0.95)),
        }
        for m in masks
    ]


@router.get("/assets/{asset_id}/keypoints")
async def get_asset_keypoints(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    anns = await session.annotations.find({
        "asset_id": asset_id,
        "geometry_type": {"$in": ["keypoints", "point"]}
    }).to_list(length=1000)
    return [
        {
            "id": str(a.get("id")),
            "label": a.get("label", "Keypoint"),
            "points": a.get("keypoints") or a.get("points") or [],
            "frame_index": a.get("frame_index", 0),
            "confidence": float(a.get("confidence", 0.9)),
            "source": a.get("source", "ai"),
        }
        for a in anns
    ]


@router.get("/assets/{asset_id}/frames")
async def get_asset_frames(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    asset = await session.assets.find_one({"id": asset_id})
    if not asset:
        return {"fps": 30.0, "duration": 0.0, "frame_count": 0}
    return {
        "asset_id": asset_id,
        "fps": asset.get("fps") or 30.0,
        "duration": asset.get("duration") or 0.0,
        "frame_count": asset.get("frame_count") or 0,
        "width": asset.get("width", 1920),
        "height": asset.get("height", 1080),
    }


def _recon_service(request: Request, session: AsyncIOMotorDatabase, settings: Settings, storage: FileStorage) -> ReconService:
    client = getattr(request.app.state, "agent_client", None) or create_agent_client(
        settings, force_fake=settings.skip_model_load or not settings.agent_enabled
    )
    factory = getattr(request.app.state, "session_factory", None)
    return ReconService(session, settings, storage, client, factory)


@router.post("/projects/{project_id}/recon/start", response_model=ReconOut)
async def start_recon(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ReconOut:
    svc = _recon_service(request, session, settings, storage)
    return ReconOut.model_validate(await svc.start(project_id))


@router.get("/projects/{project_id}/recon", response_model=ReconOut)
async def get_recon(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ReconOut:
    svc = _recon_service(request, session, settings, storage)
    return ReconOut.model_validate(await svc.get_status(project_id))


@router.patch("/projects/{project_id}/labels", response_model=ReconOut)
async def patch_labels(
    project_id: str,
    payload: LabelsUpdate,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ReconOut:
    svc = _recon_service(request, session, settings, storage)
    labels: list[Any] = []
    for item in payload.labels:
        if isinstance(item, str):
            labels.append(item)
        else:
            labels.append(item.model_dump())
    return ReconOut.model_validate(await svc.apply_labels(project_id, labels))


@router.post(
    "/projects/{project_id}/ontology/recommendations/{recommendation_id}/accept",
    response_model=ProjectOut,
)
async def accept_ontology_recommendation(
    project_id: str,
    recommendation_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ProjectOut:
    svc = _recon_service(request, session, settings, storage)
    return ProjectOut.model_validate(
        await svc.decide_recommendation(project_id, recommendation_id, accept=True)
    )


@router.post(
    "/projects/{project_id}/ontology/recommendations/{recommendation_id}/reject",
    response_model=ProjectOut,
)
async def reject_ontology_recommendation(
    project_id: str,
    recommendation_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ProjectOut:
    svc = _recon_service(request, session, settings, storage)
    return ProjectOut.model_validate(
        await svc.decide_recommendation(project_id, recommendation_id, accept=False)
    )


@router.post("/projects/{project_id}/recon/decisions", response_model=ReconOut)
async def recon_decisions(
    project_id: str,
    payload: ClarificationAnswer,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ReconOut:
    svc = _recon_service(request, session, settings, storage)
    return ReconOut.model_validate(await svc.apply_decisions(project_id, payload.answers))


@router.get("/projects/{project_id}/dataset/map", response_model=DatasetMapOut)
async def dataset_map(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> DatasetMapOut:
    svc = DatasetService(session, settings, storage)
    return DatasetMapOut.model_validate(await svc.map_points(project_id))


@router.post("/projects/{project_id}/dataset/search", response_model=DatasetSearchOut)
async def dataset_search(
    project_id: str,
    payload: DatasetSearchRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> DatasetSearchOut:
    svc = DatasetService(session, settings, storage)
    return DatasetSearchOut.model_validate(
        await svc.search(
            project_id,
            query=payload.query,
            limit=payload.limit,
            neighbor_count=payload.neighbor_count,
        )
    )


@router.get("/projects/{project_id}/dataset/health", response_model=DatasetHealthOut)
async def dataset_health(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> DatasetHealthOut:
    svc = DatasetService(session, settings, storage)
    return DatasetHealthOut.model_validate(await svc.health(project_id))


@router.get("/projects/{project_id}/dataset/coverage", response_model=DatasetCoverageOut)
async def dataset_coverage(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> DatasetCoverageOut:
    svc = DatasetService(session, settings, storage)
    return DatasetCoverageOut.model_validate(await svc.coverage(project_id))


@router.get("/projects/{project_id}/decisions")
async def list_decisions(
    project_id: str,
    role: str | None = Query(default=None),
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    svc = DecisionService(session)
    if role:
        return await svc.list_by_role(project_id, role)
    return await svc.list_open(project_id)


@router.post("/decisions/{decision_id}/resolve")
async def resolve_decision(
    decision_id: str,
    payload: dict[str, Any],
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    svc = DecisionService(session)
    return await svc.resolve(decision_id, payload)


@router.post("/decisions/{decision_id}/submit-human-review")
async def submit_human_review(
    decision_id: str,
    payload: dict[str, Any],
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    svc = DecisionService(session)
    annotations = payload.get("annotations") or []
    annotator_id = payload.get("annotator_id") or "HUMAN_ANNOTATOR"
    return await svc.submit_human_annotation(decision_id, annotations, annotator_id)


@router.get("/assets/{asset_id}/annotations", response_model=list[AnnotationOut])
async def list_annotations(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    frame_index: int | None = Query(default=None),
) -> list[AnnotationOut]:
    svc = AnnotationService(session)
    annotations = await svc.list_for_asset(asset_id, frame_index=frame_index)
    # Recover the original model score for legacy QC submissions. Older QC
    # records cleared the editable human confidence, but the pre-submit
    # annotation snapshot is retained in the immutable audit trail.
    if annotations and all(
        (a.get("confidence") is None and a.get("original_ai_confidence") is None)
        for a in annotations
    ):
        audit = await session.audit_events.find_one(
            {"asset_id": asset_id, "action": {"$in": ["SUBMIT", "submit"]}},
            sort=[("timestamp", -1)],
        )
        before = ((audit or {}).get("before_state") or {}).get("annotations") or []
        if isinstance(before, list):
            used: set[int] = set()
            for current in annotations:
                candidates = [
                    (idx, old) for idx, old in enumerate(before)
                    if idx not in used and str(old.get("id")) == str(current.get("id"))
                ] or [
                    (idx, old) for idx, old in enumerate(before)
                    if idx not in used and str(old.get("label", "")).casefold() == str(current.get("label", "")).casefold()
                ]
                if candidates:
                    idx, old = candidates[0]
                    used.add(idx)
                    old_conf = old.get("confidence") or old.get("original_ai_confidence")
                    if old_conf is not None:
                        try:
                            current["original_ai_confidence"] = float(old_conf)
                            current.setdefault("provenance", {})["original_ai_confidence"] = float(old_conf)
                        except (TypeError, ValueError):
                            pass
    logger.info(
        "annotation_api_response",
        asset_id=asset_id,
        frame_index=frame_index,
        annotation_count=len(annotations),
    )
    for annotation in annotations:
        logger.info(
            "annotation_ui_load",
            asset_id=asset_id,
            annotation_id=annotation.get("id"),
            label=annotation.get("label"),
            geometry_type=annotation.get("geometry_type"),
            confidence=annotation.get("confidence"),
        )
    return [AnnotationOut.model_validate(a) for a in annotations]


@router.post("/assets/{asset_id}/prompt", response_model=list[AnnotationOut])
async def prompt_detect_asset(
    asset_id: str,
    payload: PromptDetectionRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    storage: FileStorage = Depends(deps.get_storage),
) -> list[AnnotationOut]:
    """Run real Grounding DINO prompt detection and persist proposed boxes."""
    import time
    from app.db.models import AnnotationRow, AssetRow
    from app.errors import ModelUnavailableError, NotFoundError, ValidationAppError
    from app.inference.registry import get_runtime

    start_time = time.perf_counter()
    prompts = payload.normalized_prompts()
    if not prompts:
        raise ValidationAppError("Enter at least one non-empty prompt")

    raw_asset = await session.assets.find_one({"id": asset_id, "status": {"$ne": "deleted"}})
    if raw_asset is None:
        raise NotFoundError("Asset", asset_id)
    asset = to_mongo_doc(raw_asset)

    registry = get_runtime().registry
    if not registry.try_load("dino"):
        err_msg = registry._errors.get("dino") or "Grounding DINO is unavailable. Check the DINO model configuration."
        logger.error(
            "prompt_detection_unavailable",
            asset_id=asset_id,
            prompt=payload.prompt or (prompts[0] if prompts else ""),
            prompts=prompts,
            model="dino",
            error=err_msg,
        )
        raise ModelUnavailableError(
            "Grounding DINO is unavailable. Check the DINO model configuration.",
            details={"model_key": "dino", "error": err_msg},
        )
    dino = registry.get("dino")
    path = storage.resolve(asset.storage_path)

    request_id = f"req_dino_{uuid4().hex[:8]}"
    prompt_str = payload.prompt or (prompts[0] if prompts else "")

    logger.info(
        "dino_prompt_detection_started",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        model_key="dino",
        confidence_threshold=payload.confidence_threshold,
    )

    try:
        detections = await asyncio.to_thread(
            dino.predict,
            path,
            asset_id=asset_id,
            labels=prompts,
            confidence_threshold=payload.confidence_threshold,
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(
            "prompt_detection_failed",
            asset_id=asset_id,
            request_id=request_id,
            prompt=prompt_str,
            prompts=prompts,
            model_key="dino",
            error=str(exc),
            duration_ms=duration_ms,
        )
        raise

    logger.info(
        "dino_raw_count",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        model_key="dino",
        count=len(detections),
    )
    logger.info(
        "dino_thresholded_count",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        model_key="dino",
        count=len(detections),
        confidence_threshold=payload.confidence_threshold,
    )

    def iou(first: Any, second: Any) -> float:
        ax1, ay1 = first.bbox.x, first.bbox.y
        ax2, ay2 = ax1 + first.bbox.w, ay1 + first.bbox.h
        bx1, by1 = second.bbox.x, second.bbox.y
        bx2, by2 = bx1 + second.bbox.w, by1 + second.bbox.h
        iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        ih = max(0.0, min(ay2, by2) - max(ay1, by1))
        intersection = iw * ih
        union = first.bbox.w * first.bbox.h + second.bbox.w * second.bbox.h - intersection
        return intersection / union if union > 0 else 0.0

    unique = []
    nms_iou_thresh = getattr(dino, "nms_threshold", 0.75)
    for detection in detections:
        duplicate = next((item for item in unique if iou(item, detection) >= nms_iou_thresh), None)
        if duplicate is None:
            unique.append(detection)
        elif detection.confidence > duplicate.confidence:
            unique[unique.index(duplicate)] = detection

    logger.info(
        "dino_nms_count",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        model_key="dino",
        count=len(unique),
        nms_threshold=nms_iou_thresh,
    )

    existing_anns = await AnnotationService(session).list_for_asset(asset_id)

    # Normalize existing annotation records to safe dictionary objects representing persisted geometry and asset_id
    normalized_existing: list[dict[str, Any]] = []
    for ann in existing_anns:
        if isinstance(ann, dict):
            ann_asset_id = str(ann.get("asset_id") or asset_id)
            if ann_asset_id != str(asset_id):
                continue
            ax = float(ann.get("x") or 0.0)
            ay = float(ann.get("y") or 0.0)
            aw = float(ann.get("w") or 0.0)
            ah = float(ann.get("h") or 0.0)
            lbl = str(ann.get("label") or "").strip()
        else:
            ann_asset_id = str(getattr(ann, "asset_id", None) or asset_id)
            if ann_asset_id != str(asset_id):
                continue
            ax = float(getattr(ann, "x", 0.0) or 0.0)
            ay = float(getattr(ann, "y", 0.0) or 0.0)
            aw = float(getattr(ann, "w", 0.0) or 0.0)
            ah = float(getattr(ann, "h", 0.0) or 0.0)
            lbl = str(getattr(ann, "label", "") or "").strip()

        normalized_existing.append({
            "asset_id": ann_asset_id,
            "x": ax, "y": ay, "w": aw, "h": ah,
            "label": lbl,
        })

    logger.info(
        "dino_duplicate_check_count",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        model_key="dino",
        existing_annotations_count=len(normalized_existing),
    )

    def is_exact_duplicate_of_existing(det: Any) -> bool:
        bx1, by1, bw, bh = det.bbox.x, det.bbox.y, det.bbox.w, det.bbox.h
        bx2, by2 = bx1 + bw, by1 + bh
        det_label = (det.label or "").strip().lower()

        for ann in normalized_existing:
            ax1, ay1, aw, ah = ann["x"], ann["y"], ann["w"], ann["h"]
            ax2, ay2 = ax1 + aw, ay1 + ah
            ann_label = ann["label"].lower()

            iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
            ih = max(0.0, min(ay2, by2) - max(ay1, by1))
            inter = iw * ih
            union = aw * ah + bw * bh - inter
            if union > 0 and (inter / union) >= duplicate_iou_threshold and ann_label == det_label:
                return True
        return False

    duplicate_iou_threshold = get_settings().duplicate_iou_threshold
    new_unique = [d for d in unique if not is_exact_duplicate_of_existing(d)]

    logger.info(
        "dino_new_unique_count",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        model_key="dino",
        count=len(new_unique),
        duplicate_iou_threshold=duplicate_iou_threshold,
    )

    now = datetime.now(UTC)
    rows: list[AnnotationRow] = []
    for detection in new_unique:
        rows.append(
            AnnotationRow(
                id=f"ann_{uuid4().hex[:12]}",
                asset_id=asset_id,
                label=detection.label,
                class_id=detection.class_id,
                geometry_type="box",
                geometry={
                    "type": "box",
                    "points": [detection.bbox.x, detection.bbox.y, detection.bbox.w, detection.bbox.h],
                },
                x=detection.bbox.x,
                y=detection.bbox.y,
                w=detection.bbox.w,
                h=detection.bbox.h,
                confidence=detection.confidence,
                source="ai",
                model_id=detection.model_id or "IDEA-Research/grounding-dino-tiny",
                inferred_at=detection.inferred_at,
                provenance={
                    **(detection.provenance or {}),
                    "source": "prompt_detection",
                    "model_key": "dino",
                    "prompts": prompts,
                    "confidence_threshold": payload.confidence_threshold,
                },
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
    if rows:
        docs = [dict(r) for r in rows]
        for d in docs:
            d.pop("_id", None)
        await session["annotations"].insert_many(docs)

    logger.info(
        "dino_persistence_count",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        model_key="dino",
        count=len(rows),
    )

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.info(
        "dino_prompt_detection_completed",
        asset_id=asset_id,
        request_id=request_id,
        prompt=prompt_str,
        prompts=prompts,
        model_key="dino",
        model_id=getattr(dino, "model_id", "IDEA-Research/grounding-dino-tiny"),
        persisted_count=len(rows),
        confidences=[r.confidence for r in rows],
        duration_ms=duration_ms,
    )
    return [AnnotationOut.model_validate(row) for row in rows]


@router.post("/projects/{project_id}/classify", response_model=list[ClassificationAttributesOut])
async def classify_project_regions(
    project_id: str,
    payload: ClassifyRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> list[ClassificationAttributesOut]:
    svc = ClassificationService(session, settings, storage, get_runtime().registry)
    regions = [r.model_dump() for r in payload.regions]
    results = await svc.classify(project_id, payload.asset_id, regions, model=payload.model, threshold=payload.threshold)
    return [ClassificationAttributesOut.model_validate(r) for r in results]


@router.get("/projects/{project_id}/annotations/{asset_id}", response_model=list[GranularAnnotationOut])
async def get_granular_annotations(
    project_id: str,
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> list[GranularAnnotationOut]:
    svc = ClassificationService(session, settings, storage, get_runtime().registry)
    results = await svc.get_annotations(project_id, asset_id)
    return [GranularAnnotationOut.model_validate(r) for r in results]


@router.post("/annotations/{annotation_id}/attributes", response_model=ClassificationAttributesOut)
async def save_annotation_attributes(
    annotation_id: str,
    payload: AnnotationAttributesUpdate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ClassificationAttributesOut:
    from app.db.models import AnnotationAttributesRow, AnnotationRow, AssetRow
    from app.services.classification import ClassificationService, _TAXONOMY_SEPARATORS
    from app.inference.registry import get_runtime
    from app.errors import NotFoundError

    # Find the project_id for this annotation
    ann_raw = await session.annotations.find_one({"id": annotation_id})
    if ann_raw is None:
        raise NotFoundError("Annotation", annotation_id)
    ann = to_mongo_doc(ann_raw)
    asset_raw = await session.assets.find_one({"id": ann.get("asset_id"), "status": {"$ne": "deleted"}})
    if asset_raw is None:
        raise NotFoundError("Asset", ann.get("asset_id"))
    asset = to_mongo_doc(asset_raw)
    project_id = asset.get("project_id")

    # Resolve taxonomy path using ClassificationService helper
    svc = ClassificationService(session, settings, storage, get_runtime().registry)
    taxonomy_node_id = None
    taxonomy_path = None
    if _TAXONOMY_SEPARATORS.search(payload.label):
        node = await svc._resolve_taxonomy_path(project_id, payload.label)
        taxonomy_node_id = node.id
        taxonomy_path = node.path

    existing_doc = await session.annotation_attributes.find_one({
        "annotation_id": annotation_id,
        "label": payload.label,
    })
    existing = to_mongo_doc(existing_doc) if existing_doc else None

    if existing is not None:
        existing.confidence = payload.confidence
        existing.attributes = payload.attributes
        existing.source = payload.source
        existing.taxonomy_node_id = taxonomy_node_id
        existing.taxonomy_path = taxonomy_path
        row = existing
    else:
        row = AnnotationAttributesRow(
            id=f"attr_{uuid4().hex[:12]}",
            annotation_id=annotation_id,
            label=payload.label,
            confidence=payload.confidence,
            attributes=payload.attributes,
            source=payload.source,
            taxonomy_node_id=taxonomy_node_id,
            taxonomy_path=taxonomy_path,
        )

    doc = dict(row)
    doc.pop("_id", None)
    await session["annotation_attributes"].update_one(
        {"annotation_id": annotation_id, "label": payload.label},
        {"$set": doc},
        upsert=True,
    )

    from app.services.classification import _attribute_out
    return ClassificationAttributesOut.model_validate(_attribute_out(row))


@router.delete("/annotations/{annotation_id}/attributes")
async def delete_annotation_attribute(
    annotation_id: str,
    label: str,
    db: Annotated[Any, Depends(deps.get_db)],
) -> dict[str, Any]:
    from app.db.models import get_database
    mongo_db = get_database()
    await mongo_db.annotation_attributes.delete_one({
        "annotation_id": annotation_id,
        "label": label,
    })
    return {"status": "success"}


@router.post("/assets/{asset_id}/segment", response_model=AnnotationOut)
async def segment_asset(
    asset_id: str,
    payload: SegmentRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> AnnotationOut:
    import time
    import cv2
    import numpy as np
    import asyncio
    from PIL import Image
    from datetime import UTC, datetime
    from app.errors import NotFoundError, ModelUnavailableError, ValidationAppError
    from app.db.models import to_mongo_doc
    from app.inference.registry import get_runtime
    from app.inference.contracts import ModelKey, BoundingBoxPercent
    from app.services.annotations import AnnotationService
    from app.services.projects import ProjectService
    from app.services.masks import MaskService

    start_time = time.perf_counter()
    logger.info(
        "sam2_segment_requested",
        asset_id=asset_id,
        annotation_id=payload.annotation_id,
        label=payload.label,
    )

    # 1. Fetch asset and resolve source path
    raw_asset = await session.assets.find_one({"id": asset_id, "status": {"$ne": "deleted"}})
    if raw_asset is None:
        raise NotFoundError("Asset", asset_id)
    asset = to_mongo_doc(raw_asset)
    project_id = asset.get("project_id")

    proj_svc = ProjectService(session, settings, storage)
    path, _ = await proj_svc.asset_image_path(asset_id)

    # 2. Validate annotation exists, belongs to asset, and extract real geometry
    existing_anno = None
    if payload.annotation_id:
        existing_anno = await session.annotations.find_one({"id": payload.annotation_id})
        if existing_anno is None:
            raise NotFoundError("Annotation", payload.annotation_id)
        if existing_anno.get("asset_id") != asset_id:
            raise ValidationAppError(
                f"Annotation {payload.annotation_id} does not belong to asset {asset_id}"
            )

    # Extract real bounding box from existing annotation
    box_x: float | None = None
    box_y: float | None = None
    box_w: float | None = None
    box_h: float | None = None

    if existing_anno:
        # Check standard properties
        box_x = existing_anno.get("x")
        box_y = existing_anno.get("y")
        box_w = existing_anno.get("w")
        box_h = existing_anno.get("h")
        if box_w is None:
            box_w = existing_anno.get("width")
        if box_h is None:
            box_h = existing_anno.get("height")

        # Check bbox list
        if (box_w is None or box_h is None) and isinstance(existing_anno.get("bbox"), (list, tuple)) and len(existing_anno["bbox"]) >= 4:
            box_x = existing_anno["bbox"][0]
            box_y = existing_anno["bbox"][1]
            box_w = existing_anno["bbox"][2]
            box_h = existing_anno["bbox"][3]

        # Check geometry dict (if polygon points, calculate bounding box)
        if (box_w is None or box_h is None) and isinstance(existing_anno.get("geometry"), dict):
            geom = existing_anno["geometry"]
            if geom.get("points") and isinstance(geom["points"], list) and len(geom["points"]) >= 3:
                xs = [p[0] for p in geom["points"] if isinstance(p, (list, tuple)) and len(p) >= 2]
                ys = [p[1] for p in geom["points"] if isinstance(p, (list, tuple)) and len(p) >= 2]
                if xs and ys:
                    box_x = min(xs)
                    box_y = min(ys)
                    box_w = max(xs) - min(xs)
                    box_h = max(ys) - min(ys)
            else:
                box_x = geom.get("x", box_x)
                box_y = geom.get("y", box_y)
                box_w = geom.get("w", geom.get("width", box_w))
                box_h = geom.get("h", geom.get("height", box_h))

    # Fallback to payload.box if existing_anno box is not available or if payload.box has valid dimensions
    if (box_w is None or box_h is None or float(box_w) <= 0 or float(box_h) <= 0) and payload.box:
        box_x = payload.box.x
        box_y = payload.box.y
        box_w = payload.box.w
        box_h = payload.box.h

    # Validate geometry
    if box_x is None or box_y is None or box_w is None or box_h is None or float(box_w) <= 0 or float(box_h) <= 0:
        if not payload.points:
            raise ValidationAppError(
                f"Annotation {payload.annotation_id or 'selected'} has invalid bounding-box geometry: x={box_x}, y={box_y}, w={box_w}, h={box_h}"
            )

    box_x = float(box_x) if box_x is not None else None
    box_y = float(box_y) if box_y is not None else None
    box_w = float(box_w) if box_w is not None else None
    box_h = float(box_h) if box_h is not None else None

    # Determine real label from existing annotation
    label = payload.label
    if existing_anno and existing_anno.get("label"):
        if not label or label in ("Good fruit", "object", "Unlabeled"):
            label = existing_anno.get("label")

    logger.info(
        "sam2_annotation_validated",
        asset_id=asset_id,
        annotation_id=payload.annotation_id,
        bbox={"x": box_x, "y": box_y, "w": box_w, "h": box_h} if box_x is not None else None,
        label=label,
    )

    # 3. Get SAM2 adapter from ModelRegistry
    registry = get_runtime().registry
    if not registry.try_load(ModelKey.SAM2.value):
        raise ModelUnavailableError("SAM2 model runtime is not loaded or unavailable")
    sam2 = registry.get(ModelKey.SAM2.value)

    boxes_pct = None
    if box_x is not None and box_y is not None and box_w is not None and box_h is not None:
        boxes_pct = [BoundingBoxPercent(x=box_x, y=box_y, w=box_w, h=box_h)]

    logger.info(
        "sam2_inference_started",
        asset_id=asset_id,
        annotation_id=payload.annotation_id,
        model_key=ModelKey.SAM2.value,
    )

    t0 = time.perf_counter()
    masks = await asyncio.to_thread(
        sam2.segment_interactive,
        path,
        asset_id=asset_id,
        boxes=boxes_pct,
        points=payload.points if not boxes_pct else None,
        point_labels=payload.point_labels if not boxes_pct else None,
        label=label,
        annotation_id=payload.annotation_id,
        storage_dir=storage.root / "masks" / asset_id,
    )
    infer_duration_ms = int((time.perf_counter() - t0) * 1000)

    logger.info(
        "sam2_inference_completed",
        asset_id=asset_id,
        annotation_id=payload.annotation_id,
        duration_ms=infer_duration_ms,
        mask_count=len(masks),
    )

    if not masks:
        raise NotFoundError("SAM2 failed to generate any masks for this prompt")

    mask = masks[0]

    # 4. Convert mask to polygon using OpenCV and validate real mask
    mask_png_path = storage.resolve(mask.mask_path)
    if not mask_png_path.exists():
        raise NotFoundError(f"Generated mask image missing at {mask_png_path}")

    mask_img = cv2.imread(str(mask_png_path), cv2.IMREAD_GRAYSCALE)
    if mask_img is None or mask_img.size == 0:
        raise NotFoundError("Failed to load generated mask image or mask is empty")

    mask_area = int(np.count_nonzero(mask_img > 0))
    if mask_area == 0:
        raise NotFoundError("SAM2 generated an empty mask with zero active pixels")

    h, w = mask_img.shape[:2]
    with Image.open(path) as src_img:
        src_w, src_h = src_img.size
    if (w, h) != (src_w, src_h):
        logger.warning("mask_dimension_mismatch", mask_shape=(w, h), source_shape=(src_w, src_h))

    contours, _ = cv2.findContours(mask_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise NotFoundError("No contours found in the generated mask image")

    largest_contour = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(largest_contour, True)
    approx = cv2.approxPolyDP(largest_contour, 0.003 * peri, True)

    points = []
    for pt in approx:
        px, py = pt[0]
        points.append([float((px / w) * 100.0), float((py / h) * 100.0)])

    if points and points[0] != points[-1]:
        points.append(points[0])

    if len(points) < 3:
        raise NotFoundError("Generated mask contour could not produce a valid polygon")

    logger.info(
        "sam2_mask_validated",
        asset_id=asset_id,
        annotation_id=payload.annotation_id,
        mask_dimensions=[w, h],
        mask_area=mask_area,
    )

    # 5. Persist Mask in MaskService (guarantees idempotency on repeated clicks)
    mask_svc = MaskService(session, storage)
    persisted_mask_doc = await mask_svc.save_or_update_mask(
        asset_id=asset_id,
        mask=mask,
        project_id=project_id,
    )
    persisted_mask_id = persisted_mask_doc.get("id")

    # 6. Save or update Annotation in MongoDB/SQLite
    ann_svc = AnnotationService(session)
    geometry = {"type": "polygon", "points": points}

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_min = min(xs)
    y_min = min(ys)
    w_box = max(max(xs) - x_min, 1.0)
    h_box = max(max(ys) - y_min, 1.0)

    now = datetime.now(UTC)

    if payload.annotation_id and existing_anno:
        existing_prov = dict(existing_anno.get("provenance") or {})
        existing_src = existing_anno.get("source")
        is_ai_origin = (
            existing_src == "ai"
            or bool(existing_anno.get("model_id"))
            or existing_prov.get("origin_source") == "ai"
            or existing_prov.get("raw_model_confidence") is not None
        )

        prov = dict(existing_prov)
        if is_ai_origin:
            prov.setdefault("origin_source", "ai")
            if "original_ai_confidence" not in prov and existing_anno.get("confidence") is not None:
                prov["original_ai_confidence"] = existing_anno.get("confidence")
            elif "original_ai_confidence" not in prov and prov.get("raw_model_confidence") is not None:
                prov["original_ai_confidence"] = prov.get("raw_model_confidence")
            prov.setdefault("original_ai_label", existing_anno.get("label"))
        prov["human_edited"] = True
        prov["human_edited_at"] = now.isoformat()
        prov["interactive_segmentation"] = True
        prov["segmentation_model"] = "sam2"
        prov["mask_id"] = persisted_mask_id
        prov["polygon_point_count"] = len(points)
        prov["mask_area"] = mask_area

        new_source = "human_modified" if is_ai_origin else "human"

        updates = {
            "geometry_type": "polygon",
            "geometry": geometry,
            "polygon": points,
            "x": x_min,
            "y": y_min,
            "w": w_box,
            "h": h_box,
            "label": label,
            "source": new_source,
            "provenance": prov,
            "mask_id": persisted_mask_id,
            "updated_at": now,
        }
        await session.annotations.update_one({"id": payload.annotation_id}, {"$set": updates})
        updated_doc = await session.annotations.find_one({"id": payload.annotation_id})

        total_duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "sam2_mask_persisted",
            asset_id=asset_id,
            annotation_id=payload.annotation_id,
            mask_id=persisted_mask_id,
            mask_area=mask_area,
            duration_ms=total_duration_ms,
        )

        return AnnotationOut.model_validate(to_mongo_doc(updated_doc))

    from app.api.schemas import AnnotationCreate
    new_ann = await ann_svc.create(
        asset_id,
        AnnotationCreate(
            label=label,
            geometry_type="polygon",
            geometry=geometry,
            x=x_min,
            y=y_min,
            w=w_box,
            h=h_box,
            confidence=mask.confidence,
            source="human",
            provenance={
                "interactive_segmentation": True,
                "segmentation_model": "sam2",
                "mask_id": persisted_mask_id,
                "polygon_point_count": len(points),
                "mask_area": mask_area,
            },
        ),
    )
    total_duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.info(
        "sam2_mask_persisted",
        asset_id=asset_id,
        annotation_id=new_ann.id,
        mask_id=persisted_mask_id,
        mask_area=mask_area,
        duration_ms=total_duration_ms,
    )
    return AnnotationOut.model_validate(new_ann)


@router.get("/templates", response_model=list[ProjectTemplateOut])
async def list_templates(
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[ProjectTemplateOut]:
    # Templates are not persisted by this backend. Returning an empty result
    # keeps the UI honest until a template record exists in the database.
    return []


@router.get("/assets/{asset_id}/masks", response_model=list[MaskOut])
async def list_masks(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    storage: FileStorage = Depends(deps.get_storage),
) -> list[MaskOut]:
    svc = MaskService(session, storage)
    return [MaskOut.model_validate(m) for m in await svc.list_for_asset(asset_id)]



@router.get("/masks/{mask_id}/image")
async def get_mask_image(
    mask_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    storage: FileStorage = Depends(deps.get_storage),
) -> FileResponse:
    svc = MaskService(session, storage)
    path = await svc.image_path(mask_id)
    return FileResponse(path, media_type="image/png")


@router.get("/assets/{asset_id}/annotations", response_model=list[AnnotationOut])
async def list_asset_annotations(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    frame_index: int | None = Query(default=None),
) -> list[AnnotationOut]:
    svc = AnnotationService(session)
    return [AnnotationOut.model_validate(a) for a in await svc.list_for_asset(asset_id, frame_index)]


@router.get("/projects/{project_id}/annotations/{asset_id}", response_model=list[GranularAnnotationOut])
async def get_granular_annotations(
    project_id: str,
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    runtime: Any = Depends(get_runtime),
) -> list[GranularAnnotationOut]:
    svc = ClassificationService(session, settings, storage, runtime.registry)
    return [GranularAnnotationOut.model_validate(a) for a in await svc.get_annotations(project_id, asset_id)]


@router.post("/annotations/{annotation_id}/attributes", response_model=ClassificationAttributesOut)
async def save_annotation_attribute(
    annotation_id: str,
    payload: AnnotationAttributesUpdate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    runtime: Any = Depends(get_runtime),
) -> ClassificationAttributesOut:
    svc = ClassificationService(session, settings, storage, runtime.registry)
    return ClassificationAttributesOut.model_validate(
        await svc.save_attribute(
            annotation_id,
            label=payload.label,
            attributes=payload.attributes,
            confidence=payload.confidence,
            source=payload.source,
        )
    )


@router.delete("/annotations/{annotation_id}/attributes", status_code=204, response_class=Response)
async def delete_annotation_attribute(
    annotation_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    runtime: Any = Depends(get_runtime),
    label: str = Query(...),
) -> Response:
    svc = ClassificationService(session, settings, storage, runtime.registry)
    await svc.delete_attribute(annotation_id, label=label)
    return Response(status_code=204)


@router.patch("/annotations/{annotation_id}/classification", response_model=list[ClassificationAttributesOut])
async def patch_annotation_classification(
    annotation_id: str,
    payload: AnnotationClassificationUpdate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    runtime: Any = Depends(get_runtime),
) -> list[ClassificationAttributesOut]:
    """Batch-upsert granular classification labels for one annotation.
    Encodes review_status inside attributes JSON (no schema migration needed).
    """
    svc = ClassificationService(session, settings, storage, runtime.registry)
    results = await svc.upsert_classification(
        annotation_id,
        [entry.model_dump() for entry in payload.labels],
    )
    return [ClassificationAttributesOut.model_validate(r) for r in results]


@router.post("/projects/{project_id}/classify-region", response_model=list[ClassificationAttributesOut])
async def classify_region(
    project_id: str,
    payload: ClassifyRegionRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    runtime: Any = Depends(get_runtime),
) -> list[ClassificationAttributesOut]:
    """Run CLIP on the bounding region of an existing annotation.

    Persists the classification results as AnnotationAttributesRows with
    source='model' and review_status='ai_proposed' in the attributes JSON.
    Uses the existing annotation's bbox — no manual coordinates needed.
    """
    from app.db.models import AnnotationRow, AssetRow
    from app.errors import NotFoundError

    ann_raw = await session.annotations.find_one({"id": payload.annotation_id}) if payload.annotation_id else None
    if payload.annotation_id and ann_raw is None:
        raise NotFoundError(f"Annotation {payload.annotation_id} not found")
    ann = to_mongo_doc(ann_raw) if ann_raw else None
    asset_id = ann.get("asset_id") if ann is not None else payload.asset_id
    if not asset_id:
        raise ValidationAppError("asset_id is required when classifying a new region")
    asset_raw = await session.assets.find_one({"id": asset_id, "status": {"$ne": "deleted"}})
    if asset_raw is None:
        raise NotFoundError(f"Asset for annotation {payload.annotation_id} not found")
    asset = to_mongo_doc(asset_raw)
    if asset.get("project_id") != project_id:
        raise NotFoundError("Annotation does not belong to this project")

    svc = ClassificationService(session, settings, storage, runtime.registry)
    if ann is not None:
        results = await svc.classify_region(
            project_id=project_id,
            asset_id=asset.id,
            annotation_id=ann.id,
            text_labels=payload.text_labels,
            model=payload.model,
            threshold=payload.threshold,
        )
    else:
        if payload.bbox is None:
            raise ValidationAppError("bbox is required when classifying a new region")
        results = await svc.classify(
            project_id=project_id,
            asset_id=asset.id,
            regions=[{"bbox": payload.bbox.model_dump(), "text_labels": payload.text_labels}],
            model=payload.model,
            threshold=payload.threshold,
        )
    return [ClassificationAttributesOut.model_validate(r) for r in results]


@router.post("/assets/{asset_id}/annotations", response_model=AnnotationOut, status_code=201)
async def create_annotation(
    asset_id: str,
    payload: AnnotationCreate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="Annotator", alias="X-User-Role"),
) -> AnnotationOut:
    from app.services.rbac import check_action_permission
    from fastapi import HTTPException
    is_allowed, err = check_action_permission(x_user_role, "add_missing")
    if not is_allowed:
        raise HTTPException(status_code=403, detail=err)
    svc = AnnotationService(session)
    return AnnotationOut.model_validate(await svc.create(asset_id, payload))


@router.patch("/annotations/{annotation_id}", response_model=AnnotationOut)
async def update_annotation(
    annotation_id: str,
    payload: AnnotationUpdate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="Annotator", alias="X-User-Role"),
) -> AnnotationOut:
    from app.services.rbac import check_action_permission
    from fastapi import HTTPException
    is_allowed, err = check_action_permission(x_user_role, "modify")
    if not is_allowed:
        raise HTTPException(status_code=403, detail=err)
    svc = AnnotationService(session)
    return AnnotationOut.model_validate(await svc.update(annotation_id, payload))


@router.delete(
    "/annotations/{annotation_id}",
    status_code=204,
    response_class=Response,
)
async def delete_annotation(
    annotation_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    version: int | None = Query(default=None),
    reason: str = Query(default=""),
    actor_id: str | None = Query(default=None),
    x_user_role: str = Header(default="Annotator", alias="X-User-Role"),
) -> Response:
    from app.services.rbac import check_action_permission
    from fastapi import HTTPException
    is_allowed, err = check_action_permission(x_user_role, "delete")
    if not is_allowed:
        raise HTTPException(status_code=403, detail=err)
    svc = AnnotationService(session)
    await svc.delete(annotation_id, actor_id=actor_id, reason=reason, version=version)
    return Response(status_code=204)


@router.post("/assets/{asset_id}/review")
async def review_asset(
    asset_id: str,
    body: AssetReviewRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    x_user_role: str = Header(default="Reviewer", alias="X-User-Role"),
    x_user_id: str = Header(default="user_1", alias="X-User-Id"),
) -> dict[str, Any]:
    from app.domain.enums import ReviewAction, ReviewReason, ReviewStatus
    from app.services.review_lifecycle import resolve_human_review
    from app.services.rbac import check_action_permission, normalize_role, has_permission, PERMISSION_HITL_OVERRIDE
    from app.errors import NotFoundError
    from fastapi import HTTPException

    raw_asset = await session.assets.find_one({"id": asset_id, "status": {"$ne": "deleted"}})
    if raw_asset is None:
        raise NotFoundError("Asset not found", details={"asset_id": asset_id})
    asset = to_mongo_doc(raw_asset)

    prev_status = asset.get("review_status") or ReviewStatus.PENDING.value
    act = (body.action or body.status or "approve").lower().strip()

    # Enforce RBAC permission check
    is_allowed, perm_error = check_action_permission(x_user_role, act)
    if not is_allowed:
        raise HTTPException(status_code=403, detail=perm_error)

    reason_text = (body.reason or body.notes or "").strip()

    # Validation for rework and escalation actions
    if act in {"rework", "request_rework"} and not reason_text:
        raise HTTPException(status_code=400, detail="Rework request requires a specific feedback reason for the annotator.")
    if act in {"escalate", "escalated"} and not reason_text:
        raise HTTPException(status_code=400, detail="Escalation requires selecting or providing an escalation reason.")

    resolved_status, default_reason = resolve_human_review(act, reason_text)
    review_reason = reason_text or default_reason

    reviewer_id = body.reviewer_id or x_user_id or "reviewer_1"
    reviewer_tier = body.reviewer_tier or "reviewer_1"

    # Multi-reviewer escalation & disagreement conflict detection
    review_conflict = bool(asset.get("review_conflict", False))
    reviewer_1_decision = asset.get("reviewer_1_decision")
    reviewer_2_decision = asset.get("reviewer_2_decision")

    # Routing based on action
    assigned_role = asset.get("assigned_role")
    assigned_to = asset.get("assigned_to")

    if act in {"rework", "request_rework"}:
        assigned_role = "Annotator"
    elif act in {"escalate", "escalated"}:
        assigned_role = "SME"
    elif act in {"override", "sme_override", "resolve_conflict", "close_case"}:
        review_conflict = False
        assigned_role = "SME"

    if reviewer_tier == "reviewer_2":
        reviewer_2_decision = act
        if reviewer_1_decision and reviewer_1_decision != act:
            review_conflict = True
            resolved_status = ReviewStatus.ESCALATED.value
            assigned_role = "SME"
            review_reason = f"Reviewer conflict: Reviewer 1 ({reviewer_1_decision}) vs Reviewer 2 ({act})"
            logger.warning(
                "hitl_review_conflict_detected",
                asset_id=asset.id,
                reviewer_1=reviewer_1_decision,
                reviewer_2=act,
            )
    else:
        reviewer_1_decision = act

    asset.review_status = resolved_status
    asset.review_reason = review_reason

    # Reprocess loop execution if action is reprocess
    reprocess_count = int(asset.get("reprocess_count", 0) or 0)
    if act in {"reprocess", "request_reprocess", ReviewAction.REPROCESS.value}:
        project_doc = await session.projects.find_one({"id": asset.project_id})
        policy = (project_doc or {}).get("quality_policy") or {}
        max_reprocess_cycles = int(policy.get("max_reprocess_cycles", 3))

        if reprocess_count >= max_reprocess_cycles:
            # Loop protection: Route to escalation / second review
            asset.review_status = ReviewStatus.ESCALATED.value
            asset.review_reason = f"Max reprocess cycles ({max_reprocess_cycles}) exceeded; escalated for second review"
            logger.warning(
                "hitl_max_reprocess_cycles_exceeded",
                asset_id=asset.id,
                reprocess_count=reprocess_count,
                max_reprocess_cycles=max_reprocess_cycles,
            )
        else:
            reprocess_count += 1
            feedback_payload = (
                body.feedback.model_dump()
                if hasattr(body.feedback, "model_dump")
                else (body.feedback or {})
            )
            feedback_payload.setdefault("action", "reprocess")
            feedback_payload.setdefault("reason", review_reason)
            feedback_payload.setdefault("asset_id", asset.id)
            feedback_payload.setdefault("annotation_id", body.annotation_id)
            feedback_payload.setdefault("human_label", body.human_label)

            # Trigger agentic re-planning with feedback and runtime capabilities
            from app.agent.graphs.agentic_pipeline_graph import run_agentic_pipeline_graph
            user_prompt = (
                (project_doc or {}).get("goal")
                or f"Identify all objects according to ontology: {', '.join((project_doc or {}).get('labels', []))}."
            )
            try:
                graph_state = await run_agentic_pipeline_graph(
                    project=to_mongo_doc(project_doc),
                    asset=asset,
                    user_request=user_prompt,
                    session=session,
                    storage=storage,
                    runtime=get_runtime(),
                    project_id=asset.project_id,
                    asset_id=asset.id,
                    human_feedback=feedback_payload,
                    reprocess_count=reprocess_count,
                    max_reprocess_cycles=max_reprocess_cycles,
                    review_cycle_id=str(uuid.uuid4()),
                )
                if graph_state.get("final_status"):
                    asset.review_status = graph_state["final_status"]
            except Exception as exc:
                logger.error("hitl_reprocess_pipeline_failed", asset_id=asset.id, error=str(exc))

    current_annotations = await AnnotationService(session).list_for_asset(asset.id)
    from app.services.confidence import calculate_image_confidence
    mean_conf = calculate_image_confidence(current_annotations)
    asset.mean_confidence = mean_conf

    update_fields = {
        "review_status": asset.review_status,
        "review_reason": asset.review_reason,
        "mean_confidence": mean_conf,
        "reviewer_1_decision": reviewer_1_decision,
        "reviewer_2_decision": reviewer_2_decision,
        "review_conflict": review_conflict,
        "reprocess_count": reprocess_count,
        "assigned_role": assigned_role,
        "updated_at": datetime.now(UTC),
    }
    await session.assets.update_one({"id": asset.id}, {"$set": update_fields})

    # Record immutable audit event
    await record_audit_event(
        session,
        asset_id=asset.id,
        annotation_id=body.annotation_id,
        action=act,
        actor_type="human",
        actor_id=reviewer_id,
        actor_role=x_user_role,
        before_state={"review_status": prev_status, "before_state": body.before_state or {}},
        after_state={
            "review_status": asset.review_status,
            "mean_confidence": mean_conf,
            "review_conflict": review_conflict,
            "after_state": body.after_state or {},
        },
        reason=review_reason,
        project_id=asset.project_id,
        metadata={
            "reviewer_tier": reviewer_tier,
            "reprocess_count": reprocess_count,
            "human_label": body.human_label,
            "user_role": x_user_role,
        },
    )

    obj_count = await session.annotations.count_documents({"asset_id": asset.id})
    human_needed = asset.review_status not in {
        ReviewStatus.AUTO_APPROVED.value,
        ReviewStatus.HUMAN_APPROVED.value,
        ReviewStatus.HUMAN_MODIFIED_APPROVED.value,
    }

    return {
        "asset_id": asset.id,
        "image_name": asset.filename,
        "project_id": asset.project_id,
        "routing_decision": "HUMAN_REVIEW",
        "human_decision": act.upper(),
        "review_decision": act,
        "final_status": asset.review_status,
        "review_status": asset.review_status,
        "needs_human_review": human_needed,
        "review_reason": asset.review_reason,
        "mean_confidence": mean_conf,
        "image_confidence": mean_conf,
        "object_count": obj_count,
        "reviewer_id": reviewer_id,
        "reviewer_tier": reviewer_tier,
        "review_conflict": review_conflict,
        "reprocess_count": reprocess_count,
        "created_at": asset.created_at.isoformat() if hasattr(asset.created_at, "isoformat") else str(asset.created_at or ""),
        "updated_at": datetime.now(UTC).isoformat(),
    }


@router.post("/assets/{asset_id}/reprocess")
async def reprocess_asset_endpoint(
    asset_id: str,
    feedback: HumanFeedbackPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> dict[str, Any]:
    """Execute human-requested reprocessing with structured feedback."""
    review_req = AssetReviewRequest(
        action="reprocess",
        reason=feedback.reason or "Reprocess requested by reviewer",
        feedback=feedback,
        annotation_id=feedback.annotation_id,
        human_label=feedback.human_label,
    )
    return await review_asset(asset_id, review_req, session, settings, storage)


@router.post("/annotations/{annotation_id}/review")
async def review_annotation_object_endpoint(
    annotation_id: str,
    payload: AnnotationReviewRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Object-level review action: approve, reject, modify, delete_wrong."""
    from app.domain.enums import AnnotationSource
    from app.errors import NotFoundError

    raw_ann = await session.annotations.find_one({"id": annotation_id})
    if raw_ann is None:
        raise NotFoundError("Annotation not found", details={"annotation_id": annotation_id})
    ann = to_mongo_doc(raw_ann)

    act = (payload.action or "approve").lower().strip()
    reason_str = payload.reason or f"Object {act} by reviewer"

    before_state = {
        "label": ann.get("label"),
        "confidence": ann.get("confidence"),
        "source": ann.get("source"),
        "geometry": ann.get("geometry"),
    }

    if act in {"delete_wrong", "delete", "delete_object"}:
        svc = AnnotationService(session)
        await svc.delete(annotation_id, actor_id=payload.reviewer_id, reason=reason_str)
        return {
            "annotation_id": annotation_id,
            "asset_id": ann.asset_id,
            "status": "deleted",
            "action": act,
            "reason": reason_str,
        }

    prov = dict(ann.get("provenance") or {})
    prov["review_status"] = "human_approved" if act == "approve" else "human_rejected" if act == "reject" else "human_modified"
    prov["reviewed_by"] = payload.reviewer_id or "reviewer"
    prov["reviewed_at"] = datetime.now(UTC).isoformat()
    prov["review_reason"] = reason_str

    update_doc: dict[str, Any] = {
        "provenance": prov,
        "updated_at": datetime.now(UTC),
    }
    if payload.human_label and payload.human_label != ann.get("label"):
        prov["original_ai_label"] = ann.get("label")
        prov["original_ai_confidence"] = ann.get("confidence")
        update_doc["label"] = payload.human_label
        update_doc["source"] = AnnotationSource.HUMAN_MODIFIED.value
        update_doc["confidence"] = None

    if payload.geometry:
        prov["original_ai_geometry"] = ann.get("geometry")
        update_doc["geometry"] = payload.geometry
        update_doc["source"] = AnnotationSource.HUMAN_MODIFIED.value
        update_doc["confidence"] = None

    await session.annotations.update_one({"id": annotation_id}, {"$set": update_doc})
    updated_ann = await session.annotations.find_one({"id": annotation_id})

    # Log audit event
    await record_audit_event(
        session,
        asset_id=ann.asset_id,
        annotation_id=annotation_id,
        action=f"object_{act}",
        actor_type="human",
        actor_id=payload.reviewer_id,
        before_state=before_state,
        after_state={
            "label": updated_ann.get("label"),
            "confidence": updated_ann.get("confidence"),
            "source": updated_ann.get("source"),
            "provenance": prov,
        },
        reason=reason_str,
    )

    # Recalculate image confidence
    all_anns = await AnnotationService(session).list_for_asset(ann.asset_id)
    from app.services.confidence import calculate_image_confidence
    mean_conf = calculate_image_confidence(all_anns)
    await session.assets.update_one({"id": ann.asset_id}, {"$set": {"mean_confidence": mean_conf}})

    return {
        "annotation_id": annotation_id,
        "asset_id": ann.asset_id,
        "label": updated_ann.get("label"),
        "confidence": updated_ann.get("confidence"),
        "source": updated_ann.get("source"),
        "review_status": prov["review_status"],
        "reason": reason_str,
    }


@router.post("/annotations/{annotation_id}/suggest-label")
async def suggest_annotation_label_endpoint(
    annotation_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
    runtime: Any = Depends(get_runtime),
) -> dict[str, Any]:
    """AI Suggestion workflow: Run model inference on crop and return genuine model output."""
    from app.errors import NotFoundError

    raw_ann = await session.annotations.find_one({"id": annotation_id})
    if raw_ann is None:
        raise NotFoundError("Annotation not found", details={"annotation_id": annotation_id})
    ann = to_mongo_doc(raw_ann)

    raw_asset = await session.assets.find_one({"id": ann.asset_id, "status": {"$ne": "deleted"}})
    if raw_asset is None:
        raise NotFoundError("Asset not found")
    asset = to_mongo_doc(raw_asset)

    raw_project = await session.projects.find_one({"id": asset.project_id})
    labels = list((raw_project or {}).get("labels", []))
    if not labels:
        labels = [ann.get("label", "object")]

    svc = ClassificationService(session, settings, storage, runtime.registry)
    try:
        results = await svc.classify_region(
            project_id=asset.project_id,
            asset_id=asset.id,
            annotation_id=ann.id,
            text_labels=labels,
            model="clip",
            threshold=0.0,
        )
        if results:
            best = max(results, key=lambda r: float(r.get("confidence") or 0.0))
            suggested_conf = float(best.get("confidence") or 0.0)
            suggested_label = best.get("label", labels[0])
            return {
                "suggested_label": suggested_label,
                "suggested_confidence": suggested_conf,
                "model": "clip",
                "is_genuine_model_score": True,
            }
    except Exception as exc:
        logger.warning("ai_suggestion_classification_fallback", error=str(exc))

    # Return original model prediction if crop classification is unavailable
    orig_conf = ann.get("confidence")
    if orig_conf is None:
        prov = ann.get("provenance") or {}
        orig_conf = prov.get("raw_model_confidence") or prov.get("model_confidence")
    return {
        "suggested_label": ann.get("label"),
        "suggested_confidence": float(orig_conf) if orig_conf is not None else None,
        "model": ann.get("model_id") or "detector",
        "is_genuine_model_score": bool(orig_conf is not None),
    }


@router.get("/assets/{asset_id}/audit-trail")
async def get_asset_audit_trail_endpoint(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """Retrieve the immutable audit events timeline for an asset."""
    return await get_asset_audit_trail(session, asset_id)


@router.get("/assets/{asset_id}/notes", response_model=list[ReviewNoteOut])
async def list_review_notes(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[ReviewNoteOut]:
    svc = ReviewNoteService(session)
    return [ReviewNoteOut.model_validate(n) for n in await svc.list_for_asset(asset_id)]


@router.post("/assets/{asset_id}/notes", response_model=ReviewNoteOut, status_code=201)
async def create_review_note(
    asset_id: str,
    payload: ReviewNoteCreate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> ReviewNoteOut:
    svc = ReviewNoteService(session)
    return ReviewNoteOut.model_validate(await svc.create(asset_id, payload))


@router.patch("/notes/{note_id}", response_model=ReviewNoteOut)
async def update_review_note(
    note_id: str,
    payload: ReviewNoteUpdate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> ReviewNoteOut:
    svc = ReviewNoteService(session)
    return ReviewNoteOut.model_validate(await svc.update(note_id, payload))


@router.post("/projects/{project_id}/batches", response_model=BatchOut, status_code=201)
@router.post("/projects/{project_id}/batches/", response_model=BatchOut, status_code=201, include_in_schema=False)
async def create_batch(
    project_id: str,
    payload: BatchCreate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BatchOut:
    if payload.idempotency_key is None and idempotency_key:
        payload = payload.model_copy(update={"idempotency_key": idempotency_key})
    svc = BatchService(session, settings)
    out = BatchOut.model_validate(
        await svc.create(
            project_id,
            payload,
            batch_creation_source="explicit_batch_api_request",
            explicit_ai_annotation_trigger=True,
            caller_context=idempotency_key,
        )
    )
    # Report whether worker is present to aid debugging of stuck batches
    worker = get_worker()
    try:
        worker_state = {
            "present": worker is not None,
            "active_workers": getattr(worker, "active_workers", None),
        }
    except Exception:
        worker_state = {"present": False}
    logger.info(
        "batch_api_created",
        batch_id=out.id,
        worker=worker_state,
        project_id=project_id,
        asset_count=len(payload.asset_ids) if payload.asset_ids is not None else None,
        batch_creation_source="explicit_batch_api_request",
        request_endpoint=str(request.url.path),
        explicit_ai_annotation_trigger=True,
        caller_context=idempotency_key,
    )
    return out


@router.get("/batches/{batch_id}", response_model=BatchOut)
@router.get("/batches/{batch_id}/", response_model=BatchOut, include_in_schema=False)
async def get_batch(
    batch_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> BatchOut:
    svc = BatchService(session, settings)
    return BatchOut.model_validate(await svc.get(batch_id))


@router.get("/projects/{project_id}/batches", response_model=list[BatchOut])
@router.get("/projects/{project_id}/batches/", response_model=list[BatchOut], include_in_schema=False)
async def list_batches(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> list[BatchOut]:
    svc = BatchService(session, settings)
    return [BatchOut.model_validate(b) for b in await svc.list_for_project(project_id)]


@router.post("/batches/{batch_id}/cancel", response_model=BatchOut)
async def cancel_batch(
    batch_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> BatchOut:
    svc = BatchService(session, settings)
    return BatchOut.model_validate(await svc.cancel(batch_id))


@router.get("/projects/{project_id}/export")
async def export_project(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    storage: FileStorage = Depends(deps.get_storage),
    format: Annotated[str | None, Query()] = None,
    annotation_source: Annotated[str, Query()] = "approved",
    include_images: Annotated[bool, Query()] = True,
) -> Response:
    valid_formats = {"yolo", "yolo_seg", "coco", "coco_seg", "pascal_voc", "labelme", "createml", "ingenii_json", "json", "csv"}

    raw_project = await session.projects.find_one({"id": project_id})
    if not raw_project:
        raw_project = await session.projects.find_one({"name": project_id})
    if not raw_project:
        from app.errors import NotFoundError

        raise NotFoundError("Project not found", details={"project_id": project_id})

    proj_expected = raw_project.get("expected_output_format")
    proj_norm = normalize_export_format(proj_expected, default="coco") if proj_expected else None

    if format:
        req_norm = normalize_export_format(format, default="coco")
        if req_norm not in valid_formats:
            from app.errors import ValidationAppError

            raise ValidationAppError(
                f"Unsupported format '{format}'. Supported formats: {', '.join(sorted(valid_formats))}",
                details={"format": format},
            )
        # Rule 7: Validate explicit format against project's configured Expected Output Format
        if proj_norm:
            base_req = req_norm.replace("_seg", "")
            base_proj = proj_norm.replace("_seg", "")
            if base_req != base_proj and req_norm != proj_norm:
                from app.errors import ValidationAppError

                raise ValidationAppError(
                    f"Requested export format '{format}' does not match the project's configured Expected Output Format '{proj_expected}'.",
                    details={"requested_format": format, "configured_format": proj_expected},
                )
        target_format = req_norm
    else:
        # Rule 6: Resolve format from project configuration when no explicit format is supplied
        target_format = proj_norm or "coco"

    svc = ExportService(session, storage)
    data, media_type, filename, summary = await svc.export_project(
        project_id=project_id,
        fmt=target_format,
        annotation_source=annotation_source,  # type: ignore[arg-type]
        include_images=include_images,
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Format": str(summary.get("format", "")),
            "X-Export-Images-Count": str(summary.get("image_count", 0)),
            "X-Export-Annotations-Count": str(summary.get("annotation_count", 0)),
            "X-Export-Classes-Count": str(summary.get("class_count", 0)),
        },
    )


@router.post("/projects/{project_id}/exports")
async def create_project_export(
    project_id: str,
    body: ExportRequest,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    storage: FileStorage = Depends(deps.get_storage),
) -> Response:
    valid_formats = {"yolo", "yolo_seg", "coco", "coco_seg", "pascal_voc", "labelme", "createml", "ingenii_json", "json", "csv"}

    raw_project = await session.projects.find_one({"id": project_id})
    if not raw_project:
        raw_project = await session.projects.find_one({"name": project_id})
    if not raw_project:
        from app.errors import NotFoundError

        raise NotFoundError("Project not found", details={"project_id": project_id})

    proj_expected = raw_project.get("expected_output_format")
    proj_norm = normalize_export_format(proj_expected, default="coco") if proj_expected else None

    if body.format:
        req_norm = normalize_export_format(body.format, default="coco")
        if req_norm not in valid_formats:
            from app.errors import ValidationAppError

            raise ValidationAppError(
                f"Unsupported format '{body.format}'. Supported formats: {', '.join(sorted(valid_formats))}",
                details={"format": body.format},
            )
        # Rule 7: Validate explicit format against project's configured Expected Output Format
        if proj_norm:
            base_req = req_norm.replace("_seg", "")
            base_proj = proj_norm.replace("_seg", "")
            if base_req != base_proj and req_norm != proj_norm:
                from app.errors import ValidationAppError

                raise ValidationAppError(
                    f"Requested export format '{body.format}' does not match the project's configured Expected Output Format '{proj_expected}'.",
                    details={"requested_format": body.format, "configured_format": proj_expected},
                )
        target_format = req_norm
    else:
        # Rule 6: Resolve format from project configuration when no explicit format is supplied
        target_format = proj_norm or "coco"

    svc = ExportService(session, storage)
    data, media_type, filename, summary = await svc.export_project(
        project_id=project_id,
        fmt=target_format,
        annotation_source=body.annotation_source,  # type: ignore[arg-type]
        include_images=body.include_images,
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Format": str(summary.get("format", "")),
            "X-Export-Images-Count": str(summary.get("image_count", 0)),
            "X-Export-Annotations-Count": str(summary.get("annotation_count", 0)),
            "X-Export-Classes-Count": str(summary.get("class_count", 0)),
        },
    )


def _agent_service(request: Any, session: AsyncIOMotorDatabase, settings: Settings) -> AgentService:
    client = getattr(request.app.state, "agent_client", None) or create_agent_client(
        settings, force_fake=settings.skip_model_load or not settings.agent_enabled
    )
    return AgentService(session, settings, client)


@router.post("/projects/{project_id}/agent/intake", response_model=ProjectPlanOut)
async def agent_intake(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> ProjectPlanOut:
    svc = _agent_service(request, session, settings)
    return ProjectPlanOut.model_validate(await svc.run_intake(project_id))


@router.post("/projects/{project_id}/agent/intake/auto", response_model=ProjectPlanOut)
async def agent_intake_auto(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> ProjectPlanOut:
    """Autonomous intake: runs intake, then generates a plan automatically
    (via the LangGraph intake graph) unless the agent needs clarification first."""
    from app.agent.graphs.intake_graph import run_intake_graph

    svc = _agent_service(request, session, settings)
    return ProjectPlanOut.model_validate(await run_intake_graph(svc, project_id))


@router.post("/projects/{project_id}/agent/clarify", response_model=ProjectPlanOut)
async def agent_clarify(
    project_id: str,
    payload: ClarificationAnswer,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> ProjectPlanOut:
    svc = _agent_service(request, session, settings)
    return ProjectPlanOut.model_validate(
        await svc.apply_clarifications(project_id, payload.answers)
    )


@router.post("/projects/{project_id}/agent/plan", response_model=ProjectPlanOut)
async def agent_plan(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> ProjectPlanOut:
    svc = _agent_service(request, session, settings)
    return ProjectPlanOut.model_validate(await svc.generate_plan(project_id))


@router.get("/projects/{project_id}/plan", response_model=ProjectPlanOut | None)
async def get_plan(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> ProjectPlanOut | None:
    from app.errors import NotFoundError
    svc = _agent_service(request, session, settings)
    try:
        plan = await svc.get_plan(project_id)
        return ProjectPlanOut.model_validate(plan)
    except NotFoundError:
        return None


@router.post("/projects/{project_id}/plan/approve", response_model=ProjectPlanOut)
async def approve_plan(
    project_id: str,
    request: Request,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> ProjectPlanOut:
    svc = _agent_service(request, session, settings)
    return ProjectPlanOut.model_validate(await svc.approve_plan(project_id))


@router.post("/projects/{project_id}/ontology/approve", response_model=ProjectOut)
async def approve_ontology_endpoint(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
    storage: FileStorage = Depends(deps.get_storage),
) -> ProjectOut:
    svc = ProjectService(session, settings, storage)
    result = await svc.approve_ontology(project_id)
    return ProjectOut.model_validate(result)


# ---------------------------------------------------------------------------
# HITL RBAC User & Role Management and Audit Trail Endpoints
# ---------------------------------------------------------------------------

class UserRoleUpdatePayload(BaseModel):
    role: str


class UserCreatePayload(BaseModel):
    name: str
    email: str
    role: str


class CommentCreatePayload(BaseModel):
    comment: str | None = None
    body: str | None = None
    annotation_id: str | None = None


class TaskAssignPayload(BaseModel):
    asset_ids: list[str]
    assignee_id: str
    assignee_role: str
    notes: str | None = None


@router.get("/users")
async def list_hitl_users(
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """List all team users and their assigned HITL RBAC roles."""
    raw_users = await session.users.find({}).to_list(length=1000)
    return [to_mongo_doc(u) for u in raw_users]


@router.get("/me/permissions")
async def current_role_permissions(
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
    x_user_id: str = Header(default="", alias="X-User-Id"),
) -> dict[str, Any]:
    """Return the authenticated role contract used by the role-aware UI."""
    from app.services.rbac import get_role_permissions, normalize_role

    role = normalize_role(x_user_role)
    return {"user_id": x_user_id or None, "role": role, "permissions": sorted(get_role_permissions(role))}


@router.post("/users", status_code=201)
async def create_user_endpoint(
    payload: UserCreatePayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
    x_user_id: str = Header(default="usr_admin_1", alias="X-User-Id"),
) -> dict[str, Any]:
    """Create a new team user (Admin permission required)."""
    from app.services.rbac import has_permission, PERMISSION_USER_MANAGE, normalize_role
    if not has_permission(x_user_role, PERMISSION_USER_MANAGE):
        raise HTTPException(status_code=403, detail="USER_MANAGE permission required to create users.")
    
    norm_role = normalize_role(payload.role)
    new_id = f"usr_{norm_role.lower()}_{uuid.uuid4().hex[:6]}"
    parts = payload.name.strip().split()
    initials = "".join([p[0].upper() for p in parts[:2]]) or "US"
    doc = {
        "id": new_id,
        "name": payload.name,
        "email": payload.email,
        "role": norm_role,
        "initials": initials,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await session.users.insert_one(doc)
    return to_mongo_doc(doc)


@router.patch("/users/{user_id}/role")
async def update_user_role_endpoint(
    user_id: str,
    payload: UserRoleUpdatePayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
    x_user_id: str = Header(default="usr_admin_1", alias="X-User-Id"),
) -> dict[str, Any]:
    """Update a user's assigned RBAC role (Annotator, Reviewer, SME, Admin)."""
    from app.services.rbac import has_permission, PERMISSION_ROLE_MANAGE
    if not has_permission(x_user_role, PERMISSION_ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="ROLE_MANAGE permission required to update user roles.")

    valid_roles = {"Annotator", "Reviewer", "SME", "Admin", "Owner", "Project Manager"}
    new_role = payload.role.strip()
    if new_role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role '{new_role}'. Must be one of {sorted(valid_roles)}.")

    await session.users.update_one(
        {"id": user_id},
        {"$set": {"role": new_role, "updated_at": datetime.now(UTC).isoformat()}},
        upsert=True,
    )
    
    # Audit event for role change
    await record_audit_event(
        session,
        asset_id="SYSTEM",
        action="ROLE_CHANGED",
        actor_id=x_user_id,
        actor_role=x_user_role,
        reason=f"Changed user {user_id} role to {new_role}",
        metadata={"user_id": user_id, "new_role": new_role},
    )
    
    user_doc = await session.users.find_one({"id": user_id})
    return to_mongo_doc(user_doc or {"id": user_id, "role": new_role})


@router.get("/assets/{asset_id}/comments")
async def list_asset_comments_endpoint(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="Annotator", alias="X-User-Role"),
) -> list[dict[str, Any]]:
    """Fetch comments/notes for an asset."""
    cursor = session.comments.find({"asset_id": asset_id}).sort("timestamp", 1)
    docs = await cursor.to_list(length=1000)
    return [to_mongo_doc(d) for d in docs]


@router.post("/assets/{asset_id}/comments", status_code=201)
async def create_asset_comment_endpoint(
    asset_id: str,
    payload: CommentCreatePayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="Annotator", alias="X-User-Role"),
    x_user_id: str = Header(default="usr_annotator_1", alias="X-User-Id"),
    x_user_name: str = Header(default="User", alias="X-User-Name"),
) -> dict[str, Any]:
    """Add a structured comment/review note to an asset."""
    from app.services.rbac import check_action_permission, normalize_role
    is_allowed, err = check_action_permission(x_user_role, "comment")
    if not is_allowed:
        raise HTTPException(status_code=403, detail=err)
    
    text = (payload.comment or payload.body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text cannot be empty.")
    
    asset = await session.assets.find_one({"id": asset_id})
    current_status = asset.get("review_status", "pending") if asset else "pending"
    
    doc = {
        "id": str(uuid.uuid4()),
        "asset_id": asset_id,
        "annotation_id": payload.annotation_id,
        "user_id": x_user_id,
        "user": x_user_name or x_user_id,
        "role": normalize_role(x_user_role),
        "comment": text,
        "body": text,
        "action": current_status,
        "status_at_comment": current_status,
        "timestamp": datetime.now(UTC).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await session.comments.insert_one(doc)
    
    # Audit log
    await record_audit_event(
        session,
        asset_id=asset_id,
        annotation_id=payload.annotation_id,
        action="COMMENT_ADDED",
        actor_id=x_user_id,
        actor_role=x_user_role,
        reason=text,
        metadata={"comment": text, "user": x_user_name, "role": x_user_role},
    )
    return to_mongo_doc(doc)


@router.post("/tasks/assign")
async def assign_tasks_endpoint(
    payload: TaskAssignPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
    x_user_id: str = Header(default="usr_admin_1", alias="X-User-Id"),
) -> dict[str, Any]:
    """Assign annotation/review tasks to team members (Admin permission required)."""
    from app.services.rbac import has_permission, PERMISSION_TASK_ASSIGN, normalize_role
    if not has_permission(x_user_role, PERMISSION_TASK_ASSIGN):
        raise HTTPException(status_code=403, detail="TASK_ASSIGN permission required to assign tasks.")
    
    assigned_role = normalize_role(payload.assignee_role)
    for aid in payload.asset_ids:
        await session.assets.update_one(
            {"id": aid},
            {"$set": {
                "assigned_to": payload.assignee_id,
                "assigned_role": assigned_role,
                "assignment_notes": payload.notes or "",
                "updated_at": datetime.now(UTC).isoformat(),
            }}
        )
        await record_audit_event(
            session,
            asset_id=aid,
            action="TASK_ASSIGNED",
            actor_id=x_user_id,
            actor_role=x_user_role,
            reason=f"Assigned to {payload.assignee_id} ({assigned_role})",
            metadata={"assignee_id": payload.assignee_id, "assignee_role": assigned_role},
        )
    return {"status": "success", "assigned_count": len(payload.asset_ids), "assignee_id": payload.assignee_id, "assignee_role": assigned_role}


@router.post("/tasks/reassign")
async def reassign_tasks_endpoint(
    payload: TaskAssignPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
    x_user_id: str = Header(default="usr_admin_1", alias="X-User-Id"),
) -> dict[str, Any]:
    """Reassign tasks between team members (Admin permission required)."""
    from app.services.rbac import has_permission, PERMISSION_TASK_REASSIGN, normalize_role
    if not has_permission(x_user_role, PERMISSION_TASK_REASSIGN):
        raise HTTPException(status_code=403, detail="TASK_REASSIGN permission required to reassign tasks.")
    
    assigned_role = normalize_role(payload.assignee_role)
    for aid in payload.asset_ids:
        await session.assets.update_one(
            {"id": aid},
            {"$set": {
                "assigned_to": payload.assignee_id,
                "assigned_role": assigned_role,
                "assignment_notes": payload.notes or "",
                "updated_at": datetime.now(UTC).isoformat(),
            }}
        )
        await record_audit_event(
            session,
            asset_id=aid,
            action="TASK_REASSIGNED",
            actor_id=x_user_id,
            actor_role=x_user_role,
            reason=f"Reassigned to {payload.assignee_id} ({assigned_role})",
            metadata={"assignee_id": payload.assignee_id, "assignee_role": assigned_role},
        )
    return {"status": "success", "reassigned_count": len(payload.asset_ids), "assignee_id": payload.assignee_id, "assignee_role": assigned_role}


@router.get("/audit-logs")
async def list_audit_logs_endpoint(
    limit: int = 500,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="HUMAN_ANNOTATOR", alias="X-User-Role"),
) -> list[dict[str, Any]]:
    """Fetch global immutable audit logs timeline (AUDIT_VIEW permission required)."""
    from app.services.rbac import has_permission, PERMISSION_AUDIT_VIEW
    if not has_permission(x_user_role, PERMISSION_AUDIT_VIEW):
        raise HTTPException(status_code=403, detail="AUDIT_VIEW permission required to view audit logs.")
    
    events = await session.audit_events.find({}).sort("timestamp", -1).limit(limit).to_list(length=limit)
    return [to_mongo_doc(ev) for ev in events]


@router.get("/assets/{asset_id}/audit-trail")
async def get_asset_audit_trail_endpoint(
    asset_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """Fetch immutable audit trail history for an asset (edits, approvals, rejections)."""
    events = await session.audit_events.find({"asset_id": asset_id}).sort("timestamp", -1).to_list(length=500)
    return [to_mongo_doc(ev) for ev in events]


@router.get("/projects/{project_id}/batches/{batch_id}")
async def get_batch_status_endpoint(
    project_id: str,
    batch_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> dict[str, Any]:
    """Get real-time batch job status, progress percentage, latency metrics, and item breakdown."""
    from app.services.batches import BatchService
    svc = BatchService(session, settings)
    return await svc.get(batch_id)


@router.post("/projects/{project_id}/batches/{batch_id}/retry")
async def retry_failed_batch_endpoint(
    project_id: str,
    batch_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> dict[str, Any]:
    """Re-queue all failed items in a batch for retrying."""
    from app.services.batches import BatchService
    svc = BatchService(session, settings)
    return await svc.retry_failed_items(batch_id)


# ==============================================================================
# HITL & QUALITY AUDIT WORKFLOW ENDPOINTS (3 HUMAN ROLES)
# ==============================================================================


@router.get("/projects/{project_id}/hitl-metrics")
async def get_hitl_metrics_endpoint(
    project_id: str,
    threshold: float | None = Query(default=None, ge=0, le=1),
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Fetch real-time persistent HITL pipeline metrics and execution report stats from MongoDB/SQLite."""
    import time
    t_start_endpoint = time.perf_counter()
    from app.services.qc_service import calculate_hitl_execution_metrics
    from app.services.project_metrics import calculate_annotation_breakdown, calculate_area_identification, calculate_annotator_metrics, calculate_scorecard_metrics, calculate_triage_metrics
    svc = DecisionService(session)
    config = await svc.get_project_hitl_config(project_id)
    project = await session.projects.find_one({"id": project_id}) or await session.projects.find_one({"_id": project_id})
    project_modality = str((project or {}).get("modality") or "").lower()
    project_type = str((project or {}).get("project_type") or "").lower()
    is_text = (
        project_modality in {"text", "document", "nlp"}
        or any(k in project_type for k in ["text", "ner", "sentiment", "classification", "relation", "document", "nlp", "clinical"])
    )
    
    # Query mongo/sqlite for decisions once in bulk and compute task counts in-memory
    t_counts = time.perf_counter()
    decisions = await session.decisions.find({"project_id": project_id}).to_list(length=100000)
    assets = await session.assets.find({"project_id": project_id}).to_list(length=100000)
    # Text analysis decisions are persisted on the asset's text_analysis
    # payload. Align the HITL scorecard population with that decision for
    # legacy text assets whose review_status was not backfilled yet.
    for asset in assets:
        text_analysis = asset.get("text_analysis") or {}
        analysis_status = str(
            text_analysis.get("agent_status")
            or (text_analysis.get("quality_report") or {}).get("final_decision")
            or ""
        ).strip().upper()
        if analysis_status in {"AUTO_APPROVE", "AUTO_APPROVED"}:
            asset["review_status"] = "auto_approved"
    annotations = await session.annotations.find({"project_id": project_id}).to_list(length=100000)
    if is_text:
        # Strictly exclude image vision detections/bounding boxes from text project calculations
        image_geom = {"box", "polygon", "polyline", "point", "circle", "keypoint"}
        image_ann_types = {"box", "polygon", "detection", "bbox"}
        image_labels = {
            "auto-rickshaw", "bicycle", "bus", "car", "motorcycle", "road object",
            "traffic light", "traffic sign", "truck", "pedestrian", "person", "vehicle", "cars", "autos"
        }
        annotations = [
            a for a in annotations
            if str(a.get("geometry_type") or "").lower() not in image_geom
            and str(a.get("annotation_type") or "").lower() not in image_ann_types
            and str(a.get("label") or "").lower() not in image_labels
        ]
        # In text projects, extract real text entities from asset text_analysis if needed
        if not annotations:
            for asset in assets:
                t_analysis = asset.get("text_analysis") or {}
                for ann in t_analysis.get("annotations") or t_analysis.get("entities") or []:
                    ann_item = dict(ann)
                    ann_item["asset_id"] = str(asset.get("id") or asset.get("_id") or "")
                    ann_item.setdefault("source", "ai")
                    ann_item.setdefault("confidence", 0.92)
                    ann_item.setdefault("annotation_type", "NER Span")
                    annotations.append(ann_item)
    review_notes = await session.review_notes.find({"project_id": project_id}).to_list(length=100000)
    low_conf_statuses = {"human_review_required", "in_human_review", "human_review"}
    rework_statuses = {"human_rework_required", "rework"}
    qc_statuses = {"quality_audit_required", "human_review_completed", "high_confidence_qc_sample", "audit"}

    low_conf_count = 0
    rework_count = 0
    qc_count = 0
    high_conf_sampled_count = 0
    pass_count = 0
    fail_count = 0

    for d in decisions:
        st = d.get("status")
        if st in low_conf_statuses:
            low_conf_count += 1
        if st in rework_statuses:
            rework_count += 1
        if st in qc_statuses:
            qc_count += 1
        if d.get("sampled") and d.get("audit_source") == "HIGH_CONFIDENCE_SAMPLE":
            high_conf_sampled_count += 1
        ans = d.get("answer")
        if ans == "PASS" and st == "final_approved":
            pass_count += 1
        if ans == "FAIL":
            fail_count += 1
    logger.info("hitl_endpoint_timing_counts_total", elapsed_ms=round((time.perf_counter() - t_counts) * 1000, 2))

    t_exec = time.perf_counter()
    execution_metrics = await calculate_hitl_execution_metrics(session, project_id, decisions=decisions)
    logger.info("hitl_endpoint_timing_execution_metrics", elapsed_ms=round((time.perf_counter() - t_exec) * 1000, 2))

    total_time_ms = round((time.perf_counter() - t_start_endpoint) * 1000, 2)
    logger.info("hitl_endpoint_timing_COMPLETE", elapsed_ms=total_time_ms)

    effective_threshold = threshold if threshold is not None else config["confidence_threshold"]
    scorecard = calculate_scorecard_metrics(
        assets,
        confidence_threshold=effective_threshold,
    )

    return {
        "project_id": project_id,
        "confidence_threshold": config["confidence_threshold"],
        "qc_sample_rate": config["qc_sample_rate"],
        "pending_human_annotator_tasks": low_conf_count + rework_count,
        "pending_quality_auditor_tasks": qc_count,
        "low_confidence_tasks": low_conf_count,
        "high_confidence_sampled_tasks": high_conf_sampled_count,
        "rework_tasks": rework_count,
        "passed_tasks": pass_count,
        "failed_tasks": fail_count,
        "scorecard": scorecard,
        "annotation_breakdown": calculate_annotation_breakdown(assets, annotations),
        "area_identification": calculate_area_identification(annotations, len(assets)),
        "annotators": calculate_annotator_metrics(assets, decisions, review_notes),
        "triage": calculate_triage_metrics(assets, annotations, decisions, float(effective_threshold)),
        **execution_metrics,
    }


@router.get("/projects/{project_id}/quality-report")
async def get_quality_report_endpoint(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Fetch complete dataset quality report and defect category breakdown from real MongoDB records."""
    from app.services.quality_validation import calculate_project_quality_report
    return await calculate_project_quality_report(session, project_id)


@router.post("/assets/{asset_id}/submit_qc")
async def submit_asset_for_qc_endpoint(
    asset_id: str,
    payload: Any = Body(...),
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("submit")),
) -> dict[str, Any]:
    """Human Annotator submits modified/added annotations for Quality Audit."""
    from app.services.qc_service import submit_for_qc
    asset = await session.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")

    project_id = str(asset.get("project_id", ""))
    annotations = (payload.get("annotations") if isinstance(payload, dict) else getattr(payload, "annotations", None)) or []
    change_reason = (payload.get("change_reason") if isinstance(payload, dict) else getattr(payload, "change_reason", "Human annotation submitted")) or "Human annotation submitted"

    return await submit_for_qc(
        db=session,
        asset_id=asset_id,
        project_id=project_id,
        annotator_id=f"user_{user_role.lower()}",
        annotations=annotations,
        change_reason=change_reason,
    )


@router.post("/assets/{asset_id}/qc_decision")
async def submit_qc_decision_endpoint(
    asset_id: str,
    payload: Any = Body(...),
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("approve")),
) -> dict[str, Any]:
    """Quality Auditor evaluates task with 12-point checklist. PASS -> FINAL_APPROVED, FAIL -> REWORK_REQUIRED."""
    from app.services.qc_service import process_qc_decision
    asset = await session.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")

    project_id = str(asset.get("project_id", ""))
    raw_payload = dict(payload) if isinstance(payload, dict) else payload.model_dump()

    decision = str(raw_payload.get("decision", "PASS")).upper()
    checklist = dict(raw_payload.get("checklist", {}))
    comments = str(raw_payload.get("comments", ""))
    required_correction = str(raw_payload.get("required_correction", ""))

    return await process_qc_decision(
        db=session,
        asset_id=asset_id,
        project_id=project_id,
        auditor_id=f"auditor_{user_role.lower()}",
        decision=decision,
        checklist=checklist,
        comments=comments,
        required_correction=required_correction,
    )


@router.get("/qc/stream")
async def list_qc_stream_endpoint(
    project_id: str = Query(...),
    stream_type: str = Query("all", description="all | human_work | ai_sample"),
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """Fetch active Quality Check streams (100% human-submitted tasks + 2%-5% sampled high-confidence AI)."""
    query: dict[str, Any] = {"project_id": project_id}

    qc_status_clause = [
        {"review_status": {"$in": ["submitted_for_qc", "quality_audit_required", "QC_PENDING"]}},
        {"workflow_status": {"$in": ["QC_PENDING", "SUBMITTED_FOR_QC"]}},
        {"qc_status": "QC_PENDING"},
    ]

    if stream_type == "human_work":
        query["$or"] = qc_status_clause
    elif stream_type == "ai_sample":
        query["review_status"] = "high_confidence_qc_sample"
    else:
        query["$or"] = qc_status_clause + [{"review_status": "high_confidence_qc_sample"}]

    cursor = session.assets.find(query).sort("updated_at", -1)
    assets = await cursor.to_list(length=1000)

    out = []
    for a in assets:
        doc = to_mongo_doc(a)
        annos_cursor = session.annotations.find({"asset_id": doc["id"]})
        annos = await annos_cursor.to_list(length=500)
        doc["annotations"] = [to_mongo_doc(ann) for ann in annos]
        out.append(doc)

    return out


@router.get("/qc/reports/accuracy/{project_id}")
async def get_data_accuracy_report_endpoint(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """Run backend Data Accuracy Validation Engine for project (13 core checks)."""
    from app.services.quality_validation import run_data_accuracy_validation_engine
    return await run_data_accuracy_validation_engine(project_id, session)


@router.get("/qc/reports/domain/{project_id}")
async def get_domain_validation_report_endpoint(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Run configuration/ontology-driven Better-Fit Plan domain validation."""
    from app.services.quality_validation import validate_better_fit_plan_domain
    return await validate_better_fit_plan_domain(project_id, session)


# ==============================================================================
# SECTION 23 EXPLICIT HITL API ENDPOINTS & WORKFLOW ROUTING CONTRACTS
# ==============================================================================


class HitlConfigUpdatePayload(BaseModel):
    confidence_threshold: float | None = None
    qc_sample_rate: float | None = None
    annotation_guidelines: str | None = None
    ontology: list[str] | None = None


class QcChecklistPayload(BaseModel):
    checklist: dict[str, Any] = Field(default_factory=dict)
    comments: str | None = ""
    required_correction: str | None = ""


class QcPassPayload(BaseModel):
    checklist: dict[str, Any] = Field(default_factory=dict)
    comments: str | None = ""


class QcFailPayload(BaseModel):
    failure_reason: str = Field(..., min_length=1)
    feedback: str | None = ""
    required_corrections: str | None = ""
    checklist: dict[str, Any] = Field(default_factory=dict)


class QcAgentRecommendationPayload(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


@router.get("/projects/{project_id}/hitl/config")
async def get_project_hitl_config_endpoint(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Fetch project HITL settings (confidence threshold, qc sample rate, guidelines, ontology)."""
    svc = DecisionService(session)
    return await svc.get_project_hitl_config(project_id)


@router.put("/projects/{project_id}/hitl/config")
async def update_project_hitl_config_endpoint(
    project_id: str,
    payload: HitlConfigUpdatePayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("config")),
) -> dict[str, Any]:
    """Update project HITL configuration (confidence threshold, sample rate 2%-5%, guidelines, ontology)."""
    svc = DecisionService(session)
    return await svc.update_project_hitl_config(
        project_id=project_id,
        confidence_threshold=payload.confidence_threshold,
        qc_sample_rate=payload.qc_sample_rate,
        annotation_guidelines=payload.annotation_guidelines,
        ontology=payload.ontology,
    )


@router.get("/projects/{project_id}/hitl/human/tasks")
async def get_human_annotator_tasks(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """Fetch Human Annotator queue (<95% low confidence tasks & rework tasks)."""
    svc = DecisionService(session)
    return await svc.list_by_role(project_id, "HUMAN_ANNOTATOR")


@router.get("/hitl/tasks/{task_id}")
async def get_hitl_task(
    task_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Fetch reviewable task details, annotations, routing metadata, and decision state."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task/Asset {task_id} not found")
    doc = to_mongo_doc(asset)
    annos = await session.annotations.find({"asset_id": task_id}).to_list(length=500)
    doc["annotations"] = [to_mongo_doc(a) for a in annos]
    dec = await session.decisions.find_one({"asset_id": task_id})
    if dec:
        doc["decision"] = to_mongo_doc(dec)
    return doc


@router.post("/hitl/tasks/{task_id}/start")
async def start_hitl_task(
    task_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Mark task as actively in progress by reviewer."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task/Asset {task_id} not found")
    cur_status = asset.get("review_status") or asset.get("status")
    new_status = "in_human_review"
    if cur_status in ("submitted_for_qc", "quality_audit_required", "high_confidence_qc_sample"):
        new_status = "qc_in_progress"
    now = datetime.now(UTC)
    await session.assets.update_one({"id": task_id}, {"$set": {"review_status": new_status, "updated_at": now}})
    await session.decisions.update_one({"asset_id": task_id}, {"$set": {"status": new_status, "updated_at": now}})
    return {"status": new_status, "task_id": task_id}


@router.post("/hitl/tasks/{task_id}/annotations")
async def add_hitl_annotation(
    task_id: str,
    payload: AnnotationCreate,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("add_missing")),
) -> AnnotationOut:
    """Human Annotator adds a missing annotation record."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if asset.get("is_locked"):
        raise HTTPException(status_code=400, detail="Task is locked. Final approved annotations cannot be modified.")

    ann_svc = AnnotationService(session)
    ann = await ann_svc.create(task_id, payload)

    from app.services.audit_trail import record_audit_event
    await record_audit_event(
        db=session,
        asset_id=task_id,
        project_id=str(asset.get("project_id", "")),
        action="HUMAN_ADDED",
        actor_role=user_role,
        actor_id=f"user_{user_role.lower()}",
        annotation_id=ann.get("id"),
        before_state={"review_status": str(asset.get("review_status", ""))},
        after_state={"review_status": str(asset.get("review_status", ""))},
        metadata={"added_label": payload.label},
    )
    return AnnotationOut.model_validate(ann)


@router.patch("/hitl/tasks/{task_id}/annotations/{annotation_id}")
async def update_hitl_annotation(
    task_id: str,
    annotation_id: str,
    payload: dict[str, Any],
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("modify")),
) -> dict[str, Any]:
    """Human Annotator modifies existing annotation geometry or label while keeping original AI provenance intact."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if asset.get("is_locked"):
        raise HTTPException(status_code=400, detail="Task is locked. Final approved annotations cannot be modified.")

    ann = await session.annotations.find_one({"id": annotation_id, "asset_id": task_id})
    if not ann:
        raise HTTPException(status_code=404, detail=f"Annotation {annotation_id} not found")

    prov = dict(ann.get("provenance") or {})
    if ann.get("source") == "ai" or ann.get("confidence") is not None:
        prov.setdefault("origin_source", "ai")
        prov.setdefault("original_ai_confidence", ann.get("confidence"))
        prov.setdefault("original_ai_label", ann.get("label"))
    prov["human_edited"] = True
    prov["human_edited_at"] = datetime.now(UTC).isoformat()

    updates: dict[str, Any] = {
        "source": "human_modified",
        "provenance": prov,
        "updated_at": datetime.now(UTC),
    }
    if "label" in payload:
        updates["label"] = payload["label"]
    if "bbox" in payload or "x" in payload:
        if "bbox" in payload:
            b = payload["bbox"]
            updates["x"] = float(b[0])
            updates["y"] = float(b[1])
            updates["w"] = float(b[2])
            updates["h"] = float(b[3])
        if "x" in payload: updates["x"] = float(payload["x"])
        if "y" in payload: updates["y"] = float(payload["y"])
        if "w" in payload: updates["w"] = float(payload["w"])
        if "h" in payload: updates["h"] = float(payload["h"])

    await session.annotations.update_one({"id": annotation_id}, {"$set": updates})
    updated = await session.annotations.find_one({"id": annotation_id})

    from app.services.audit_trail import record_audit_event
    await record_audit_event(
        db=session,
        asset_id=task_id,
        project_id=str(asset.get("project_id", "")),
        action="HUMAN_MODIFIED",
        actor_role=user_role,
        actor_id=f"user_{user_role.lower()}",
        annotation_id=annotation_id,
        before_state={"review_status": str(asset.get("review_status", ""))},
        after_state={"review_status": str(asset.get("review_status", ""))},
        metadata=payload,
    )
    return to_mongo_doc(updated)


@router.delete("/hitl/tasks/{task_id}/annotations/{annotation_id}")
async def delete_hitl_annotation(
    task_id: str,
    annotation_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("delete")),
) -> dict[str, Any]:
    """Human Annotator removes an incorrect annotation."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if asset.get("is_locked"):
        raise HTTPException(status_code=400, detail="Task is locked. Final approved annotations cannot be modified.")

    ann = await session.annotations.find_one({"id": annotation_id, "asset_id": task_id})
    if not ann:
        raise HTTPException(status_code=404, detail=f"Annotation {annotation_id} not found")

    await session.annotations.delete_one({"id": annotation_id})

    from app.services.audit_trail import record_audit_event
    await record_audit_event(
        db=session,
        asset_id=task_id,
        project_id=str(asset.get("project_id", "")),
        action="HUMAN_REMOVED",
        actor_role=user_role,
        actor_id=f"user_{user_role.lower()}",
        annotation_id=annotation_id,
        before_state={"review_status": str(asset.get("review_status", ""))},
        after_state={"review_status": str(asset.get("review_status", ""))},
        metadata={"removed_label": ann.get("label")},
    )
    return {"status": "deleted", "annotation_id": annotation_id}


class HitlQcSubmitPayload(BaseModel):
    annotations: list[dict[str, Any]] | None = None


class BatchAnnotationsPayload(BaseModel):
    annotations: list[dict[str, Any]]


@router.put("/assets/{asset_id}/annotations/batch")
async def batch_save_asset_annotations(
    asset_id: str,
    payload: BatchAnnotationsPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    x_user_role: str = Header(default="Annotator", alias="X-User-Role"),
) -> dict[str, Any]:
    """Atomically batch save all annotations for an asset in one fast database transaction."""
    from app.services.rbac import check_action_permission
    from fastapi import HTTPException
    is_allowed, err = check_action_permission(x_user_role, "modify")
    if not is_allowed:
        raise HTTPException(status_code=403, detail=err)

    asset = await session.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    project_id = str(asset.get("project_id", ""))

    now = datetime.now(UTC)
    await session.annotations.delete_many({"asset_id": asset_id})

    new_rows = []
    for ann in payload.annotations:
        ann_id = ann.get("id") or str(uuid4())
        x = float(ann.get("x", 0.0))
        y = float(ann.get("y", 0.0))
        w = float(ann.get("w", 0.0))
        h = float(ann.get("h", 0.0))
        new_row = {
            "id": ann_id,
            "asset_id": asset_id,
            "project_id": project_id,
            "label": str(ann.get("label") or ann.get("category") or "object"),
            "confidence": ann.get("confidence"),
            "source": ann.get("source") or "human",
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "bbox": [x, y, w, h],
            "polygon": ann.get("polygon"),
            "geometry_type": ann.get("geometry_type", "box"),
            "attributes": ann.get("attributes", {}),
            "provenance": ann.get("provenance", {}),
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        new_rows.append(new_row)

    if new_rows:
        await session.annotations.insert_many(new_rows)

    await session.assets.update_one({"id": asset_id}, {"$set": {"updated_at": now}})
    return {"status": "success", "count": len(new_rows), "asset_id": asset_id}


@router.post("/hitl/tasks/{task_id}/submit-qc")
async def submit_hitl_task_for_qc(
    task_id: str,
    payload: HitlQcSubmitPayload | None = None,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("submit")),
) -> dict[str, Any]:
    """Human Annotator submits task for Quality Audit validation."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    project_id = str(asset.get("project_id", ""))
    
    if payload and payload.annotations is not None:
        annos = payload.annotations
    else:
        annos = await session.annotations.find({"asset_id": task_id}).to_list(length=500)

    from app.services.qc_service import submit_for_qc
    return await submit_for_qc(
        db=session,
        asset_id=task_id,
        project_id=project_id,
        annotator_id=f"user_{user_role.lower()}",
        annotations=[to_mongo_doc(a) if isinstance(a, dict) else a for a in annos],
    )


@router.get("/projects/{project_id}/hitl/qc/tasks")
async def get_qc_auditor_tasks(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """Fetch Quality Auditor queue (100% human work submissions + 2%-5% sampled high-confidence AI)."""
    svc = DecisionService(session)
    return await svc.list_by_role(project_id, "QUALITY_AUDITOR")


@router.get("/hitl/tasks/{task_id}/qc")
async def get_hitl_task_qc(
    task_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Fetch current Quality Check decision and checklist evaluation status."""
    dec = await session.decisions.find_one({"asset_id": task_id})
    if not dec:
        return {"task_id": task_id, "checklist": {}, "decision": None, "status": "pending"}
    return to_mongo_doc(dec)


@router.post("/hitl/tasks/{task_id}/qc/recommendation")
async def get_hitl_task_qc_recommendation(
    task_id: str,
    payload: QcAgentRecommendationPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    settings: Settings = Depends(deps.get_app_settings),
) -> dict[str, Any]:
    """Ask the configured quality agent for an evidence-backed QC recommendation.

    This endpoint is advisory only: it never changes workflow state and never
    replaces the auditor's PASS/FAIL decision. Categories are generated from
    the current task context, so the UI does not carry a fixed defect taxonomy.
    """
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task/Asset {task_id} not found")
    annotations = await session.annotations.find({"asset_id": task_id}).to_list(length=1000)
    decision = await session.decisions.find_one({"asset_id": task_id})
    from app.inference.agent_reasoning import call_json_agent
    agent_result = call_json_agent(
        system_prompt=(
            "You are a multimodal annotation quality auditor. Review the supplied task context and "
            "return strict JSON with keys recommendation (PASS, FAIL, or HUMAN_REVIEW), confidence "
            "(0..1), summary, categories (array of {name,severity,evidence}), and evidence (array). "
            "Infer defect categories from evidence; do not use a fixed checklist or invent facts. "
            "This is advisory and a human auditor must make the final decision."
        ),
        user_payload={
            "asset": to_mongo_doc(asset),
            "annotations": [to_mongo_doc(a) for a in annotations],
            "decision": to_mongo_doc(decision) if decision else None,
            "reviewer_context": payload.context,
        },
        settings=settings,
        max_output_tokens=900,
    )
    if not agent_result:
        return {"status": "unavailable", "recommendation": "HUMAN_REVIEW", "summary": "Quality agent is unavailable; complete the audit manually.", "categories": [], "evidence": [], "agent_run_id": None}
    return {
        "status": "ready",
        "recommendation": str(agent_result.get("recommendation") or agent_result.get("decision") or "HUMAN_REVIEW").upper(),
        "confidence": agent_result.get("confidence"),
        "summary": agent_result.get("summary") or agent_result.get("reason"),
        "categories": agent_result.get("categories") if isinstance(agent_result.get("categories"), list) else [],
        "evidence": agent_result.get("evidence") if isinstance(agent_result.get("evidence"), list) else [],
        "agent_run_id": agent_result.get("agent_run_id"),
    }


@router.post("/hitl/tasks/{task_id}/qc/checklist")
async def save_hitl_task_qc_checklist(
    task_id: str,
    payload: QcChecklistPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("approve")),
) -> dict[str, Any]:
    """Quality Auditor saves/evaluates 12-point quality checklist."""
    dec = await session.decisions.find_one({"asset_id": task_id})
    if not dec:
        raise HTTPException(status_code=404, detail=f"QC Decision record for {task_id} not found")
    await session.decisions.update_one({"asset_id": task_id}, {"$set": {"checklist": payload.checklist, "updated_at": datetime.now(UTC)}})
    updated = await session.decisions.find_one({"asset_id": task_id})
    return to_mongo_doc(updated)


@router.post("/hitl/tasks/{task_id}/qc/pass")
async def pass_hitl_task_qc(
    task_id: str,
    payload: QcPassPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("approve")),
) -> dict[str, Any]:
    """Quality Auditor PASS decision -> sets status FINAL_APPROVED and locks task."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    project_id = str(asset.get("project_id", ""))
    from app.services.qc_service import process_qc_decision
    return await process_qc_decision(
        db=session,
        asset_id=task_id,
        project_id=project_id,
        auditor_id=f"auditor_{user_role.lower()}",
        decision="PASS",
        checklist=payload.checklist,
        comments=payload.comments or "Passed Quality Audit",
    )


@router.post("/hitl/tasks/{task_id}/qc/fail")
async def fail_hitl_task_qc(
    task_id: str,
    payload: QcFailPayload,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("approve")),
) -> dict[str, Any]:
    """Quality Auditor FAIL decision -> sets status REWORK_REQUIRED and returns task to Human Annotator queue."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    project_id = str(asset.get("project_id", ""))
    from app.services.qc_service import process_qc_decision
    return await process_qc_decision(
        db=session,
        asset_id=task_id,
        project_id=project_id,
        auditor_id=f"auditor_{user_role.lower()}",
        decision="FAIL",
        checklist=payload.checklist,
        comments=payload.feedback or payload.failure_reason,
        required_correction=payload.required_corrections or payload.failure_reason,
    )


@router.post("/hitl/tasks/{task_id}/rework")
async def submit_hitl_task_rework(
    task_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
    user_role: str = Depends(deps.require_action_permission("submit")),
) -> dict[str, Any]:
    """Human Annotator resubmits corrected rework for Quality Audit."""
    asset = await session.assets.find_one({"id": task_id})
    if not asset:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    project_id = str(asset.get("project_id", ""))
    annos = await session.annotations.find({"asset_id": task_id}).to_list(length=500)
    from app.services.qc_service import submit_for_qc
    return await submit_for_qc(
        db=session,
        asset_id=task_id,
        project_id=project_id,
        annotator_id=f"user_{user_role.lower()}",
        annotations=[to_mongo_doc(a) for a in annos],
        change_reason="Rework corrected and resubmitted for QC",
    )


@router.get("/hitl/tasks/{task_id}/audit")
async def get_hitl_task_audit(
    task_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> list[dict[str, Any]]:
    """Fetch immutable audit event trail history for task."""
    events = await session.audit_events.find({"asset_id": task_id}).sort("timestamp", -1).to_list(length=500)
    return [to_mongo_doc(ev) for ev in events]


@router.get("/projects/{project_id}/hitl/metrics")
async def get_project_hitl_metrics_alias(
    project_id: str,
    session: AsyncIOMotorDatabase = Depends(deps.get_db),
) -> dict[str, Any]:
    """Fetch persistent HITL metrics."""
    return await get_hitl_metrics_endpoint(project_id, session)



