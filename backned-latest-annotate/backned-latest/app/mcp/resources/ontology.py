"""Dataset MCP resource: ``project://{project_id}/ontology``."""

from __future__ import annotations

from typing import Any

from app.db.models import MongoSession
from app.mcp.tools.dataset import get_project_ontology


async def read_project_ontology(session: MongoSession, project_id: str) -> Any:
    """Resolve ``project://{project_id}/ontology``."""
    return await get_project_ontology(session, project_id)
