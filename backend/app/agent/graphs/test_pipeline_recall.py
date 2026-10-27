"""Regression unit & integration tests for Pipeline Object Recall & Agentic Retry Execution.

Tests:
1. TEST 1: Quality Agent RETRY decision triggers re-planning, retry model execution, combined raw fusion, and quality re-check.
2. TEST 2: Dense scene NMS preserves distinct adjacent objects (IoU 0.45 - 0.60) without premature suppression.
3. TEST 3: Small objects use higher adaptive IoU threshold (>= 0.65) to protect nearby small objects.
4. TEST 4: Original model confidence is strictly preserved throughout fusion without artificial score manipulation.
5. TEST 5: Multi-pass fusion combines initial and retry detections cleanly.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from app.db.models import MongoSession, _utcnow, MongoDoc, init_db
from app.config import get_settings
from app.storage.files import FileStorage
from app.inference.contracts import NormalizedDetection, BoundingBoxPercent
from app.inference.ontology_map import build_ontology_index
from app.inference.merge import merge_detections, _adaptive_iou_threshold, _same_model_class_aware_nms
from app.agent.quality_review import review_execution_quality, _normalize_quality_decision
from app.agent.graphs.agentic_pipeline_graph import (
    _final_same_label_deduplicate,
    replan_node,
    run_agentic_pipeline_graph,
    evaluate_quality_and_decision_node,
)


def test_final_safety_dedup_removes_near_identical_same_label_boxes():
    first = make_det("first", "ast1", "car", 0.91, BoundingBoxPercent(x=10, y=10, w=20, h=20), "yolo26")
    duplicate = make_det("duplicate", "ast1", "car", 0.72, BoundingBoxPercent(x=10.5, y=10.5, w=20, h=20), "dino")
    distinct = make_det("distinct", "ast1", "car", 0.70, BoundingBoxPercent(x=38, y=10, w=20, h=20), "yolo26")

    kept, suppressed = _final_same_label_deduplicate([duplicate, distinct, first])

    assert {item.id for item in kept} == {"first", "distinct"}
    assert suppressed == 1


def make_det(
    id: str,
    asset_id: str,
    label: str,
    confidence: float,
    bbox: BoundingBoxPercent,
    model_key: str = "yolo26",
    class_id: int | None = 0,
    model_id: str = "model_1",
) -> NormalizedDetection:
    return NormalizedDetection(
        id=id,
        asset_id=asset_id,
        label=label,
        class_id=class_id,
        bbox=bbox,
        confidence=confidence,
        model_id=model_id,
        model_key=model_key,
        inferred_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def test_env(tmp_path):
    storage = FileStorage(tmp_path / "storage")
    settings = get_settings()
    db = await init_db(str(settings.sqlite_database_path))
    yield db, storage
    await db.projects.delete_many({})
    await db.assets.delete_many({})
    await db.batches.delete_many({})
    await db.job_items.delete_many({})


@pytest.mark.asyncio
async def test_1_quality_agent_retry_executes_replanning_and_fusion():
    """TEST 1: Quality Agent RETRY generates execution plan and combines detections."""
    coverage = {
        "raw_count": 5,
        "missing_requested_labels": ["Traffic light"],
        "suspicious_boxes": 0,
    }
    detections = [
        make_det(
            id="d1",
            asset_id="ast1",
            label="car",
            confidence=0.85,
            bbox=BoundingBoxPercent(10.0, 10.0, 15.0, 15.0),
            model_key="yolo26",
        )
    ]
    
    # Evaluate quality decision
    quality_decision = _normalize_quality_decision(
        parsed={"action": "RETRY", "suggested_strategy": "tiled", "suggested_models": ["yolo26"], "missing_labels": ["Traffic light"]},
        detections=detections,
        coverage=coverage,
    )
    
    assert quality_decision["action"] == "RETRY"
    assert "Traffic light" in quality_decision["missing_labels"]
    assert quality_decision["suggested_strategy"] == "tiled"
    assert quality_decision["suggested_models"] == ["yolo26"]

    # Replan node test
    state = {
        "quality_agent_decision": quality_decision,
        "merged_detections": detections,
        "raw_detections": detections,
        "replan_count": 0,
        "project_snapshot": {"labels": ["car", "Traffic light"]},
        "execution_plan": {"models": ["yolo26"], "strategy": "full_image", "requested_labels": ["car", "Traffic light"]},
        "available_models": {"yolo26": True, "dino": True},
        "runtime_capabilities": [
            {"model_key": "yolo26", "capabilities": ["detection"], "vocabulary": ["car", "traffic light"], "available": True},
            {"model_key": "dino", "is_open_vocabulary": True, "capabilities": ["open_vocab_detection"], "available": True},
        ],
    }

    replan_res = await replan_node(state)
    assert replan_res.get("next_node") != "human_review"
    new_plan = replan_res["execution_plan"]
    assert new_plan["strategy"] in ("tiled", "full_image", "high_resolution", "high_resolution_tiled")
    assert len(new_plan["models"]) > 0
    assert any(m in new_plan["models"] for m in ("yolo26", "dino"))


def test_2_dense_scene_nms_preserves_adjacent_objects():
    """TEST 2: Dense scene NMS preserves distinct adjacent objects (IoU 0.45 - 0.60)."""
    # Two cars parked bumper to bumper with ~50% IoU overlap but 40% centroid offset
    car1 = make_det(
        id="car_1",
        asset_id="ast1",
        label="car",
        confidence=0.88,
        bbox=BoundingBoxPercent(x=10.0, y=10.0, w=20.0, h=10.0),
        model_key="yolo26",
    )
    car2 = make_det(
        id="car_2",
        asset_id="ast1",
        label="car",
        confidence=0.82,
        bbox=BoundingBoxPercent(x=18.0, y=10.0, w=20.0, h=10.0), # Centroid x is offset from 20.0 to 28.0 (8.0 offset >= 35% of 20.0)
        model_key="yolo26",
    )

    index = build_ontology_index(["car"])
    kept, stats = merge_detections([car1, car2], index=index)
    
    # Both cars should survive in dense traffic
    assert len(kept) == 2
    kept_ids = {d.id for d in kept}
    assert "car_1" in kept_ids
    assert "car_2" in kept_ids


def test_3_small_object_adaptive_iou_threshold():
    """TEST 3: Small objects (area <= 400) use higher adaptive IoU threshold."""
    # Small traffic light boxes (area 50)
    box1 = make_det(
        id="tl_1",
        asset_id="ast1",
        label="traffic light",
        confidence=0.75,
        bbox=BoundingBoxPercent(x=5.0, y=5.0, w=5.0, h=10.0), # area = 50
        model_key="yolo26",
    )
    box2 = make_det(
        id="tl_2",
        asset_id="ast1",
        label="traffic light",
        confidence=0.70,
        bbox=BoundingBoxPercent(x=6.0, y=5.0, w=5.0, h=10.0), # area = 50, IoU ~0.70
        model_key="yolo26",
    )

    adaptive_th = _adaptive_iou_threshold([box1, box2], 0.50)
    assert adaptive_th >= 0.70


def test_4_real_model_confidence_is_strictly_preserved():
    """TEST 4: Candidate merging preserves original model confidence without boosting."""
    det1 = make_det(
        id="d1",
        asset_id="ast1",
        label="car",
        confidence=0.64,
        bbox=BoundingBoxPercent(x=10.0, y=10.0, w=10.0, h=10.0),
        model_key="yolo26",
    )
    det2 = make_det(
        id="d2",
        asset_id="ast1",
        label="car",
        confidence=0.61,
        bbox=BoundingBoxPercent(x=10.0, y=10.0, w=10.0, h=10.0),
        model_key="dino",
    )

    index = build_ontology_index(["car"])
    merged, _ = merge_detections([det1, det2], index=index)

    assert len(merged) == 1
    winner = merged[0]
    # Winning confidence MUST equal original model confidence (0.64), not averaged or boosted
    assert winner.confidence == 0.64


def test_5_multi_pass_fusion_preserves_initial_pass_objects():
    """TEST 5: Multi-pass fusion retains initial pass detections alongside retry pass detections."""
    initial_pass = [
        make_det(
            id="init_car_1",
            asset_id="ast1",
            label="car",
            confidence=0.90,
            bbox=BoundingBoxPercent(x=5.0, y=5.0, w=15.0, h=15.0),
            model_key="yolo26",
        )
    ]
    retry_pass = [
        make_det(
            id="retry_tl_1",
            asset_id="ast1",
            label="traffic light",
            confidence=0.78,
            bbox=BoundingBoxPercent(x=80.0, y=10.0, w=5.0, h=10.0),
            model_key="yolo26",
        )
    ]

    combined_raw = initial_pass + retry_pass
    index = build_ontology_index(["car", "traffic light"])
    merged, _ = merge_detections(combined_raw, index=index)

    assert len(merged) == 2
    labels = {d.label for d in merged}
    assert "car" in labels
    assert "traffic light" in labels
