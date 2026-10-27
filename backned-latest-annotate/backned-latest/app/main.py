"""FastAPI application entry point - updated for HITL workflow endpoints."""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agent.service import create_agent_client
from app.api.routes import router
from app.config import Settings, get_settings
from app.db.firebase import DatabaseUnavailableError
from app.db.models import close_database, init_database
from app.errors import AppError, DuplicateProjectError
from app.inference.detector import create_detector_from_settings, set_detector
from app.inference.registry import get_runtime, set_runtime
from app.jobs.worker import BatchWorker, set_worker
from app.logging import configure_logging, get_logger
from app.storage.files import FileStorage
from app.storage.cloud import CloudStorageService
from app.context import set_current_base_prefix

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    startup_start = time.perf_counter()
    settings: Settings = app.state.settings
    configure_logging(settings.log_level, settings.log_format)
    logger.info("server_starting", host=settings.host, port=settings.port, reload=bool(settings.debug))
    settings.ensure_runtime_dirs()

    logger.info(
        "app_startup",
        yolo26_model_id=settings.yolo26_model_id,
        device=settings.device,
        yolo26_enabled=settings.yolo26_enabled,
        dino_enabled=settings.dino_enabled,
        florence_enabled=settings.florence_enabled,
        sam2_enabled=settings.sam2_enabled,
        agent_enabled=settings.agent_enabled,
        agent_provider="azure_openai" if getattr(settings, "is_azure_agent", False) else "vertex",
        agent_model=settings.effective_agent_model,
        azure_endpoint=settings.azure_openai_endpoint if getattr(settings, "is_azure_agent", False) else None,
        azure_deployment=settings.azure_openai_deployment if getattr(settings, "is_azure_agent", False) else None,
        vertex_agent_enabled=not getattr(settings, "is_azure_agent", False) and settings.agent_enabled,
        vertex_project=settings.google_cloud_project,
        vertex_location=settings.vertex_location,
        vertex_model=settings.vertex_agent_model,
        vertex_auth="ADC" if not getattr(settings, "is_azure_agent", False) else "API_KEY",
        gemini_api_key_configured=bool(settings.effective_gemini_api_key),
        database_provider=settings.database_provider,
        storage_dir=str(settings.storage_dir),
    )

    db_start = time.perf_counter()
    db = await init_database(settings=settings)
    db_ms = int((time.perf_counter() - db_start) * 1000)
    app.state.db = db
    app.state.session_factory = lambda: db

    logger.info(
        "database_diagnostics",
        database_provider=getattr(db, "provider", "firebase"),
        database_project=getattr(db, "project_id", ""),
        database_database_name=getattr(db, "database_id", "engenii-annotate-native"),
        database_connection_status=getattr(db, "connection_status", "unhealthy"),
        database_persistence_mode=getattr(db, "persistence_mode", "unhealthy"),
        database_init_ms=db_ms,
    )

    if not getattr(db, "is_healthy", False):
        database_error = getattr(db, "last_error", "unknown error")
        if getattr(db, "authentication_required", False):
            database_error = (
                "Google ADC authentication requires reauthentication. "
                "Run: gcloud auth application-default login"
            )
        logger.error(
            "startup_database_unhealthy",
            provider=getattr(db, "provider", "firebase"),
            project=getattr(db, "project_id", ""),
            database=getattr(db, "database_id", "engenii-annotate-native"),
            error=database_error,
        )
        raise RuntimeError(
            f"Startup failed: database {getattr(db, 'project_id', '')}/{getattr(db, 'database_id', '')} "
            f"connection is unhealthy: {database_error}"
        )

    from app.db.seed import seed_database_if_empty
    await seed_database_if_empty(db, settings=settings)

    cloud_storage = CloudStorageService(
        storage_provider=settings.storage_provider,
        gcs_bucket_name=settings.gcs_bucket_name,
        gcs_project_id=settings.gcs_project_id,
        gcs_prefix=settings.gcs_prefix,
        aws_s3_bucket=settings.aws_s3_bucket,
        aws_region=settings.aws_region,
        aws_endpoint_url=settings.aws_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    storage = FileStorage(settings.storage_dir, cloud_storage=cloud_storage)
    app.state.storage = storage
    app.state.cloud_storage = cloud_storage
    if settings.storage_provider == "gcs" and settings.gcs_bucket_name:
        try:
            cloud_storage.validate_bucket(provider="gcs", bucket=settings.gcs_bucket_name)
            app.state.cloud_storage_status = "connected"
            logger.info("gcs_startup_validation_succeeded", bucket=settings.gcs_bucket_name)
        except Exception as exc:
            app.state.cloud_storage_status = "unavailable"
            logger.error("gcs_startup_validation_failed", error=str(exc))
    else:
        app.state.cloud_storage_status = "not_configured"

    detector = create_detector_from_settings(settings)
    runtime = get_runtime()
    model_start = time.perf_counter()
    if not settings.skip_model_load:
        runtime.load_eager()
    eager_model_load_ms = int((time.perf_counter() - model_start) * 1000)
    startup_model_status = {
        status.key: status.availability for status in runtime.model_statuses()
        if status.key in {
            "yolo26", "faster_rcnn", "dino", "florence", "sam2", "clip"
        }
    }
    logger.info(
        "model_startup_initialization_complete",
        model_status=startup_model_status,
        duration_ms=eager_model_load_ms,
        skipped=bool(settings.skip_model_load),
    )
    set_detector(detector)
    app.state.detector = detector
    app.state.runtime = runtime

    agent_client = create_agent_client(settings)
    if settings.agent_enabled:
        try:
            agent_client.probe()
            setattr(agent_client, "available", True)
            setattr(agent_client, "reason", None)
            from app.inference import agent_reasoning
            agent_reasoning.vertex_agent_available = True
        except Exception as exc:  # noqa: BLE001
            setattr(agent_client, "available", False)
            err_str = str(exc).lower()
            if (
                "credentials" in err_str
                or "auth" in err_str
                or "unauthenticated" in err_str
                or "permission" in err_str
                or "reauthentication" in err_str
                or "expired" in err_str
                or "default credentials" in err_str
            ):
                reason = "authentication_required"
            elif "not configured" in err_str or "missing" in err_str or "project" in err_str:
                reason = "configuration_error"
            else:
                reason = "model_unavailable"
            setattr(agent_client, "reason", reason)

            from app.inference import agent_reasoning
            agent_reasoning.vertex_agent_available = False

            logger.error(
                "agent_unavailable",
                model=settings.vertex_agent_model,
                project=settings.google_cloud_project,
                location=settings.vertex_location,
                auth="ADC",
                reason=reason,
                error=str(exc),
            )
    app.state.agent_client = agent_client

    worker = BatchWorker(
        settings=settings,
        storage=storage,
        detector=detector,
        runtime=runtime,
        db=db,
    )
    await worker.start()
    set_worker(worker)
    app.state.worker = worker

    degraded = []
    if not getattr(agent_client, "available", True):
        degraded.append("vertex_agent")

    logger.info(
        "application_started",
        degraded_capabilities=degraded
    )

    statuses = {s.key: s.availability for s in runtime.model_statuses()}
    logger.info("app_ready", model_status=statuses, device=detector.device)
    logger.info("server_started", host=settings.host, port=settings.port)

    total_startup_ms = int((time.perf_counter() - startup_start) * 1000)
    loaded_models = [s.key for s in runtime.model_statuses() if s.loaded]
    lazy_models = [s.key for s in runtime.model_statuses() if not s.loaded and s.availability != "disabled"]
    failed_models = [s.key for s in runtime.model_statuses() if s.availability == "unavailable"]

    logger.info(
        "startup_complete",
        total_ms=total_startup_ms,
        database_ms=db_ms,
        eager_model_load_ms=eager_model_load_ms,
        loaded_models=loaded_models,
        lazy_models=lazy_models,
        failed_optional_models=failed_models,
    )
    try:
        yield
    finally:
        logger.info(
            "shutdown_requested",
            shutdown_reason="lifespan_exit",
            active_annotation_tasks=getattr(worker, "active_workers", 0),
        )
        logger.info("resource_shutdown_started")
        await worker.stop()
        set_worker(None)
        from app.recon.service import shutdown_recon_tasks
        await shutdown_recon_tasks()
        set_detector(None)
        set_runtime(None)
        await close_database()
        logger.info("resource_shutdown_complete")
        logger.info("server_shutdown_complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Ingenii Annotate API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Any]) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            path = request.url.path
            set_current_base_prefix("/app1" if path.startswith("/app1") else "")
            response: Response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-Id"] = request_id
        if request.url.path != "/api/v1/health":
            logger.info(
                "request_complete",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    @app.exception_handler(DuplicateProjectError)
    async def duplicate_project_handler(
        request: Request, exc: DuplicateProjectError
    ) -> JSONResponse:
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        logger.warning(
            "project_creation_duplicate",
            existing_project_id=exc.existing_project_id,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=409,
            content={
                "code": "duplicate_project",
                "message": exc.message,
                "error": exc.message,
                "existing_project_id": exc.existing_project_id,
                "details": {"existing_project_id": exc.existing_project_id},
                "request_id": request_id,
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        logger.warning(
            "app_error",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.message,
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
                "request_id": request_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        return JSONResponse(
            status_code=422,
            content={
                "error": "Request validation failed",
                "code": "validation_error",
                "details": {"errors": exc.errors()},
                "request_id": request_id,
            },
        )

    @app.exception_handler(DatabaseUnavailableError)
    async def database_unavailable_handler(
        request: Request, exc: DatabaseUnavailableError
    ) -> JSONResponse:
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database is temporarily unavailable.",
                "error": "Database is temporarily unavailable.",
                "code": "database_unavailable",
                "details": {"reason": str(exc)},
                "request_id": request_id,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": str(exc.detail),
                "error": str(exc.detail),
                "code": "http_error",
                "details": {},
                "request_id": request_id,
            },
        )

    app.include_router(router)
    app.include_router(router, prefix="/app1")

    # Static frontend serving (for single container deployment e.g. Cloud Run)
    import os
    from pathlib import Path
    from fastapi.responses import RedirectResponse

    frontend_dir = os.environ.get("STATIC_DIR") or os.environ.get("FRONTEND_DIST_DIR")
    if not frontend_dir:
        candidates = [
            Path("/app/frontend_dist"),
            Path(__file__).resolve().parent.parent / "frontend_dist",
            Path(__file__).resolve().parent.parent.parent.parent / "Annotate-ui" / "Annotate-ui" / "dist",
        ]
        for candidate in candidates:
            if candidate.is_dir() and (candidate / "index.html").is_file():
                frontend_dir = str(candidate)
                break

    if frontend_dir and Path(frontend_dir).is_dir() and (Path(frontend_dir) / "index.html").is_file():
        dist_path = Path(frontend_dir).resolve()
        index_file = dist_path / "index.html"
        assets_dir = dist_path / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")
            app.mount("/app1/assets", StaticFiles(directory=str(assets_dir)), name="app1-frontend-assets")

        @app.get("/app1")
        @app.get("/app1/")
        @app.get("/")
        async def root_index() -> Response:
            if index_file.is_file():
                return FileResponse(index_file)
            return JSONResponse(status_code=503, content={"error": "Frontend UI bundle index.html not found"})

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> Response:
            if full_path.startswith(("api", "docs", "openapi.json", "redoc", "app1/api", "app1/docs", "app1/openapi.json", "app1/redoc")):
                raise StarletteHTTPException(status_code=404, detail="Not Found")
            clean_path = full_path
            if clean_path.startswith("app1/"):
                clean_path = clean_path[len("app1/"):]
            target = dist_path / clean_path
            if target.is_file():
                return FileResponse(target)
            if index_file.is_file():
                return FileResponse(index_file)
            raise StarletteHTTPException(status_code=404, detail="Not Found")
    else:
        @app.get("/")
        async def root() -> dict[str, str]:
            return {
                "service": "ingenii-annotate",
                "docs": "/docs",
                "health": "/api/v1/health",
            }

    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_dirs=["app"] if settings.debug else None,
        log_config=None,
    )


if __name__ == "__main__":
    main()
