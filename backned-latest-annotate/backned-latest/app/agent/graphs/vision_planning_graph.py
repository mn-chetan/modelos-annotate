"""LangGraph vision planning agent.

Replaces the single ad-hoc LLM call previously inlined in
``app.inference.routing.build_execution_plan`` with an explicit two-node
graph: ``plan`` (ask the model) -> ``validate`` (check the JSON is usable),
looping back to ``plan`` up to ``max_attempts`` times.

The actual model call is delegated to
``app.inference.agent_reasoning.call_json_agent`` so the existing
Vertex/HTTP transport, auth, and prompt plumbing are reused unchanged -
this graph only owns the control flow (retry-until-valid), which is the
part that benefits from being an explicit graph.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.agent.graphs import LangGraphUnavailable, _require_langgraph

_SUPPORTED_MODELS = {"yolo26", "faster_rcnn", "dino", "florence", "sam2"}

_SYSTEM_PROMPT = (
    "You are the Vision Planning Agent.\n"
    "Create a dynamic execution plan based on the scene evidence and available models.\n"
    "Supported Models:\n"
    "- yolo26: Primary detector for common objects (person, bicycle, car, motorcycle, bus, truck).\n"
    "- faster_rcnn: Secondary closed-set detector. Use as secondary when yolo26 is insufficient "
    "(e.g. crowded, high recall risk), or fallback if yolo26 is disabled.\n"
    "- dino: Grounding DINO open-vocabulary detector. Use only if there are custom classes in the "
    "ontology that YOLO/R-CNN cannot cover.\n"
    "- florence: Caption/labels helper. Use if cross-model verification or captioning is needed.\n"
    "- sam2: Segmentation model. ONLY use if segmentation is requested in evidence.metadata "
    "(segmentation_required = true).\n"
    "\n"
    "Strategies:\n"
    "- full_image: Standard resolution pass.\n"
    "- high_resolution: Higher resolution (1280) resize.\n"
    "- tiled: 3x3 tiles at 1024 resolution.\n"
    "- high_resolution_tiled: 4x4 tiles at 1280 resolution.\n"
    "\n"
    "Rules:\n"
    "- Treat small_object_ratio and scene density as observations; do not apply a fixed routing threshold.\n"
    "- If user intent or metadata requests 'outline', 'contour', 'precise boundary', 'segmentation', 'mask', or 'polygon', add 'sam2' to models for instance segmentation / polygon generation. Do NOT use bounding box only when polygon/segmentation is requested.\n"
    "- If user intent requests open line/path tracing ('trace', 'lane', 'centerline', 'polyline'), select path/line workflow.\n"
    "- Do not run Faster R-CNN blindly unless necessary or requested.\n"
    "\n"
    "Return ONLY JSON:\n"
    "{\n"
    '  "actions": [{"model": "yolo26", "strategy": "full_image", "labels": [], "parameters": {}}],\n'
    '  "verification": "standard"|"cross_model"|"human_review",\n'
    '  "reason": "evidence-based reasoning"\n'
    "}"
)


class VisionPlanningState(TypedDict, total=False):
    payload: dict[str, Any]
    settings: Any
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    valid: bool


def _validate(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    raw_actions = raw.get("actions")
    if not isinstance(raw_actions, list):
        return None
    actions = []
    supported_strategies = {"full_image", "high_resolution", "tiled", "high_resolution_tiled"}
    for raw_action in raw_actions:
        if not isinstance(raw_action, dict):
            return None
        model = str(raw_action.get("model") or "")
        strategy = str(raw_action.get("strategy") or "")
        if model not in _SUPPORTED_MODELS or strategy not in supported_strategies:
            return None
        actions.append({
            "model": model,
            "strategy": strategy,
            "labels": list(raw_action.get("labels") or []),
            "parameters": dict(raw_action.get("parameters") or {}),
            "reason": str(raw_action.get("reason") or ""),
        })
    if not actions:
        return None
    return {
        "decision_source": "agent",
        "plan_version": str(raw.get("plan_version") or "1"),
        "task_type": str(raw.get("task_type") or "detection"),
        "geometry": str(raw.get("geometry") or "box"),
        "actions": actions,
    }


def _plan_node(state: VisionPlanningState) -> VisionPlanningState:
    from app.inference.agent_reasoning import call_json_agent

    raw = call_json_agent(
        system_prompt=_SYSTEM_PROMPT,
        user_payload=state["payload"],
        settings=state.get("settings"),
    )
    return {"result": raw, "attempts": state.get("attempts", 0) + 1}


def _validate_node(state: VisionPlanningState) -> VisionPlanningState:
    validated = _validate(state.get("result"))
    return {"result": validated, "valid": validated is not None}


def _should_retry(state: VisionPlanningState) -> str:
    if state.get("valid"):
        return "done"
    if state.get("attempts", 0) >= state.get("max_attempts", 2):
        return "done"
    return "retry"


def _build_graph() -> Any:
    _require_langgraph()
    from langgraph.graph import END, StateGraph

    graph = StateGraph(VisionPlanningState)
    graph.add_node("plan", _plan_node)
    graph.add_node("validate", _validate_node)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "validate")
    graph.add_conditional_edges("validate", _should_retry, {"retry": "plan", "done": END})
    return graph.compile()


_compiled_graph: Any = None


def run_vision_planning_graph(
    *,
    ontology_classes: list[str],
    evidence: dict[str, Any],
    available_models: dict[str, bool],
    settings: Any = None,
    max_attempts: int = 2,
) -> dict[str, Any] | None:
    """Run the vision planning graph and return a validated plan dict, or ``None``.

    Raises ``LangGraphUnavailable`` if langgraph is not installed - callers
    (``app.inference.routing``) decide whether that should surface as an
    error or fall back to calling ``call_json_agent`` directly.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()

    final_state: VisionPlanningState = _compiled_graph.invoke(
        {
            "payload": {
                "ontology_classes": ontology_classes,
                "evidence": evidence,
                "available_models": available_models,
            },
            "settings": settings,
            "attempts": 0,
            "max_attempts": max_attempts,
        }
    )
    return final_state.get("result")


__all__ = ["run_vision_planning_graph", "LangGraphUnavailable"]
