"""Dataset MCP resource: ``asset://{asset_id}`` and ``asset://{asset_id}/metadata``."""

from __future__ import annotations

from typing import Any

from app.db.models import MongoSession
from app.mcp.tools.dataset import get_asset_metadata


async def read_asset(session: MongoSession, asset_id: str) -> Any:
    """Resolve ``asset://{asset_id}`` and ``asset://{asset_id}/metadata``."""
    return await get_asset_metadata(session, asset_id)
