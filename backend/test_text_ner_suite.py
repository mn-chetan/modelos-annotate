import pytest
import asyncio
from pathlib import Path

from app.services.text_capability import TextCapabilityService, normalize_text_task
from app.text_backend.core.exceptions import AppError
from app.inference.registry import InferenceRuntime, set_runtime, create_registry_from_settings
from app.config import get_settings


@pytest.mark.asyncio
async def test_1_generic_ner_with_all_target_labels(tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_text = (
        "Satya Nadella is the CEO of Microsoft. Microsoft is headquartered in Redmond, Washington. "
        "The company announced the event on October 3, 2026 and launched a new product worth $999."
    )
    sample_file.write_text(sample_text)
    
    target_labels = ["Person", "Organization", "Location", "Date", "Product", "Event", "Money"]
    
    svc = TextCapabilityService()
    res = await svc.execute(
        path=sample_file,
        task_type="ENTITY_EXTRACTION",
        labels=target_labels,
        asset_id="test_asset_1",
        model_id="text_entity_extraction"
    )
    
    assert "annotations" in res
    assert res.get("errors") == []
    assert len(res["annotations"]) > 0
    # Confirm no IDENTIFICATION_NAME_REQUIRED errors were produced
    assert not any(err.get("code") == "IDENTIFICATION_NAME_REQUIRED" for err in res.get("errors", []))


@pytest.mark.asyncio
async def test_2_generic_ner_empty_labels(tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("Apple Inc. reported record revenue in Cupertino yesterday.")
    
    svc = TextCapabilityService()
    res = await svc.execute(
        path=sample_file,
        task_type="NER",
        labels=[],
        asset_id="test_asset_2",
        model_id="text_entity_extraction"
    )
    
    assert "annotations" in res
    assert res.get("errors") == []
    assert not any(err.get("code") == "IDENTIFICATION_NAME_REQUIRED" for err in res.get("errors", []))


@pytest.mark.asyncio
async def test_3_sentiment_annotation(tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("The product performance was absolutely outstanding and exceeded expectations.")
    
    svc = TextCapabilityService()
    res = await svc.execute(
        path=sample_file,
        task_type="SENTIMENT_ANALYSIS",
        labels=[],
        asset_id="test_asset_3",
        model_id="text_sentiment_analysis"
    )
    
    assert "annotations" in res
    assert len(res["annotations"]) == 1
    assert res["annotations"][0]["geometry_type"] == "text_classification"
    assert res["annotations"][0]["label"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]


@pytest.mark.asyncio
async def test_4_text_classification(tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("This quarter financial results show steady revenue growth.")
    
    svc = TextCapabilityService()
    res = await svc.execute(
        path=sample_file,
        task_type="TEXT_CLASSIFICATION",
        labels=[],
        asset_id="test_asset_4",
        model_id="text_classification"
    )
    
    assert "annotations" in res
    assert len(res["annotations"]) == 1
    assert res["annotations"][0]["geometry_type"] == "text_classification"


@pytest.mark.asyncio
async def test_5_relation_extraction(tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("Steve Jobs founded Apple in California.")
    
    svc = TextCapabilityService()
    res = await svc.execute(
        path=sample_file,
        task_type="RELATION_EXTRACTION",
        labels=[],
        asset_id="test_asset_5",
        model_id="text_relation_extraction"
    )
    
    assert "annotations" in res
    assert res.get("errors") == []


@pytest.mark.asyncio
async def test_6_drug_matching_requires_identification_name(tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("Patient took 500mg daily.")
    
    svc = TextCapabilityService()
    with pytest.raises(AppError) as exc_info:
        await svc.execute(
            path=sample_file,
            task_type="DRUG_MATCHING",
            labels=[],
            asset_id="test_asset_6",
            model_id="text_drug_matching"
        )
    assert exc_info.value.code == "IDENTIFICATION_NAME_REQUIRED"


@pytest.mark.asyncio
async def test_7_image_annotation_regression():
    from app.agent.graphs.agentic_pipeline_graph import discover_capabilities_node
    from app.agent.intent import ParsedIntent
    runtime = InferenceRuntime(registry=create_registry_from_settings(get_settings()))
    set_runtime(runtime)
    intent = ParsedIntent(user_request="detect objects", task_type="detection", requested_labels=["car", "person"])
    fake_state = {
        "project_snapshot": {"modality": "image", "task_type": "object_detection"},
        "asset_snapshot": {"id": "test_img"},
        "user_request": "detect objects",
        "parsed_intent": intent,
        "runtime": runtime
    }
    result = await discover_capabilities_node(fake_state)
    discovered_caps = result.get("available_capabilities", {})
    discovered_models = result.get("available_models", [])
    assert len(discovered_caps) > 0 or len(discovered_models) > 0
