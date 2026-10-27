"""Dataset MCP server: groups asset metadata / ontology / workflow resources."""

from __future__ import annotations

from typing import Any

from app.db.models import MongoSession

from app.mcp.contracts import MCPResult
from app.mcp.tools import dataset
from app.mcp.resources import workflow as workflow_resource


class DatasetMCPServer:
    def __init__(self, session: MongoSession) -> None:
        self.session = session

    async def get_asset_metadata(self, asset_id: str) -> MCPResult[dict[str, Any]]:
        return await dataset.get_asset_metadata(self.session, asset_id)

    async def get_asset_annotation_summary(self, asset_id: str) -> MCPResult[dict[str, Any]]:
        return await dataset.get_asset_annotation_summary(self.session, asset_id)

    async def get_project_ontology(self, project_id: str) -> MCPResult[dict[str, Any]]:
        return await dataset.get_project_ontology(self.session, project_id)

    async def get_workflow_state(self, batch_id: str) -> MCPResult[dict[str, Any]]:
        return await workflow_resource.read_workflow_state(self.session, batch_id)
