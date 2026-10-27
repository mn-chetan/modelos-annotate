"""LangGraph-based agents.

Three graphs, each wrapping an existing agentic capability in an explicit,
inspectable control-flow graph instead of a single ad-hoc LLM call:

- ``vision_planning_graph``: decides which vision models/strategy to run
  for one asset (used by ``app.inference.routing``).
- ``mcp_tool_agent``: a ReAct-style loop that autonomously chooses which
  MCP tool (detect / segment / verify) to call next for one asset.
- ``intake_graph``: drives project intake -> plan generation end to end.

``langgraph``/``langchain-core`` are optional at import time: importing this
package never raises, so the rest of the app keeps working before the
dependency is installed. Only calling into a graph raises
``LangGraphUnavailable`` if the packages are missing.
"""

from __future__ import annotations


class LangGraphUnavailable(RuntimeError):
    """Raised when a graph is invoked but langgraph/langchain-core is not installed."""


def _require_langgraph() -> None:
    try:
        import langgraph  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only pre-install
        raise LangGraphUnavailable(
            "langgraph is not installed. Add it via `pip install -r requirements.txt` "
            "(langgraph>=0.2.0 is listed in backend/requirements.txt)."
        ) from exc


__all__ = ["LangGraphUnavailable"]
