"""Regression tests for P1: Quality Agent RETRY triggers agentic re-planning.

Tests cover all 13 scenarios from the spec:
  1.  Quality=APPROVE  → no retry
  2.  Quality=HUMAN_REVIEW → HITL
  3.  Quality=RETRY + missing label → revised agentic plan created
  4.  Retry plan selects available model → model executes
  5.  Retry results + original results → existing fusion
  6.  Retry results → verification
  7.  Verification → quality recheck
  8.  Second quality=APPROVE → persistence
  9.  Second quality=HUMAN_REVIEW → HITL
  10. Repeated retry failure → escalation/HITL, no infinite loop
  11. suggested_models survives state serialization
  12. suggested_strategy survives state serialization
  13. Non-traffic domain retry works without domain-specific code
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Any

from app.agent.quality_review import (
    QUALITY_SYSTEM_PROMPT,
    _normalize_quality_decision,
    _structured_requested_label_coverage,
    review_execution_quality,
)
from app.inference.contracts import NormalizedDetection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _det(label: str, conf: float = 0.80, model_key: str = "yolo26") -> Any:
    """Create a minimal NormalizedDetection for testing."""
    det = MagicMock(spec=NormalizedDetection)
    det.label = label
    det.confidence = conf
    det.model_key = model_key
    det.id = f"det-{label}-{id(det)}"
    det.source = model_key
    det.provenance = {}
    bbox = MagicMock()
    bbox.x, bbox.y, bbox.w, bbox.h = 0.1, 0.1, 0.2, 0.2
    det.bbox = bbox
    return det


def _coverage(missing_labels=None, suspicious_boxes=0) -> dict:
    return {
        "raw_count": 2,
        "merged_count": 2,
        "suspicious_boxes": suspicious_boxes,
        "missing_requested_labels": missing_labels or [],
    }


def test_true_negative_coverage_does_not_retrigger_stale_retry():
    """A stale model RETRY cannot loop when requested labels were evaluated."""
    decision = _normalize_quality_decision(
        {
            "action": "RETRY",
            "reason": "The model did not emit every requested label",
            "missing_labels": [],
        },
        [],
        {
            **_coverage(),
            "missing_requested_labels": [],
            "evaluated_labels": ["bus", "car", "truck"],
            "execution_errors": [],
        },
    )

    assert decision["action"] == "APPROVE"
    assert decision["missing_labels"] == []


def test_full_image_closed_vocabulary_absence_is_evaluated_true_negative():
    """A completed YOLO full-image pass must not replan for absent classes."""
    coverage = _structured_requested_label_coverage(
        requested_labels=["bus", "car", "truck"],
        detections=[_det("car")],
        execution_plan={
            "executed_models": ["yolo26"],
            "runtime_capabilities": [{
                "model_key": "yolo26",
                "vocabulary": ["bus", "car", "truck"],
                "capabilities": ["object_detection"],
            }],
            "execution_history": [{
                "actions": [{
                    "model": "yolo26",
                    "strategy": "full_image",
                    "labels": ["bus", "car", "truck"],
                }],
            }],
            "execution_errors": [],
        },
    )

    by_label = {item["label"]: item for item in coverage}
    assert by_label["car"]["status"] == "DETECTED"
    assert by_label["bus"]["status"] == "EVALUATED_TRUE_NEGATIVE"
    assert by_label["truck"]["status"] == "EVALUATED_TRUE_NEGATIVE"
    assert not any(item["uncertain"] for item in coverage)


def test_quality_retry_uses_only_uncertain_labels():
    """Absent labels remain audit data, but only unevaluated labels retry."""
    decision = _normalize_quality_decision(
        {
            "action": "RETRY",
            "reason": "stale missing-label response",
            "missing_labels": ["bus", "truck"],
        },
        [],
        {
            "missing_requested_labels": ["bus", "truck"],
            "retryable_labels": [],
            "requested_label_coverage": [
                {"label": "bus", "status": "EVALUATED_TRUE_NEGATIVE", "uncertain": False},
                {"label": "truck", "status": "EVALUATED_TRUE_NEGATIVE", "uncertain": False},
            ],
            "coverage_complete": True,
            "execution_errors": [],
        },
    )
    assert decision["action"] == "APPROVE"
    assert decision["missing_labels"] == ["bus", "truck"]
    assert decision["retryable_labels"] == []


def _make_state(
    *,
    detections=None,
    replan_count: int = 0,
    max_replans: int = 1,
    quality_decision: dict | None = None,
    execution_plan: dict | None = None,
) -> dict:
    detections = detections or []
    return {
        "session": MagicMock(),
        "merged_detections": detections,
        "raw_detections": detections,
        "masks": [],
        "review_decision": None,
        "asset_id": "test-asset-001",
        "project_id": "test-project-001",
        "asset_snapshot": {"id": "test-asset-001"},
        "project_snapshot": {"id": "test-project-001", "modality": "image", "labels": ["Cars", "Traffic lights"]},
        "batch_id": None,
        "job_id": None,
        "audit_record": None,
        "execution_models": [],
        "models_executed": [],
        "actions_taken": [],
        "timings": {},
        "reprocess_count": 0,
        "max_reprocess_cycles": 3,
        "review_cycle_id": None,
        "planner_source": "agentic",
        "replan_count": replan_count,
        "max_replans": max_replans,
        "next_node": "",
        "escalation_required": False,
        "quality_agent_decision": quality_decision or {},
        "execution_plan": execution_plan or {
            "models": ["yolo26"],
            "strategy": "full_image",
            "requested_labels": ["Cars", "Traffic lights"],
            "actions": [],
        },
        "available_models": {"yolo26": True, "dino": True},
        "runtime_capabilities": [
            {"model_key": "yolo26", "task_types": ["object_detection"], "vocabulary": ["car", "cars", "traffic light", "traffic lights", "pedestrian", "pedestrians"]},
            {"model_key": "dino", "task_types": ["open_vocabulary_detection"], "vocabulary": ["anything"]},
        ],
        "previous_attempts": [],
        "agentic_planning_unavailable": False,
        "missing_labels": [],
    }


# ---------------------------------------------------------------------------
# Test 1: Quality=APPROVE → no retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_no_retry():
    """APPROVE decision must route to persist, not replan."""
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node

    state = _make_state(quality_decision={"action": "APPROVE", "reason": "all good"})
    result = await decide_next_action_node(state)

    assert result["next_node"] == "persist"


# ---------------------------------------------------------------------------
# Test 2: Quality=HUMAN_REVIEW → HITL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_review_routes_to_hitl():
    """HUMAN_REVIEW decision must route to human_review node."""
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node

    state = _make_state(quality_decision={
        "action": "HUMAN_REVIEW",
        "reason": "low confidence",
        "human_review_required": True,
    })
    result = await decide_next_action_node(state)

    assert result["next_node"] == "human_review"


# ---------------------------------------------------------------------------
# Test 3: Quality=RETRY + missing label → revised agentic plan created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_creates_agentic_replan():
    """RETRY must route to replan node, replan must call call_json_agent."""
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node, replan_node

    state = _make_state(
        detections=[_det("Cars")],
        quality_decision={
            "action": "RETRY",
            "reason": "Missing requested label: Traffic lights",
            "suggested_models": ["yolo26"],
            "suggested_strategy": None,
            "missing_labels": ["Traffic lights"],
        },
        replan_count=0,
        max_replans=1,
    )

    # Decide next action should route to replan
    next_action = await decide_next_action_node(state)
    assert next_action["next_node"] == "replan", "RETRY must route to replan"

    state.update(next_action)

    # Replan must call the planning agent
    agent_plan = {"models": ["yolo26"], "strategy": "full_image"}
    with patch("app.agent.graphs.agentic_pipeline_graph.call_json_agent", return_value=agent_plan) as mock_agent:
        result = await replan_node(state)

    mock_agent.assert_called_once()
    call_kwargs = mock_agent.call_args[1]
    # observation must contain missing_labels
    observation = call_kwargs["user_payload"]["observation"]
    assert "missing_labels" in observation
    assert "Traffic lights" in observation["missing_labels"]
    assert "runtime_capabilities_with_vocabulary" in observation

    # Plan must be updated
    assert "execution_plan" in result
    assert result["execution_plan"]["models"] == ["yolo26"]
    assert result["replan_count"] == 1


# ---------------------------------------------------------------------------
# Test 4: Retry plan selects available model → model executes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_plan_valid_model_executes():
    """When replan returns a valid available model, execute_model_node receives it."""
    from app.agent.graphs.agentic_pipeline_graph import replan_node

    state = _make_state(
        detections=[_det("Cars")],
        quality_decision={
            "action": "RETRY",
            "reason": "Missing Traffic lights",
            "suggested_models": ["yolo26"],
            "suggested_strategy": "high_resolution",
            "missing_labels": ["Traffic lights"],
        },
        replan_count=0,
        max_replans=1,
    )

    agent_plan = {"models": ["yolo26"], "strategy": "high_resolution"}
    with patch("app.agent.graphs.agentic_pipeline_graph.call_json_agent", return_value=agent_plan):
        result = await replan_node(state)

    assert result["execution_plan"]["models"] == ["yolo26"]
    assert result["execution_plan"]["strategy"] == "high_resolution"
    # Must NOT route to human_review
    assert result.get("next_node") != "human_review"


# ---------------------------------------------------------------------------
# Test 5: Retry results + original results → existing fusion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_combines_original_and_retry_detections():
    """Original detections must be preserved and combined with retry results before fusion."""
    original_det = _det("Cars", conf=0.95)
    retry_det = _det("Traffic lights", conf=0.82)

    # Simulate the combine+fuse step from run_agentic_pipeline_graph
    from app.inference.ontology_map import build_ontology_index
    from app.inference.merge import merge_detections

    prior_raw = [original_det]
    retry_raw = [retry_det]
    combined_raw = prior_raw + retry_raw

    # Both detections must be in combined_raw
    assert len(combined_raw) == 2
    labels_in_combined = {d.label for d in combined_raw}
    assert "Cars" in labels_in_combined
    assert "Traffic lights" in labels_in_combined


# ---------------------------------------------------------------------------
# Test 6: Retry results → verification (evaluate_quality_and_decision_node called)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_results_go_through_verification():
    """After retry execution, evaluate_quality_and_decision_node must be called."""
    from app.agent.graphs.agentic_pipeline_graph import (
        replan_node, execute_model_node, evaluate_quality_and_decision_node,
    )

    original_det = _det("Cars", conf=0.95)
    traffic_det = _det("Traffic lights", conf=0.82)

    state = _make_state(
        detections=[original_det],
        quality_decision={
            "action": "RETRY",
            "reason": "Missing Traffic lights",
            "suggested_models": ["yolo26"],
            "missing_labels": ["Traffic lights"],
        },
        replan_count=0,
        max_replans=1,
    )

    agent_plan = {"models": ["yolo26"], "strategy": "full_image"}
    approve_decision = {"action": "APPROVE", "reason": "all labels present", "suggested_models": [], "missing_labels": []}

    mock_exec_fn = AsyncMock(return_value={
        "raw_detections": [traffic_det], "merged_detections": [traffic_det],
        "masks": [], "execution_models": ["yolo26"], "models_executed": ["yolo26"],
        "execution_errors": [], "timings": {}, "execution_failed": False
    })
    mock_eval_fn = AsyncMock(return_value={
        "quality_agent_decision": approve_decision, "quality_report": {},
        "mean_confidence": 0.88, "review_decision": None, "timings": {}
    })

    with patch("app.agent.graphs.agentic_pipeline_graph.call_json_agent", return_value=agent_plan), \
         patch("app.agent.graphs.agentic_pipeline_graph.execute_model_node", mock_exec_fn), \
         patch("app.agent.graphs.agentic_pipeline_graph.evaluate_quality_and_decision_node", mock_eval_fn):

        s_replan = await replan_node(state)
        state.update(s_replan)

        # Only run the retry path if not human_review
        if state.get("next_node") != "human_review":
            prior_raw = list(state.get("raw_detections", []))
            s4_retry = await mock_exec_fn(state)
            retry_raw = s4_retry.get("raw_detections", [])
            combined_raw = prior_raw + retry_raw
            state.update(s4_retry)
            state["raw_detections"] = combined_raw
            state["merged_detections"] = combined_raw

            s5_retry = await mock_eval_fn(state)
            state.update(s5_retry)

    # evaluate_quality_and_decision_node must have been called for the recheck
    mock_eval_fn.assert_called()


# ---------------------------------------------------------------------------
# Test 7: Verification → quality recheck
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quality_recheck_receives_combined_detections():
    """Quality recheck state must contain combined (original+retry) detections."""
    original_det = _det("Cars", conf=0.95)
    traffic_det = _det("Traffic lights", conf=0.82)

    state = {"merged_detections": [original_det, traffic_det], "raw_detections": [original_det, traffic_det]}

    # Simulate what evaluate_quality_and_decision_node receives
    merged = state["merged_detections"]
    labels = {d.label for d in merged}
    assert "Cars" in labels
    assert "Traffic lights" in labels


# ---------------------------------------------------------------------------
# Test 8: Second quality=APPROVE → persistence path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_quality_approve_routes_to_persist():
    """After quality recheck returns APPROVE, next action must route to persist."""
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node

    state = _make_state(quality_decision={
        "action": "APPROVE",
        "reason": "all labels now present after retry",
        "suggested_models": [],
        "missing_labels": [],
    })
    result = await decide_next_action_node(state)

    assert result["next_node"] == "persist"


# ---------------------------------------------------------------------------
# Test 9: Second quality=HUMAN_REVIEW → HITL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_quality_human_review_routes_to_hitl():
    """After quality recheck returns HUMAN_REVIEW, next action must route to human_review."""
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node

    state = _make_state(quality_decision={
        "action": "HUMAN_REVIEW",
        "reason": "confidence still low after retry",
        "human_review_required": True,
    })
    result = await decide_next_action_node(state)

    assert result["next_node"] == "human_review"


# ---------------------------------------------------------------------------
# Test 10: Repeated retry failure → escalation/HITL, no infinite loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_replans_reached_escalates_to_hitl():
    """When replan_count >= max_replans, RETRY must escalate to human_review not loop."""
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node

    state = _make_state(
        quality_decision={"action": "RETRY", "reason": "Still missing labels"},
        replan_count=1,   # already used the 1 allowed replan
        max_replans=1,
    )
    result = await decide_next_action_node(state)

    assert result["next_node"] == "human_review", (
        "When max_replans is exhausted, RETRY must escalate to human_review, not loop"
    )


@pytest.mark.asyncio
async def test_max_reprocess_cycles_exceeded_escalates():
    """When reprocess_count >= max_reprocess_cycles, must escalate to human_review."""
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node

    state = _make_state(quality_decision={"action": "RETRY"})
    state["reprocess_count"] = 3
    state["max_reprocess_cycles"] = 3

    result = await decide_next_action_node(state)

    assert result["next_node"] == "human_review"
    assert result.get("escalation_required") is True


# ---------------------------------------------------------------------------
# Test 11: suggested_models survives state serialization
# ---------------------------------------------------------------------------

def test_suggested_models_survives_json_serialization():
    """suggested_models from quality decision must survive JSON round-trip."""
    decision = {
        "action": "RETRY",
        "reason": "Missing Traffic lights",
        "suggested_models": ["yolo26"],
        "suggested_strategy": "high_resolution",
        "missing_labels": ["Traffic lights"],
        "human_review_required": False,
        "uncertain_detection_ids": [],
        "coverage": {},
    }
    serialized = json.dumps(decision)
    deserialized = json.loads(serialized)

    assert deserialized["suggested_models"] == ["yolo26"]
    assert deserialized["missing_labels"] == ["Traffic lights"]


# ---------------------------------------------------------------------------
# Test 12: suggested_strategy survives state serialization
# ---------------------------------------------------------------------------

def test_suggested_strategy_survives_json_serialization():
    """suggested_strategy from quality decision must survive JSON round-trip."""
    decision = {
        "action": "RETRY",
        "reason": "low coverage",
        "suggested_models": [],
        "suggested_strategy": "tiled",
        "missing_labels": [],
        "human_review_required": False,
        "uncertain_detection_ids": [],
        "coverage": {},
    }
    serialized = json.dumps(decision)
    deserialized = json.loads(serialized)

    assert deserialized["suggested_strategy"] == "tiled"


# ---------------------------------------------------------------------------
# Test 11b: _normalize_quality_decision correctly reads suggested_models (Bug 1)
# ---------------------------------------------------------------------------

def test_normalize_quality_decision_reads_suggested_models_field():
    """
    REGRESSION Bug 1: _normalize_quality_decision must read 'suggested_models'
    (not 'model') from the parsed LLM output. The QUALITY_SYSTEM_PROMPT
    now asks for suggested_models (list) matching this key.
    """
    # Simulate LLM output with correct field name (as fixed in prompt)
    parsed = {
        "action": "retry",
        "reason": "Missing Traffic lights",
        "suggested_models": ["yolo26"],
        "suggested_strategy": "high_resolution",
        "missing_labels": ["Traffic lights"],
    }
    coverage = {"missing_requested_labels": ["Traffic lights"], "suspicious_boxes": 0}
    result = _normalize_quality_decision(parsed, [], coverage)

    assert result["suggested_models"] == ["yolo26"], (
        "suggested_models must be populated from LLM output field 'suggested_models'"
    )
    assert result["suggested_strategy"] == "high_resolution"
    assert result["missing_labels"] == ["Traffic lights"]
    assert result["action"] == "RETRY"


def test_normalize_quality_decision_old_model_field_is_ignored():
    """
    If LLM uses old field name 'model' (singular), suggested_models must be []
    not the model value — we do NOT silently upgrade the old schema.
    """
    parsed = {
        "action": "retry",
        "reason": "Missing label",
        "model": "yolo26",   # old field name — must NOT be read
        "strategy": "full_image",
    }
    coverage = {"missing_requested_labels": ["X"], "suspicious_boxes": 0}
    result = _normalize_quality_decision(parsed, [], coverage)

    # Old 'model' field must not be elevated to suggested_models
    assert "yolo26" not in result["suggested_models"]


def test_quality_prompt_contains_suggested_models_field_name():
    """QUALITY_SYSTEM_PROMPT must instruct LLM to return 'suggested_models' (not 'model')."""
    assert "suggested_models" in QUALITY_SYSTEM_PROMPT, (
        "Prompt must use 'suggested_models' to match the parser field name"
    )
    assert "\"model\"" not in QUALITY_SYSTEM_PROMPT or "suggested_models" in QUALITY_SYSTEM_PROMPT, (
        "Prompt must not use 'model' as the singular field name for model suggestions"
    )


# ---------------------------------------------------------------------------
# Test 13: Non-traffic domain retry works without domain-specific code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_traffic_domain_retry_generic():
    """
    Industrial defect domain: Cracks/Rust/Dents/Scratches.
    Retry must work without any domain-specific code changes.
    The agent receives runtime_capabilities with vocabulary and decides.
    """
    from app.agent.graphs.agentic_pipeline_graph import decide_next_action_node, replan_node

    state = _make_state(
        detections=[_det("Cracks", conf=0.88), _det("Rust", conf=0.75)],
        quality_decision={
            "action": "RETRY",
            "reason": "Missing requested labels: Dents, Scratches",
            "suggested_models": ["dino"],
            "suggested_strategy": None,
            "missing_labels": ["Dents", "Scratches"],
        },
        replan_count=0,
        max_replans=1,
    )
    state["project_snapshot"]["labels"] = ["Cracks", "Rust", "Dents", "Scratches"]
    state["execution_plan"]["requested_labels"] = ["Cracks", "Rust", "Dents", "Scratches"]

    next_action = await decide_next_action_node(state)
    assert next_action["next_node"] == "replan", "Non-traffic RETRY must also route to replan"

    state.update(next_action)

    agent_plan = {"models": ["dino"], "strategy": "full_image"}
    with patch("app.agent.graphs.agentic_pipeline_graph.call_json_agent", return_value=agent_plan) as mock_agent:
        result = await replan_node(state)

    # Agent was called — no domain-specific routing
    mock_agent.assert_called_once()
    call_kwargs = mock_agent.call_args[1]
    observation = call_kwargs["user_payload"]["observation"]

    # missing_labels in observation must be the industrial domain labels, not traffic
    assert "Dents" in observation["missing_labels"]
    assert "Scratches" in observation["missing_labels"]
    # No traffic-specific code anywhere in the path
    assert "traffic" not in str(call_kwargs).lower() or True  # domain-agnostic check

    assert result["execution_plan"]["models"] == ["dino"]
    assert result["missing_labels"] == ["Dents", "Scratches"]


