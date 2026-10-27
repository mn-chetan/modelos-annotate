"""Dataset MCP resource: ``workflow://{batch_id}/state``.

Read-only view of an in-flight/completed batch, sourced from the existing
``BatchRow``/``JobItemRow`` tables — no new persistence introduced.
"""

from __future__ import annotations

from typing import Any

from app.db.models import BatchRow, MongoSession, get_database, to_mongo_docs
from app.errors import NotFoundError
from app.mcp.instrumentation import mcp_tool


@mcp_tool("dataset_workflow_state")
async def read_workflow_state(session: MongoSession, batch_id: str) -> dict[str, Any]:
    """Resolve ``workflow://{batch_id}/state``."""
    batch = await session.get(BatchRow, batch_id)
    if batch is None:
        raise NotFoundError(f"Batch {batch_id} not found", details={"batch_id": batch_id})

    db = get_database()
    raw_items = await db.job_items.find({"batch_id": batch_id}).to_list(length=None)
    items = to_mongo_docs(raw_items)
    return {
        "batch_id": batch.id,
        "project_id": batch.project_id,
        "status": batch.status,
        "total": batch.total,
        "completed": batch.completed,
        "failed": batch.failed,
        "running": batch.running,
        "workflow": list(batch.workflow or []),
        "items": [
            {
                "id": item.id,
                "asset_id": item.asset_id,
                "status": item.status,
                "attempt": item.attempt,
                "detection_count": item.detection_count,
                "duration_ms": item.duration_ms,
                "error_message": item.error_message,
            }
            for item in items
        ],
    }
