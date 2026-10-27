from __future__ import annotations

import pytest
from unittest.mock import patch

from app.agent.graphs.agentic_pipeline_graph import (
    validate_plan_grounding,
    ground_labels_to_capabilities,
    create_execution_plan_node,
)
from app.agent.intent import ParsedIntent


RUNTIME_CAPS = [
    {
        "model_key": "yolo26",
        "model_id": "yolo26n.pt",
        "available": True,
        "loaded": True,
        "capabilities": ["detection"],
        "is_open_vocabulary": False,
        "vocabulary": ["car", "person", "truck", "bus"],
        "geometry_types": ["box"],
    },
    {
        "model_key": "clip",
        "model_id": "openai/clip-vit-base-patch32",
        "available": True,
        "loaded": True,
        "capabilities": ["classification"],
        "is_open_vocabulary": True,
        "vocabulary": [],
        "geometry_types": ["classification"],
    },
]


def test_ground_labels_to_capabilities_ignores_clip():
    """clip must not be selected as an open-vocabulary object detector."""
    actions, unavailable = ground_labels_to_capabilities(
        requested_labels=["car", "custom_vehicle"],
        runtime_capabilities=RUNTIME_CAPS,
    )
    # car should go to yolo26
    yolo_action = next((a for a in actions if a["model"] == "yolo26"), None)
    assert yolo_action is not None
    assert "car" in yolo_action["labels"]

    # clip must NOT be assigned to custom_vehicle for detection
    clip_action = next((a for a in actions if a["model"] == "clip"), None)
    assert clip_action is None
    assert "custom_vehicle" in unavailable


def test_validate_plan_grounding_non_spatial_has_label_key():
    """invalid_reasons entry for non-spatial model must include 'label' key."""
    actions = [
        {"model": "clip", "labels": ["car", "pedestrian"], "strategy": "full_image"}
    ]
    is_valid, records, invalid_reasons = validate_plan_grounding(
        actions=actions,
        runtime_capabilities=RUNTIME_CAPS,
    )
    assert not is_valid
    assert len(invalid_reasons) > 0
    assert "label" in invalid_reasons[0]
    assert "labels" in invalid_reasons[0]
    assert invalid_reasons[0]["model"] == "clip"


@pytest.mark.asyncio
async def test_create_execution_plan_node_no_key_error_on_non_spatial():
    """If Gemini returns clip for detection, create_execution_plan_node must not raise KeyError: 'label'."""
    intent = ParsedIntent(
        user_request="Detect TrafficVision AI",
        task_type="detection",
        geometry_type="box",
        requested_labels=["TrafficVision AI"],
    )
    state = {
        "parsed_intent": intent,
        "available_models": {"yolo26": True, "clip": True},
        "capability_gaps": [],
        "runtime_capabilities": RUNTIME_CAPS,
        "project_snapshot": {"modality": "image", "labels": ["TrafficVision AI"]},
        "asset_snapshot": {"id": "asset-1", "width": 640, "height": 480},
    }

    # Simulate Gemini returning an invalid plan with clip
    with patch(
        "app.agent.graphs.agentic_pipeline_graph.call_json_agent",
        return_value={
            "decision_source": "agent",
            "plan_version": "1",
            "task_type": "detection",
            "geometry": "box",
            "actions": [
                {
                    "model": "clip",
                    "strategy": "full_image",
                    "labels": ["TrafficVision AI"],
                    "parameters": {},
                    "reason": "Test non-spatial model",
                }
            ],
        },
    ):
        result = await create_execution_plan_node(state)
        # It must complete without raising KeyError: 'label'
        assert result is not None
