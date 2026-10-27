"""LangGraph intake agent.

Drives the project intake -> plan pipeline end to end as an explicit graph:
``intake`` -> (needs clarification? stop : ``generate_plan``) -> end.

All budget guarding, persistence, and LLM calls are delegated unchanged to
the existing ``app.agent.service.AgentService`` methods - this graph only
owns the control flow (skip straight to a plan when the agent didn't ask
clarifying questions, otherwise stop and wait for a human).
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.agent.graphs import _require_langgraph
from app.domain.enums import PlanStatus


class IntakeState(TypedDict, total=False):
    agent_service: Any
    project_id: str
    plan: dict[str, Any]
    needs_clarification: bool


async def _intake_node(state: IntakeState) -> IntakeState:
    plan = await state["agent_service"].run_intake(state["project_id"])
    return {
        "plan": plan,
        "needs_clarification": plan.get("status") == PlanStatus.AWAITING_CLARIFICATION.value,
    }


async def _generate_plan_node(state: IntakeState) -> IntakeState:
    plan = await state["agent_service"].generate_plan(state["project_id"])
    return {"plan": plan}


def _route(state: IntakeState) -> str:
    return "stop" if state.get("needs_clarification") else "generate_plan"


def _build_graph() -> Any:
    _require_langgraph()
    from langgraph.graph import END, StateGraph

    graph = StateGraph(IntakeState)
    graph.add_node("intake", _intake_node)
    graph.add_node("generate_plan", _generate_plan_node)
    graph.set_entry_point("intake")
    graph.add_conditional_edges("intake", _route, {"stop": END, "generate_plan": "generate_plan"})
    graph.add_edge("generate_plan", END)
    return graph.compile()


_compiled_graph: Any = None


async def run_intake_graph(agent_service: Any, project_id: str) -> dict[str, Any]:
    """Run intake, then automatically generate a plan if no clarification is needed.

    Returns the final plan dict (same shape as ``AgentService.get_plan``).
    Raises ``LangGraphUnavailable`` if langgraph is not installed.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()

    final_state: IntakeState = await _compiled_graph.ainvoke(
        {"agent_service": agent_service, "project_id": project_id}
    )
    return final_state["plan"]


__all__ = ["run_intake_graph"]
