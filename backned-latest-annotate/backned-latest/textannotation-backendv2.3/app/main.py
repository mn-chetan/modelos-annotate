from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi

from app.api.routes.annotations import router as annotations_router
from app.api.routes.sources import router as sources_router
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.core.logging import configure_logging
from app.database.mongodb import MongoDB
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.source_repository import SourceRepository
from app.services.drug_matching_service import DrugMatchingService
from app.services.gemini_service import GeminiService
from app.services.relation_extraction_service import RelationExtractionService
from app.services.ocr_service import TesseractOCRService
from app.services.sentiment_service import SentimentService
from app.services.text_classification_service import TextClassificationService
from app.services.text_extraction_service import TextExtractionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging()
    mongo = MongoDB(settings.mongodb_uri, settings.mongodb_database)
    database = await mongo.connect()
    await mongo.init_indexes(database)

    app.state.settings = settings
    app.state.mongo = mongo
    app.state.database = database
    app.state.source_repository = SourceRepository(database["sources"])
    app.state.analysis_repository = AnalysisRepository(database["analyses"])
    app.state.ocr_service = TesseractOCRService()
    app.state.gemini_service = GeminiService(model="gemini-2.5-flash")
    app.state.text_extraction_service = TextExtractionService(app.state.ocr_service)
    app.state.drug_matching_service = DrugMatchingService(app.state.gemini_service)
    app.state.sentiment_service = SentimentService(app.state.gemini_service)
    app.state.text_classification_service = TextClassificationService(app.state.gemini_service)
    app.state.relation_extraction_service = RelationExtractionService(app.state.gemini_service)

    yield

    await mongo.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Text Annotation Backend", version=get_settings().app_version, lifespan=lifespan)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(annotations_router)
    app.include_router(sources_router)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )

        def normalize_file_schema(value):
            if isinstance(value, dict):
                if value.get("contentMediaType") == "application/octet-stream":
                    return {"type": "string", "format": "binary"}

                return {
                    key: normalize_file_schema(item)
                    for key, item in value.items()
                }

            if isinstance(value, list):
                return [normalize_file_schema(item) for item in value]

            return value

        app.openapi_schema = normalize_file_schema(openapi_schema)
        return app.openapi_schema

    app.openapi = custom_openapi

    @app.get("/health")
    async def health(request: Request):
        mongo = request.app.state.mongo
        try:
            await mongo.ping()
        except Exception as exc:
            raise AppError("MONGODB_FAILURE", "MongoDB is not reachable.", status_code=503) from exc
        return {"status": "healthy", "mongodb": "connected"}

    return app


app = create_app()
