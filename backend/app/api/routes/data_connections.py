"""FastAPI router for Data Connections API."""

from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, Query, Response, status

from app.config import Settings
from app.api import deps
from app.schemas.data_connection import (
    DataConnectionCreate,
    DataConnectionImportOut,
    DataConnectionImportRequest,
    DataConnectionObjectsOut,
    DataConnectionOut,
    DataConnectionValidateOut,
)
from app.services.data_connections import DataConnectionService
from app.storage.files import FileStorage

router = APIRouter(prefix="/data-connections", tags=["data-connections"])


@router.post("", response_model=DataConnectionOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=DataConnectionOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_data_connection(
    payload: DataConnectionCreate,
    db: Annotated[Any, Depends(deps.get_db)],
) -> DataConnectionOut:
    svc = DataConnectionService(db)
    res = await svc.create(payload)
    return DataConnectionOut.model_validate(res)


@router.get("", response_model=list[DataConnectionOut])
@router.get("/", response_model=list[DataConnectionOut], include_in_schema=False)
async def list_data_connections(
    db: Annotated[Any, Depends(deps.get_db)],
) -> list[DataConnectionOut]:
    svc = DataConnectionService(db)
    res = await svc.list_connections()
    return [DataConnectionOut.model_validate(c) for c in res]


@router.get("/{connection_id}", response_model=DataConnectionOut)
async def get_data_connection(
    connection_id: str,
    db: Annotated[Any, Depends(deps.get_db)],
) -> DataConnectionOut:
    svc = DataConnectionService(db)
    res = await svc.get(connection_id)
    return DataConnectionOut.model_validate(res)


@router.post("/{connection_id}/validate", response_model=DataConnectionValidateOut)
async def validate_data_connection(
    connection_id: str,
    db: Annotated[Any, Depends(deps.get_db)],
) -> DataConnectionValidateOut:
    svc = DataConnectionService(db)
    res = await svc.validate(connection_id)
    return DataConnectionValidateOut.model_validate(res)


@router.get("/{connection_id}/objects", response_model=DataConnectionObjectsOut)
async def list_data_connection_objects(
    connection_id: str,
    db: Annotated[Any, Depends(deps.get_db)],
    prefix: str | None = Query(default=None),
    page_size: int = Query(default=50, ge=1, le=500),
    continuation_token: str | None = Query(default=None),
    next_page_token: str | None = Query(default=None),
) -> DataConnectionObjectsOut:
    token = continuation_token or next_page_token
    svc = DataConnectionService(db)
    res = await svc.list_objects(
        connection_id,
        prefix=prefix,
        page_size=page_size,
        continuation_token=token,
    )
    return DataConnectionObjectsOut.model_validate(res)


@router.post("/{connection_id}/import", response_model=DataConnectionImportOut)
async def import_data_connection_objects(
    connection_id: str,
    payload: DataConnectionImportRequest,
    db: Annotated[Any, Depends(deps.get_db)],
    settings: Annotated[Settings, Depends(deps.get_app_settings)],
    storage: Annotated[FileStorage, Depends(deps.get_storage)],
) -> DataConnectionImportOut:
    svc = DataConnectionService(db, settings, storage)
    res = await svc.import_objects(connection_id, payload)
    return DataConnectionImportOut.model_validate(res)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_data_connection(
    connection_id: str,
    db: Annotated[Any, Depends(deps.get_db)],
) -> Response:
    svc = DataConnectionService(db)
    await svc.delete(connection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
