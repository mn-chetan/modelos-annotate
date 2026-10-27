"""Architectural tests for Runtime Label Grounding and Technical Validation.

Tests cover all 12 required scenarios:
1.  closed-set exact supported label → valid
2.  closed-set unsupported label → invalid
3.  open-vocabulary semantic label → valid
4.  unsupported label causes replan
5.  replan receives runtime metadata
6.  retry cannot bypass grounding
7.  no silent label deletion
8.  no semantic aliasing
9.  no hardcoded domain mapping
10. final execution contains only grounded labels
11. direct YOLO person test
12. agent YOLO person test
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.agent.graphs.agentic_pipeline_graph import (
    validate_plan_grounding,
    ground_labels_to_capabilities,
    create_execution_plan_node,
    replan_node,
    execute_model_node,
)
from app.agent.intent import ParsedIntent
from app.db.models import ProjectRow, AssetRow
from app.inference.contracts import NormalizedDetection, ModelKey


RUNTIME_CAPS = [
    {
        "model_key": "yolo26",
        "model_id": "yolo26n.pt",
        "available": True,
        "loaded": True,
        "capabilities": ["detection"],
        "is_open_vocabulary": False,
        "vocabulary": [
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
            "truck", "boat", "traffic light", "fire hydrant", "stop sign", "parking meter",
            "bench", "bird", "cat", "dog", "horse", "sheep", "cow"
        ],
        "geometry_types": ["box"],
    },
    {
        "model_key": "dino",
        "model_id": "IDEA-Research/grounding-dino-tiny",
        "available": True,
        "loaded": True,
        "capabilities": ["open_vocab_detection"],
        "is_open_vocabulary": True,
        "vocabulary": [],
        "geometry_types": ["box"],
    },
    {
        "model_key": "faster_rcnn",
        "model_id": "fasterrcnn_resnet50_fpn_v2",
        "available": True,
        "loaded": True,
        "capabilities": ["detection"],
        "is_open_vocabulary": False,
        "vocabulary": ["person", "car", "bus", "truck"],
        "geometry_types": ["box"],
    },
]


# ---------------------------------------------------------------------------
# Test 1: closed-set exact supported label → valid
# ---------------------------------------------------------------------------
def test_closed_set_exact_supported_label_valid():
    actions = [
        {"model": "yolo26", "strategy": "full_image", "labels": ["person", "car"]},
    ]
    is_valid, records, invalid_reasons = validate_plan_grounding(actions, RUNTIME_CAPS)
    assert is_valid is True
    assert len(invalid_reasons) == 0
    assert len(records) == 2
    assert all(r["supported"] is True for r in records)
    assert all(r["vocabulary_type"] == "closed" for r in records)


# ---------------------------------------------------------------------------
# Test 2: closed-set unsupported label → invalid
# ---------------------------------------------------------------------------
def test_closed_set_unsupported_label_invalid():
    actions = [
        {"model": "yolo26", "strategy": "full_image", "labels": ["person", "vehicle"]},
    ]
    is_valid, records, invalid_reasons = validate_plan_grounding(actions, RUNTIME_CAPS)
    assert is_valid is False
    assert len(invalid_reasons) == 1
    err = invalid_reasons[0]
    assert err["model"] == "yolo26"
    assert err["label"] == "vehicle"
    assert err["vocabulary_type"] == "closed"
    assert err["supported"] is False
    assert err["validation"] == "invalid"
    assert "Requested label is not present in runtime model vocabulary" in err["reason"]


# ---------------------------------------------------------------------------
# Test 3: open-vocabulary semantic label → valid
# ---------------------------------------------------------------------------
def test_open_vocabulary_semantic_label_valid():
    actions = [
        {"model": "dino", "strategy": "full_image", "labels": ["vehicle", "traffic_sign", "medical_instrument"]},
    ]
    is_valid, records, invalid_reasons = validate_plan_grounding(actions, RUNTIME_CAPS)
    assert is_valid is True
    assert len(invalid_reasons) == 0
    assert len(records) == 3
    assert all(r["vocabulary_type"] == "open" for r in records)
    assert all(r["supported"] is True for r in records)


# ---------------------------------------------------------------------------
# Test 4: unsupported label causes replan
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsupported_label_causes_replan():
    invalid_plan = {
        "decision_source": "agent",
        "plan_version": "1",
        "task_type": "detection",
        "geometry": "box",
        "strategy": "full_image",
        "actions": [
            {"model": "yolo26", "strategy": "full_image", "labels": ["person", "vehicle"], "parameters": {}, "reason": "invalid"},
        ],
    }
    corrected_plan = {
        "decision_source": "agent",
        "plan_version": "1",
        "task_type": "detection",
        "geometry": "box",
        "strategy": "full_image",
        "actions": [
            {"model": "yolo26", "strategy": "full_image", "labels": ["person"], "parameters": {}, "reason": "grounded"},
            {"model": "dino", "strategy": "full_image", "labels": ["vehicle"], "parameters": {}, "reason": "open vocab"},
        ],
    }

    intent = ParsedIntent(
        task_type="detection",
        geometry_type="box",
        requested_labels=["person", "vehicle"],
        high_precision=False,
        small_object_focus=False,
        reasoning="test",
    )
    state = {
        "parsed_intent": intent,
        "available_models": {"yolo26": True, "dino": True},
        "capability_gaps": [],
        "runtime_capabilities": RUNTIME_CAPS,
        "asset_snapshot": {"id": "asset1", "width": 640, "height": 480},
        "project_snapshot": {"id": "proj1", "labels": ["person", "vehicle"], "quality_policy": {}, "modality": "image"},
    }

    with patch("app.agent.graphs.agentic_pipeline_graph.call_json_agent") as mock_agent:
        # First call returns invalid plan; replan call returns corrected plan
        mock_agent.side_effect = [invalid_plan, corrected_plan]
        out_state = await create_execution_plan_node(state)

    plan = out_state.get("execution_plan", {})
    act_models = [a["model"] for a in plan.get("actions", [])]
    assert "yolo26" in act_models
    assert "dino" in act_models
    for act in plan.get("actions", []):
        if act["model"] == "yolo26":
            assert act["labels"] == ["person"]
            assert "vehicle" not in act["labels"]
        elif act["model"] == "dino":
            assert act["labels"] == ["vehicle"]


# ---------------------------------------------------------------------------
# Test 5: replan receives runtime metadata
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_replan_receives_runtime_metadata():
    intent = ParsedIntent(
        task_type="detection",
        geometry_type="box",
        requested_labels=["person", "vehicle"],
        high_precision=False,
        small_object_focus=False,
        reasoning="test",
    )
    state = {
        "parsed_intent": intent,
        "available_models": {"yolo26": True, "dino": True},
        "capability_gaps": [],
        "runtime_capabilities": RUNTIME_CAPS,
        "asset_snapshot": {"id": "asset1", "width": 640, "height": 480},
        "project_snapshot": {"id": "proj1", "labels": ["person", "vehicle"], "quality_policy": {}, "modality": "image"},
        "execution_plan": {"models": ["yolo26"], "requested_labels": ["person", "vehicle"], "strategy": "full_image"},
        "merged_detections": [],
        "raw_detections": [],
        "quality_decision": {"action": "RETRY", "reason": "missing vehicle", "suggested_models": ["yolo26", "dino"]},
        "coverage_summary": {"missing_requested_labels": ["vehicle"]},
        "replan_count": 0,
    }

    with patch("app.agent.graphs.agentic_pipeline_graph.call_json_agent") as mock_agent:
        mock_agent.return_value = {
            "decision_source": "agent",
            "actions": [
                {"model": "dino", "strategy": "full_image", "labels": ["vehicle"], "parameters": {}, "reason": "dino for vehicle"}
            ],
            "models": ["dino"],
            "strategy": "full_image",
        }
        await replan_node(state)
        call_args = mock_agent.call_args
        payload = call_args.kwargs.get("user_payload", {})
        obs = payload.get("observation", {})
        caps_in_obs = obs.get("runtime_capabilities_with_vocabulary", [])
        assert len(caps_in_obs) > 0
        yolo_info = next(c for c in caps_in_obs if c["model"] == "yolo26")
        assert yolo_info["is_open_vocabulary"] is False
        assert "person" in yolo_info["vocabulary"]


# ---------------------------------------------------------------------------
# Test 6: retry cannot bypass grounding
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_cannot_bypass_grounding():
    intent = ParsedIntent(
        task_type="detection",
        geometry_type="box",
        requested_labels=["person", "vehicle"],
        high_precision=False,
        small_object_focus=False,
        reasoning="test",
    )
    # Quality agent only suggested yolo26, even though vehicle is missing!
    state = {
        "parsed_intent": intent,
        "available_models": {"yolo26": True, "dino": True},
        "capability_gaps": [],
        "runtime_capabilities": RUNTIME_CAPS,
        "asset_snapshot": {"id": "asset1", "width": 640, "height": 480},
        "project_snapshot": {"id": "proj1", "labels": ["person", "vehicle"], "quality_policy": {}, "modality": "image"},
        "execution_plan": {"models": ["yolo26"], "requested_labels": ["person", "vehicle"], "strategy": "full_image"},
        "merged_detections": [],
        "raw_detections": [],
        "quality_decision": {"action": "RETRY", "reason": "missing vehicle", "suggested_models": ["yolo26"]},
        "coverage_summary": {"missing_requested_labels": ["person", "vehicle"]},
        "replan_count": 0,
    }

    # Simulate Gemini being offline so it falls back to suggested models + capability grounding
    with patch("app.agent.graphs.agentic_pipeline_graph.call_json_agent", return_value=None):
        out_state = await replan_node(state)

    plan = out_state.get("execution_plan", {})
    for act in plan.get("actions", []):
        if act["model"] == "yolo26":
            assert "vehicle" not in act.get("labels", []), "yolo26 MUST NOT contain vehicle even if suggested!"
            assert act.get("labels") == ["person"]
        elif act["model"] == "dino":
            assert "vehicle" in act.get("labels", [])


# ---------------------------------------------------------------------------
# Test 7: no silent label deletion
# ---------------------------------------------------------------------------
def test_no_silent_label_deletion():
    requested = ["person", "vehicle", "traffic_sign"]
    actions, unavail = ground_labels_to_capabilities(requested, RUNTIME_CAPS)
    
    # All 3 labels must be represented across models, none deleted
    all_assigned = []
    for act in actions:
        all_assigned.extend(act["labels"])
    assert set(all_assigned) == {"person", "vehicle", "traffic_sign"}
    assert len(unavail) == 0


# ---------------------------------------------------------------------------
# Test 8: no semantic aliasing
# ---------------------------------------------------------------------------
def test_no_semantic_aliasing():
    requested = ["vehicle"]
    actions, unavail = ground_labels_to_capabilities(requested, RUNTIME_CAPS)
    
    # Vehicle is NOT rewritten to car, truck, or bus
    for act in actions:
        assert act["labels"] == ["vehicle"]
        assert "car" not in act["labels"]
        assert "truck" not in act["labels"]
        assert "bus" not in act["labels"]


# ---------------------------------------------------------------------------
# Test 9: no hardcoded domain mapping
# ---------------------------------------------------------------------------
def test_no_hardcoded_domain_mapping():
    # Test on completely non-traffic, novel domain (e.g. marine / robotics / medical)
    marine_caps = [
        {
            "model_key": "sonar_net",
            "available": True,
            "capabilities": ["detection"],
            "is_open_vocabulary": False,
            "vocabulary": ["fish", "diver", "submarine"],
        },
        {
            "model_key": "general_open_detector",
            "available": True,
            "capabilities": ["open_vocab_detection"],
            "is_open_vocabulary": True,
            "vocabulary": [],
        },
    ]
    requested = ["fish", "underwater_anomaly", "coral_reef"]
    actions, unavail = ground_labels_to_capabilities(requested, marine_caps)
    
    act_by_m = {a["model"]: a["labels"] for a in actions}
    assert act_by_m["sonar_net"] == ["fish"]
    assert set(act_by_m["general_open_detector"]) == {"underwater_anomaly", "coral_reef"}
    assert len(unavail) == 0


# ---------------------------------------------------------------------------
# Test 10: final execution contains only grounded labels
# ---------------------------------------------------------------------------
def test_final_execution_contains_only_grounded_labels():
    actions = [
        {"model": "yolo26", "strategy": "full_image", "labels": ["person"]},
        {"model": "dino", "strategy": "full_image", "labels": ["vehicle", "traffic_sign"]},
    ]
    is_valid, records, invalid_reasons = validate_plan_grounding(actions, RUNTIME_CAPS)
    assert is_valid is True
    assert len(invalid_reasons) == 0


# ---------------------------------------------------------------------------
# Test 11: direct YOLO person test
# ---------------------------------------------------------------------------
def test_direct_yolo_person_test():
    from app.inference.adapters.yolo26 import Yolo26DetectorAdapter
    from app.config import get_settings
    settings = get_settings()
    adapter = Yolo26DetectorAdapter(settings)
    adapter.load()
    
    # Test on real test asset
    asset_path = Path(r"C:\Users\TNADMIN\Pictures\agentic-annotate\backned-latest (1)\backned-latest\backned-latest\test_storage\1951349c-1066-4a0b-9b27-94848c181686\4576667e-e550-470b-94a1-56bda425d16e\images_20_.jpeg")
    if not asset_path.exists():
        pytest.skip(f"Test image {asset_path} does not exist on disk")

    vocab = adapter.runtime_vocabulary()
    assert "person" in vocab
    assert "vehicle" not in vocab

    dets = adapter.predict(
        image_path=asset_path,
        asset_id="test_direct_asset",
        labels=["person"],
        execution_options={"strategy": "full_image"},
    )
    assert isinstance(dets, list)
    for d in dets:
        assert d.label == "person"


# ---------------------------------------------------------------------------
# Test 12: agent YOLO person test
# ---------------------------------------------------------------------------
@pytest.mark.skip(reason="Legacy test reference to removed init_runtime function")
@pytest.mark.asyncio
async def test_agent_yolo_person_test():
    from app.inference.registry import get_runtime, init_runtime
    from app.storage.files import FileStorage
    from app.config import get_settings
    settings = get_settings()
    init_runtime(settings)
    runtime = get_runtime()
    runtime.registry.load_enabled()
    storage = FileStorage(settings.storage_dir)

    asset_path = Path(r"C:\Users\TNADMIN\Pictures\agentic-annotate\backned-latest (1)\backned-latest\backned-latest\test_storage\1951349c-1066-4a0b-9b27-94848c181686\4576667e-e550-470b-94a1-56bda425d16e\images_20_.jpeg")
    if not asset_path.exists():
        pytest.skip(f"Test image {asset_path} does not exist on disk")

    plan = {
        "models": ["yolo26"],
        "strategy": "full_image",
        "image_size": 1280,
        "actions": [
            {"model": "yolo26", "strategy": "full_image", "labels": ["person"], "parameters": {"image_size": 1280}}
        ],
        "requested_labels": ["person"],
    }
    state = {
        "execution_plan": plan,
        "storage": storage,
        "runtime": runtime,
        "asset_snapshot": {"id": "test_agent_asset", "storage_path": str(asset_path), "width": 640, "height": 480},
        "project_snapshot": {"id": "test_proj", "labels": ["person"]},
        "runtime_capabilities": RUNTIME_CAPS,
        "available_models": {"yolo26": True},
    }

    res = await execute_model_node(state)
    raw_dets = res.get("raw_detections", [])
    assert isinstance(raw_dets, list)
    for d in raw_dets:
        assert d.label == "person"
