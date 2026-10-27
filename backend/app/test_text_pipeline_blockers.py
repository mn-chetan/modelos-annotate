"""Targeted validation tests for text agentic pipeline routing and persistence fixes."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.services.text_capability import normalize_text_task, TextCapabilityService
from app.agent.graphs.agentic_pipeline_graph import (
    create_execution_plan_node,
    execute_model_node,
    evaluate_quality_and_decision_node,
    replan_node,
    persist_and_analytics_node,
)


def test_task_normalization():
    print("--- Test 1: Task Normalization ---")
    sentiment_variants = [
        "Sentiment",
        "sentiment",
        "Sentiment Analysis",
        "sentiment_analysis",
        "Sentiment Annotation",
    ]
    for s in sentiment_variants:
        norm_task, cap = normalize_text_task(s)
        assert norm_task == "SENTIMENT_ANALYSIS", f"Expected SENTIMENT_ANALYSIS for {s}, got {norm_task}"
        assert cap == "text_sentiment_analysis", f"Expected text_sentiment_analysis for {s}, got {cap}"
    print("[PASS] All sentiment variants normalized correctly to text_sentiment_analysis")

    ner_variants = [
        "NER",
        "ner",
        "Named Entity Recognition",
        "entity_extraction",
        "NER Annotation",
    ]
    for n in ner_variants:
        norm_task, cap = normalize_text_task(n)
        assert norm_task == "ENTITY_EXTRACTION", f"Expected ENTITY_EXTRACTION for {n}, got {norm_task}"
        assert cap == "text_entity_extraction", f"Expected text_entity_extraction for {n}, got {cap}"
    print("[PASS] All NER variants normalized correctly to text_entity_extraction")

    class_variants = ["Text Classification", "classification", "text_classification"]
    for c in class_variants:
        norm_task, cap = normalize_text_task(c)
        assert norm_task == "TEXT_CLASSIFICATION", f"Expected TEXT_CLASSIFICATION for {c}, got {norm_task}"
        assert cap == "text_classification", f"Expected text_classification for {c}, got {cap}"
    print("[PASS] All Classification variants normalized correctly to text_classification")

    rel_variants = ["Relation Extraction", "relation", "relation_extraction"]
    for r in rel_variants:
        norm_task, cap = normalize_text_task(r)
        assert norm_task == "RELATION_EXTRACTION", f"Expected RELATION_EXTRACTION for {r}, got {norm_task}"
        assert cap == "text_relation_extraction", f"Expected text_relation_extraction for {r}, got {cap}"
    print("[PASS] All Relation variants normalized correctly to text_relation_extraction")


import pytest

@pytest.mark.asyncio
async def test_sentiment_planner_routing():
    print("--- Test 2: Sentiment Planner Routing ---")
    mock_intent = MagicMock()
    mock_intent.task_type = "Sentiment Annotation"
    mock_intent.requested_labels = ["POSITIVE", "NEGATIVE"]

    state = {
        "parsed_intent": mock_intent,
        "available_models": {},
        "capability_gaps": [],
        "project_snapshot": {
            "modality": "text",
            "task_type": "Sentiment Annotation",
            "labels": ["POSITIVE", "NEGATIVE"],
        },
        "asset_snapshot": {"id": "asset-test-123"},
        "timings": {},
    }

    res = await create_execution_plan_node(state)
    plan = res["execution_plan"]
    assert plan["models"] == ["text_sentiment_analysis"], f"Expected text_sentiment_analysis in models, got {plan['models']}"
    assert plan["task_type"] == "SENTIMENT_ANALYSIS", f"Expected SENTIMENT_ANALYSIS task_type, got {plan['task_type']}"
    assert plan["actions"][0]["model"] == "text_sentiment_analysis"
    print("[PASS] Sentiment planner routing selects text_sentiment_analysis")


@pytest.mark.asyncio
async def test_firebase_persistence_no_crash():
    print("--- Test 3: Firebase Persistence Fix ---")
    mock_col = AsyncMock()
    mock_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
    mock_col.insert_many = AsyncMock(return_value=MagicMock())

    class MockFirebaseSession:
        def __getitem__(self, name: str):
            if name == "annotations":
                return mock_col
            raise KeyError(name)

    session = MockFirebaseSession()

    state = {
        "session": session,
        "asset_id": "asset-123",
        "project_id": "proj-456",
        "project_snapshot": {"modality": "text"},
        "asset_snapshot": {"id": "asset-123"},
        "text_annotations": [
            {
                "id": "asset-123:document",
                "asset_id": "asset-123",
                "label": "POSITIVE",
                "geometry_type": "text_classification",
                "geometry": {"start": 0, "end": 50, "text": "Sample text"},
                "confidence": 0.95,
                "model_id": "text_sentiment_analysis",
            }
        ],
        "audit_record": MagicMock(),
        "timings": {},
    }

    res = await persist_and_analytics_node(state)
    assert res["final_status"] == "persisted"
    assert res["persisted_count"] == 1
    assert res["persisted_annotation_count"] == 1
    assert state["audit_record"].persisted_annotation_count == 1
    mock_col.delete_many.assert_called_once_with({"asset_id": "asset-123", "source": "ai"})
    mock_col.insert_many.assert_called_once()
    print("[PASS] Firebase persistence executed delete_many and insert_many and set persisted_annotation_count=1")


@pytest.mark.asyncio
async def test_semantic_conflict_blocks_auto_approve_and_requests_replan(monkeypatch):
    async def fake_verify(**kwargs):
        return {
            "available": True,
            "verifications": [{
                "annotation_id": "ann-1",
                "semantic_validity": False,
                "ontology_validity": True,
                "contextual_validity": False,
                "conflict_detected": True,
                "alternative_label": "Order ID",
                "reason": "Context identifies an order identifier.",
                "verification_confidence": 0.98,
                "decision": "INVALID",
            }],
        }

    monkeypatch.setattr("app.services.text_capability.verify_text_annotations", fake_verify)
    state = {
        "project_snapshot": {"modality": "text", "task_type": "NER"},
        "execution_plan": {"models": ["text_entity_extraction"], "requested_labels": ["Product", "Order ID"]},
        "text_result": {"text": "We checked order ORD-45821."},
        "text_annotations": [{
            "id": "ann-1",
            "label": "Product",
            "text_span": {"start": 18, "end": 27, "text": "ORD-45821"},
            "confidence": 1.0,
        }],
        "timings": {},
        "audit_record": MagicMock(),
    }

    result = await evaluate_quality_and_decision_node(state)
    assert result["quality_agent_decision"]["action"] == "RETRY"
    assert result["quality_agent_decision"]["missing_labels"] == ["Order ID"]
    assert result["review_decision"].status == "REPLAN"
    assert result["review_decision"].human_review_required is False
    assert result["quality_report"]["semantic_conflicts"]


def _quality_state(confidence: float, *, replan_count: int = 0):
    return {
        "project_snapshot": {"modality": "text", "task_type": "NER"},
        "execution_plan": {"models": ["text_entity_extraction"], "requested_labels": ["Person"]},
        "text_result": {"text": "Alex Doe visited Hyderabad."},
        "text_annotations": [{
            "id": "ann-1",
            "label": "Person",
            "text_span": {"start": 0, "end": 8, "text": "Alex Doe"},
            "confidence": confidence,
        }],
        "timings": {},
        "replan_count": replan_count,
        "max_replans": 1,
        "audit_record": MagicMock(),
    }


@pytest.mark.asyncio
async def test_quality_decision_confidence_and_semantics_are_independent(monkeypatch):
    async def valid_verify(**kwargs):
        return {"available": True, "verifications": [{
            "annotation_id": "ann-1", "semantic_validity": True,
            "ontology_validity": True, "contextual_validity": True,
            "conflict_detected": False, "alternative_label": None,
            "reason": "Context supports the label.",
            "verification_confidence": 0.99, "decision": "VALID",
        }]}

    monkeypatch.setattr("app.services.text_capability.verify_text_annotations", valid_verify)
    high = await evaluate_quality_and_decision_node(_quality_state(0.98))
    assert high["quality_agent_decision"]["action"] == "APPROVE"
    assert high["review_decision"].status == "AUTO_APPROVE"

    low = await evaluate_quality_and_decision_node(_quality_state(0.91))
    assert low["quality_agent_decision"]["action"] == "HUMAN_REVIEW"
    assert low["review_decision"].status == "HUMAN_REVIEW"


@pytest.mark.asyncio
async def test_semantic_conflict_after_replan_routes_to_human_review(monkeypatch):
    async def still_invalid(**kwargs):
        return {"available": True, "verifications": [{
            "annotation_id": "ann-1", "semantic_validity": False,
            "ontology_validity": True, "contextual_validity": False,
            "conflict_detected": True, "alternative_label": "Order ID",
            "reason": "Unresolved context conflict.",
            "verification_confidence": 0.98, "decision": "INVALID",
        }]}

    monkeypatch.setattr("app.services.text_capability.verify_text_annotations", still_invalid)
    result = await evaluate_quality_and_decision_node(_quality_state(1.0, replan_count=1))
    assert result["quality_agent_decision"]["action"] == "HUMAN_REVIEW"
    assert result["review_decision"].status == "HUMAN_REVIEW"


@pytest.mark.asyncio
async def test_successful_replan_can_auto_approve(monkeypatch):
    async def invalid_verify(**kwargs):
        return {"available": True, "verifications": [{
            "annotation_id": "ann-1", "semantic_validity": False,
            "ontology_validity": True, "contextual_validity": False,
            "conflict_detected": True, "alternative_label": "Order ID",
            "reason": "Semantic mismatch.", "verification_confidence": 0.98,
            "decision": "INVALID",
        }]}

    monkeypatch.setattr("app.services.text_capability.verify_text_annotations", invalid_verify)
    state = _quality_state(1.0)
    first = await evaluate_quality_and_decision_node(state)
    state.update(first)
    replanned = await replan_node(state)
    assert replanned["execution_plan"]["requested_labels"] == ["Person", "Order ID"]
    state.update(replanned)
    state["text_annotations"][0]["label"] = "Order ID"

    async def valid_verify(**kwargs):
        return {"available": True, "verifications": [{
            "annotation_id": "ann-1", "semantic_validity": True,
            "ontology_validity": True, "contextual_validity": True,
            "conflict_detected": False, "alternative_label": None,
            "reason": "Corrected label is contextually supported.",
            "verification_confidence": 0.99, "decision": "VALID",
        }]}

    monkeypatch.setattr("app.services.text_capability.verify_text_annotations", valid_verify)
    final = await evaluate_quality_and_decision_node(state)
    assert final["quality_agent_decision"]["action"] == "APPROVE"
    assert final["review_decision"].status == "AUTO_APPROVE"


@pytest.mark.asyncio
async def test_medical_sentiment_rules_regression():
    print("--- Test 4: Medical Report Sentiment Regression ---")
    from app.text_backend.schemas.source import SourceDocument, PageText
    from app.text_backend.services.gemini_service import GeminiService
    from app.text_backend.services.sentiment_service import SentimentService

    cases = [
        ("The patient visited the hospital for a routine checkup.", "NEUTRAL"),
        ("The patient has persistent headaches and dizziness.", "NEUTRAL"),
        ("The patient is unhappy with the hospital's treatment.", "NEGATIVE"),
        ("The patient is very satisfied with the hospital's treatment.", "POSITIVE"),
        ("The patient reported severe pain but praised the doctor for providing excellent care.", "POSITIVE"),
        ("The report records a diagnosis of a serious illness.", "NEUTRAL"),
        ("Medical_Report Patient Name: Meera Joshi visited Apollo Hospital in Chennai on 4 October 2026 following complaints of persistent headaches and dizziness.", "NEUTRAL"),
    ]
    service = SentimentService(GeminiService())
    for text, expected in cases:
        doc = SourceDocument(source_type="TEXT", extracted_text=text, pages=[PageText(page=1, text=text)])
        res = await service.analyze(doc, analysis_level="document")
        assert res.sentiment == expected, f"Failed on '{text}': expected {expected}, got {res.sentiment} ({res.reason})"
    print("[PASS] All medical report sentiment regression test cases passed!")


def run_all_tests():
    test_task_normalization()
    asyncio.run(test_sentiment_planner_routing())
    asyncio.run(test_firebase_persistence_no_crash())
    asyncio.run(test_medical_sentiment_rules_regression())
    print("\nALL TARGETED PIPELINE TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_all_tests()
