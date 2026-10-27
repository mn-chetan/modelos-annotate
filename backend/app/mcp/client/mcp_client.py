"""MCP client used by the Vision Orchestrator (``app.jobs.worker``).

Aggregates the three in-process MCP servers (vision / annotation / dataset)
behind one object so the orchestrator only needs a single dependency.
This is the sole integration seam between the existing worker and the new
MCP capability layer — see ``app/jobs/worker.py`` for the call sites.
"""

from __future__ import annotations

from app.db.models import MongoSession
from app.inference.registry import ModelRegistry
from app.mcp.server.annotation_server import AnnotationMCPServer
from app.mcp.server.dataset_server import DatasetMCPServer
from app.mcp.server.vision_server import VisionMCPServer
from app.storage.files import FileStorage


class MCPClient:
    """Single entry point exposing vision/annotation/dataset MCP capabilities.

    ``vision`` only needs the model registry (reused across calls).
    ``annotation``/``dataset`` need a per-request DB session, so they are
    (re)bound via :meth:`for_session` — cheap, since no new connections or
    model loads happen here.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self.vision = VisionMCPServer(registry)
        self._registry = registry
        self.annotation: AnnotationMCPServer | None = None
        self.dataset: DatasetMCPServer | None = None

    def for_session(self, session: MongoSession, storage: FileStorage) -> "MCPClient":
        """Bind annotation/dataset servers to the caller's session for one unit of work."""
        self.annotation = AnnotationMCPServer(session, storage)
        self.dataset = DatasetMCPServer(session)
        return self
