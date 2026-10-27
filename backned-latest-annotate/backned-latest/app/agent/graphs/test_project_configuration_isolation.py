"""Regression tests for project-scoped intent configuration."""

import pytest

from app.agent.graphs.agentic_pipeline_graph import understand_request_node


@pytest.mark.asyncio
async def test_image_intent_uses_current_project_task_and_labels():
    state = {
        "project_id": "project-b",
        "asset_id": "asset-b",
        "user_request": "traffic monitoring with cars and buses",
        "project_snapshot": {
            "id": "project-b",
            "modality": "image",
            "task_type": "object_detection",
            "labels": ["person", "bicycle"],
        },
        "timings": {},
        "audit_record": None,
    }

    result = await understand_request_node(state)
    intent = result["parsed_intent"]

    assert intent.task_type == "detection"
    assert intent.geometry_type == "box"
    assert intent.requested_labels == ["person", "bicycle"]
    assert "car" not in intent.requested_labels
    assert "bus" not in intent.requested_labels


@pytest.mark.asyncio
async def test_text_intent_does_not_inherit_image_labels():
    state = {
        "project_id": "text-project",
        "asset_id": "text-asset",
        "user_request": "detect traffic objects",
        "project_snapshot": {
            "id": "text-project",
            "modality": "text",
            "task_type": "NER",
            "target_objects": ["PERSON", "LOCATION", "ORGANIZATION"],
            "labels": [],
        },
        "timings": {},
        "audit_record": None,
    }

    result = await understand_request_node(state)
    intent = result["parsed_intent"]

    assert intent.task_type == "ENTITY_EXTRACTION"
    assert intent.geometry_type == "text_span"
    assert intent.requested_labels == ["Person", "Location", "Organization"]
    assert "car" not in intent.requested_labels
    assert "bus" not in intent.requested_labels


@pytest.mark.asyncio
async def test_explicit_multi_object_requirement_is_not_collapsed_to_project_label():
    state = {
        "project_id": "traffic-project",
        "asset_id": "traffic-asset",
        "user_request": "Detect car + person + motorcycle + auto-rickshaw",
        "project_snapshot": {
            "id": "traffic-project",
            "modality": "image",
            "task_type": "object_detection",
            # Represents the stale/single label configuration that previously
            # caused planning to receive only `auto`.
            "labels": ["auto"],
        },
        "timings": {},
        "audit_record": None,
    }

    result = await understand_request_node(state)

    assert set(result["parsed_intent"].requested_labels) == {
        "car", "person", "motorcycle"
    }


@pytest.mark.asyncio
async def test_detection_scope_keeps_custom_target_and_approved_ontology_classes():
    state = {
        "project_id": "traffic-project",
        "asset_id": "traffic-asset",
        "user_request": "Run object detection on this traffic image",
        "project_snapshot": {
            "id": "traffic-project",
            "modality": "image",
            "task_type": "object_detection",
            "target_labels": ["auto"],
            "labels": ["auto"],
            "label_ontology": [
                {"name": "auto"}, {"name": "person"}, {"name": "car"},
                {"name": "motorcycle"}, {"name": "bus"}, {"name": "truck"},
                {"name": "bicycle"},
            ],
        },
        "timings": {},
        "audit_record": None,
    }

    result = await understand_request_node(state)

    assert set(result["parsed_intent"].requested_labels) == {
        "person", "car", "motorcycle", "bus", "truck", "bicycle"
    }
