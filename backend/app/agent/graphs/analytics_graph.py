"""LangGraph orchestration for validated project analytics."""

from __future__ import annotations

from typing import Any, TypedDict

from app.agent.graphs import LangGraphUnavailable, _require_langgraph
from app.services.analytics import calculate_project_kpis, validate_kpi_snapshot


class AnalyticsState(TypedDict, total=False):
    context: dict[str, Any]
    snapshot: dict[str, Any]


def _calculate_node(state: AnalyticsState) -> AnalyticsState:
    context = state["context"]
    return {
        "snapshot": calculate_project_kpis(
            project_id=context["project_id"],
            assets=context["assets"],
            annotations=context["annotations"],
            confidence_threshold=context.get("confidence_threshold"),
            total_production_cost=context.get("total_production_cost"),
            approved_annotations=context.get("approved_annotations", 0),
            ontology=context.get("ontology", []),
            throughput_per_hour=context.get("throughput_per_hour"),
            target_images=context.get("target_images"),
            double_review_events=context.get("audit_events"),
        )
    }


def _validate_node(state: AnalyticsState) -> AnalyticsState:
    return {"snapshot": validate_kpi_snapshot(state["snapshot"])}


def _build_graph() -> Any:
    _require_langgraph()
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AnalyticsState)
    graph.add_node("calculate", _calculate_node)
    graph.add_node("validate", _validate_node)
    graph.set_entry_point("calculate")
    graph.add_edge("calculate", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


_compiled_graph: Any = None


def run_project_analytics_graph(context: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic analytics through the existing graph architecture."""
    global _compiled_graph
    try:
        if _compiled_graph is None:
            _compiled_graph = _build_graph()
        state: AnalyticsState = _compiled_graph.invoke({"context": context})
        return state["snapshot"]
    except (ImportError, LangGraphUnavailable):
        return calculate_project_kpis(
            project_id=context["project_id"],
            assets=context["assets"],
            annotations=context["annotations"],
            confidence_threshold=context.get("confidence_threshold"),
            total_production_cost=context.get("total_production_cost"),
            approved_annotations=context.get("approved_annotations", 0),
            ontology=context.get("ontology", []),
            throughput_per_hour=context.get("throughput_per_hour"),
            target_images=context.get("target_images"),
            double_review_events=context.get("audit_events"),
        )


__all__ = ["run_project_analytics_graph"]
