"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import Header, Request
from app.db.firebase import AsyncIOMotorDatabase

from app.config import Settings
from app.db.models import get_database
from app.storage.files import FileStorage
from app.logging import get_logger

logger = get_logger(__name__)


async def get_db() -> AsyncIterator[AsyncIOMotorDatabase]:
    db = get_database()
    yield db


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


get_settings = get_app_settings


def get_storage(request: Request) -> FileStorage:
    return request.app.state.storage


def get_current_user_role(request: Request, x_user_role: str | None = Header(None, alias="X-User-Role")) -> str:
    user = getattr(request.state, "user", None)
    if user:
        return str(user.get("role") or "HUMAN_ANNOTATOR")
    return x_user_role or "HUMAN_ANNOTATOR"


def require_action_permission(action: str):
    from fastapi import Depends, HTTPException
    from app.services.rbac import check_action_permission

    async def _permission_dependency(role: str = Depends(get_current_user_role)):
        allowed, msg = check_action_permission(role, action)
        if not allowed:
            raise HTTPException(status_code=403, detail=msg or f"Permission denied for action '{action}'")
        return role

    return _permission_dependency
