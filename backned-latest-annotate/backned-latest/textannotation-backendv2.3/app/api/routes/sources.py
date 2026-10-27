from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.exceptions import AppError
from app.schemas.source import SourceDocument

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceDocument, name="get_source")
async def get_source(request: Request, source_id: str):
    source_repository = request.app.state.source_repository
    source = await source_repository.find_by_source_id(source_id)
    if source is None:
        raise AppError("SOURCE_NOT_FOUND", "Source not found.", status_code=404)
    return SourceDocument.model_validate(source)