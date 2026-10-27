"""Dataset MCP resource: ``asset://{asset_id}/annotations``."""

from __future__ import annotations

from typing import Any

from app.db.models import MongoSession
from app.mcp.tools.annotation import get_annotations


async def read_asset_annotations(session: MongoSession, asset_id: str) -> Any:
    """Resolve ``asset://{asset_id}/annotations``."""
    return await get_annotations(session, asset_id)
