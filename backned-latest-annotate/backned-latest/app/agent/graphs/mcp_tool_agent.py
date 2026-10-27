"""LangGraph MCP tool-calling agent.

A ReAct-style graph that autonomously decides which MCP vision tool to call
next for one asset (``detect_objects`` / ``detect_custom_objects`` /
``segment_objects`` / ``verify_result``), inspects the result, and either
calls another tool or finishes - instead of a fixed, hand-coded call order.

This is additive: ``app.jobs.worker.BatchWorker`` keeps its existing
deterministic per-model execution loop. This agent is exposed as a
standalone entry point (``run_mcp_tool_agent``) that callers can opt into.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from app.agent.graphs import _require_langgraph
from app.mcp.client.mcp_client import MCPClient

_MAX_ITERATIONS_DEFAULT = 6

_TOOL_DESCRIPTIONS = (
    "- detect_objects: closed-set detection (yolo26 / faster_rcnn). "
    "args: {model: 'yolo26'|'faster_rcnn', labels: [str]|null}\n"
    "- detect_custom_objects: open-vocabulary detection (dino). "
    "args: {prompts: [str]|null}\n"
    "- segment_objects: SAM2 masks for already-found detections. "
    "args: {} (uses all detections found so far)\n"
    "- verify_result: run review-decision verification on what has been found so far. "
    "args: {}\n"
    "- finish: stop, nothing further is needed. args: {}"
)

_SYSTEM_PROMPT = (
    "You are the Vision Tool-Calling Agent. You have access to these MCP tools:\n"
    f"{_TOOL_DESCRIPTIONS}\n\n"
    "Given the ontology labels, the tool call history, and their results so far, "
    "decide the single next action. Typical order is: detect (closed-set and/or "
    "open-vocabulary) -> segment (only if segmentation is requested) -> verify -> finish. "
    "Do not repeat a tool call that already produced a usable, non-empty result unless "
    "a prior detection call failed or returned nothing and another detector is available.\n"
    "Return ONLY JSON: {\"action\": \"<tool name or finish>\", \"args\": {...}, \"reason\": \"...\"}"
)


class ToolAgentState(TypedDict, total=False):
    asset_id: str
    image_path: str
    ontology_labels: list[str]
    segmentation_required: bool
    settings: Any
    mcp: MCPClient
    history: list[dict[str, Any]]
    detections: list[Any]
    masks: list[Any]
    review_decision: Any
    iterations: int
    max_iterations: int
    done: bool


def _agent_node(state: ToolAgentState) -> ToolAgentState:
    from app.inference.agent_reasoning import call_json_agent

    payload = {
        "ontology_labels": state.get("ontology_labels", []),
        "segmentation_required": state.get("segmentation_required", False),
        "history": state.get("history", []),
        "detections_found": len(state.get("detections") or []),
        "masks_found": len(state.get("masks") or []),
    }
    decision = call_json_agent(
        system_prompt=_SYSTEM_PROMPT,
        user_payload=payload,
        settings=state.get("settings"),
    ) or {"action": "finish", "args": {}, "reason": "planning agent unavailable"}

    action = str(decision.get("action") or "finish")
    args = decision.get("args") or {}
    reason = decision.get("reason") or ""

    iterations = state.get("iterations", 0) + 1
    if iterations >= state.get("max_iterations", _MAX_ITERATIONS_DEFAULT):
        action = "finish"

    history = list(state.get("history") or [])
    history.append({"action": action, "args": args, "reason": reason})
    return {"history": history, "iterations": iterations, "done": action == "finish"}


def _tool_node(state: ToolAgentState) -> ToolAgentState:
    last = (state.get("history") or [])[-1]
    action = last["action"]
    args = last.get("args") or {}
    mcp = state["mcp"]
    image_path = Path(state["image_path"])
    asset_id = state["asset_id"]

    if action == "detect_objects":
        outcome = mcp.vision.detect_objects(
            image_path,
            asset_id=asset_id,
            model=args.get("model", "yolo26"),
            labels=args.get("labels") or state.get("ontology_labels"),
        )
        found = outcome.data if outcome.success else []
        detections = list(state.get("detections") or []) + list(found or [])
        return {"detections": detections}

    if action == "detect_custom_objects":
        outcome = mcp.vision.detect_custom_objects(
            image_path,
            asset_id=asset_id,
            prompts=args.get("prompts") or state.get("ontology_labels") or [],
        )
        found = outcome.data if outcome.success else []
        detections = list(state.get("detections") or []) + list(found or [])
        return {"detections": detections}

    if action == "segment_objects":
        detections = state.get("detections") or []
        if not detections:
            return {}
        outcome = mcp.vision.segment_objects(image_path, asset_id=asset_id, detections=detections)
        masks = outcome.data if outcome.success else []
        return {"masks": list(masks or [])}

    if action == "verify_result":
        from app.mcp.tools.verification import verify_result

        verify_outcome = verify_result(
            asset_id=asset_id,
            merged=state.get("detections") or [],
            all_detections=state.get("detections") or [],
            scene_evidence=None,
            completed_models=[h["action"] for h in (state.get("history") or [])],
        )
        return {"review_decision": verify_outcome.data if verify_outcome.success else None}

    return {}


def _route(state: ToolAgentState) -> str:
    if state.get("done"):
        return "end"
    last = (state.get("history") or [])[-1]
    return "end" if last["action"] == "finish" else "tool"


def _build_graph() -> Any:
    _require_langgraph()
    from langgraph.graph import END, StateGraph

    graph = StateGraph(ToolAgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tool", _tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _route, {"tool": "tool", "end": END})
    graph.add_edge("tool", "agent")
    return graph.compile()


_compiled_graph: Any = None


def run_mcp_tool_agent(
    *,
    mcp: MCPClient,
    image_path: str | Path,
    asset_id: str,
    ontology_labels: list[str],
    segmentation_required: bool = False,
    settings: Any = None,
    max_iterations: int = _MAX_ITERATIONS_DEFAULT,
) -> dict[str, Any]:
    """Run the autonomous MCP tool-calling agent for one asset.

    Returns a dict with ``detections``, ``masks``, ``review_decision``, and
    ``history`` (the ordered trace of tool calls, for auditability).
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()

    final_state: ToolAgentState = _compiled_graph.invoke(
        {
            "asset_id": asset_id,
            "image_path": str(image_path),
            "ontology_labels": ontology_labels,
            "segmentation_required": segmentation_required,
            "settings": settings,
            "mcp": mcp,
            "history": [],
            "detections": [],
            "masks": [],
            "iterations": 0,
            "max_iterations": max_iterations,
        }
    )
    return {
        "detections": final_state.get("detections") or [],
        "masks": final_state.get("masks") or [],
        "review_decision": final_state.get("review_decision"),
        "history": final_state.get("history") or [],
    }


__all__ = ["run_mcp_tool_agent"]
