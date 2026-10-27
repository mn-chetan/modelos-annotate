"""Regression tests for persist_and_analytics_node MongoDB asset access.

P0 fix: 'MongoSession' object has no attribute 'assets'

These tests verify that persist_and_analytics_node correctly uses
get_database() / AnnotationService(db) for asset lookup regardless of
whether `session` in the pipeline state is a MongoSession (from worker.py)
or an AsyncIOMotorDatabase (from routes_main.py).

No SQLAlchemy, no fake compatibility layer, no MongoSession.assets.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from app.db.models import MongoSession, MongoDoc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mongo_session() -> MongoSession:
    """Create a MongoSession backed by a MagicMock database."""
    mock_db = MagicMock()
    return MongoSession(db=mock_db)


def _make_minimal_state(
    *,
    session: Any,
    asset_id: str = "test-asset-001",
    project_id: str = "test-project-001",
) -> dict:
    """Build the minimum PipelineState needed by persist_and_analytics_node."""
    return {
        "session": session,
        "merged_detections": [],
        "masks": [],
        "review_decision": None,
        "asset_id": asset_id,
        "project_id": project_id,
        "asset_snapshot": {"id": asset_id},
        "project_snapshot": {"id": project_id, "modality": "image"},
        "batch_id": None,
        "job_id": None,
        "audit_record": None,
        "execution_models": [],
        "models_executed": [],
        "actions_taken": [],
        "timings": {},
        "reprocess_count": 0,
        "planner_source": "agentic",
    }


# ---------------------------------------------------------------------------
# Test: no AttributeError when session is MongoSession (from worker.py path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_node_uses_get_database_not_session_assets_mongo_session():
    """
    REGRESSION: When session is a MongoSession, persist_and_analytics_node
    must NOT call session.assets which raises AttributeError.
    """
    mongo_session = _make_mongo_session()

    assert not hasattr(mongo_session, "assets"), (
        "MongoSession must NOT have an 'assets' attribute; "
        "if it does the original bug has been re-introduced."
    )

    state = _make_minimal_state(session=mongo_session)

    mock_motor_db = MagicMock()
    mock_asset_doc = {
        "id": "test-asset-001",
        "project_id": "test-project-001",
        "status": "pending",
        "filename": "test.jpg",
        "storage_path": "uploads/test.jpg",
    }
    mock_motor_db.assets.find_one = AsyncMock(return_value=mock_asset_doc)
    mock_motor_db.annotations.delete_many = AsyncMock()
    mock_motor_db.annotations.insert_many = AsyncMock()

    replace_result = ([], None)

    with patch("app.db.models.get_database", return_value=mock_motor_db), \
         patch(
             "app.services.annotations.AnnotationService.replace_ai_detections",
             new_callable=AsyncMock,
             return_value=replace_result,
         ), \
         patch(
             "app.services.annotations.AnnotationService._require_asset",
             new_callable=AsyncMock,
             return_value=MongoDoc(mock_asset_doc),
             ), \
             patch(
                 "app.services.annotations.AnnotationService.verify_ai_detections_readback",
                 new_callable=AsyncMock,
             ):
        from app.agent.graphs.agentic_pipeline_graph import persist_and_analytics_node
        result = await persist_and_analytics_node(state)

    assert isinstance(result, dict)
    assert "actions_taken" in result
    assert "persist_and_analytics" in result["actions_taken"]


@pytest.mark.asyncio
async def test_persist_node_works_when_session_is_motor_database():
    """When session is AsyncIOMotorDatabase (routes path), must also work."""
    mock_motor_db = MagicMock()
    mock_motor_db.assets = MagicMock()

    state = _make_minimal_state(session=mock_motor_db)

    mock_asset_doc = {"id": "test-asset-001", "project_id": "test-project-001", "status": "pending"}
    replace_result = ([], None)

    with patch("app.db.models.get_database", return_value=mock_motor_db), \
         patch(
             "app.services.annotations.AnnotationService.replace_ai_detections",
             new_callable=AsyncMock,
             return_value=replace_result,
         ), \
         patch(
             "app.services.annotations.AnnotationService._require_asset",
             new_callable=AsyncMock,
             return_value=MongoDoc(mock_asset_doc),
             ), \
             patch(
                 "app.services.annotations.AnnotationService.verify_ai_detections_readback",
                 new_callable=AsyncMock,
             ):
        from app.agent.graphs.agentic_pipeline_graph import persist_and_analytics_node
        result = await persist_and_analytics_node(state)

    assert isinstance(result, dict)
    assert "persist_and_analytics" in result["actions_taken"]


@pytest.mark.asyncio
async def test_persist_node_records_final_fused_annotation_count_before_returning():
    """The worker must not observe completion before canonical annotations persist."""
    from app.agent.graphs.agentic_pipeline_graph import persist_and_analytics_node

    session = _make_mongo_session()
    state = _make_minimal_state(session=session)
    audit = MagicMock()
    state["audit_record"] = audit
    persisted = [MongoDoc({"id": "ann-1"}), MongoDoc({"id": "ann-2"})]

    mock_db = MagicMock()
    with patch("app.db.models.get_database", return_value=mock_db), \
         patch(
             "app.services.annotations.AnnotationService.replace_ai_detections",
             new_callable=AsyncMock,
             return_value=(persisted, 0.9),
         ), \
         patch(
             "app.services.annotations.AnnotationService._require_asset",
             new_callable=AsyncMock,
             return_value=MongoDoc({"id": "test-asset-001", "status": "pending"}),
             ), \
             patch(
                 "app.services.annotations.AnnotationService.verify_ai_detections_readback",
                 new_callable=AsyncMock,
             ):
        result = await persist_and_analytics_node(state)

    assert "persist_and_analytics" in result["actions_taken"]
    assert result["persisted_count"] == len(persisted)
    assert audit.persisted_annotation_count == len(persisted)
    audit.log_event.assert_called_once_with(
        "persist_and_analytics", {"persisted_count": len(persisted)}
    )


def test_graph_entry_rejects_conflicting_asset_ids():
    from types import SimpleNamespace

    from app.agent.graphs.agentic_pipeline_graph import _resolve_authoritative_asset_id

    with pytest.raises(RuntimeError, match="Asset identity mismatch"):
        _resolve_authoritative_asset_id(
            asset_id="worker-asset",
            asset=SimpleNamespace(id="orm-asset"),
            asset_snapshot={"id": "snapshot-asset"},
        )


@pytest.mark.asyncio
async def test_persist_node_rejects_detection_from_another_asset():
    state = _make_minimal_state(session=_make_mongo_session())
    state["merged_detections"] = [{"asset_id": "foreign-asset"}]

    from app.agent.graphs.agentic_pipeline_graph import persist_and_analytics_node

    with pytest.raises(RuntimeError, match="Refusing to persist detections"):
        await persist_and_analytics_node(state)


@pytest.mark.asyncio
async def test_persist_node_deleted_asset_raises_not_found():
    """Deleted asset must raise NotFoundError, not silently return fake data.

    AnnotationService._require_asset returns None when the asset has status=deleted
    (excluded by the status != deleted filter) and then raises NotFoundError.
    We patch _require_asset directly to simulate this — verifying that
    persist_and_analytics_node propagates the error and does not swallow it.
    """
    from app.errors import NotFoundError

    mongo_session = _make_mongo_session()
    state = _make_minimal_state(session=mongo_session, asset_id="deleted-asset-999")

    mock_motor_db = MagicMock()

    with patch("app.db.models.get_database", return_value=mock_motor_db), \
         patch(
             "app.services.annotations.AnnotationService._require_asset",
             new_callable=AsyncMock,
             side_effect=NotFoundError("Asset", "deleted-asset-999"),
         ):
        from app.agent.graphs.agentic_pipeline_graph import persist_and_analytics_node
        with pytest.raises(NotFoundError):
            await persist_and_analytics_node(state)


@pytest.mark.asyncio
async def test_persist_node_missing_asset_raises_not_found():
    """Missing asset must raise NotFoundError, not continue with fabricated data.

    When find_one returns None (asset does not exist), _require_asset raises
    NotFoundError. We patch it directly to verify persist_and_analytics_node
    propagates the error correctly and does not fabricate an asset.
    """
    from app.errors import NotFoundError

    mongo_session = _make_mongo_session()
    state = _make_minimal_state(session=mongo_session, asset_id="nonexistent-asset")

    mock_motor_db = MagicMock()

    with patch("app.db.models.get_database", return_value=mock_motor_db), \
         patch(
             "app.services.annotations.AnnotationService._require_asset",
             new_callable=AsyncMock,
             side_effect=NotFoundError("Asset", "nonexistent-asset"),
         ):
        from app.agent.graphs.agentic_pipeline_graph import persist_and_analytics_node
        with pytest.raises(NotFoundError):
            await persist_and_analytics_node(state)


def test_mongo_session_has_no_assets_attribute():
    """Contract test: MongoSession must NOT have assets/annotations attributes."""
    session = _make_mongo_session()
    assert not hasattr(session, "assets"), (
        "MongoSession.assets has been re-added — this re-introduces the P0 bug."
    )
    assert not hasattr(session, "annotations"), (
        "MongoSession.annotations has been re-added — this re-introduces the bug."
    )


@pytest.mark.asyncio
async def test_calculate_hitl_execution_metrics_structure():
    """Test calculate_hitl_execution_metrics returns required 5 metric fields and DATA_NOT_AVAILABLE fallback when empty."""
    from app.services.qc_service import calculate_hitl_execution_metrics

    mock_db = MagicMock()
    mock_find_empty = MagicMock()
    mock_find_empty.to_list = AsyncMock(return_value=[])
    mock_db.review_notes.find.return_value = mock_find_empty
    mock_db.assets.find.return_value = mock_find_empty
    mock_db.decisions.find.return_value = mock_find_empty
    mock_db.annotations.find.return_value = mock_find_empty
    mock_db.audit_events.find.return_value = mock_find_empty

    metrics = await calculate_hitl_execution_metrics(mock_db, "test-project-001")

    assert "audit_pass_rate" in metrics
    assert "mean_iou" in metrics
    assert "defect_leakage" in metrics
    assert "inter_annotator_agreement" in metrics
    assert "iou_acceptance_distribution" in metrics

    assert metrics["audit_pass_rate"]["status"] == "DATA_NOT_AVAILABLE"
    assert metrics["audit_pass_rate"]["reason"] == "No completed QA audits available"
    assert metrics["mean_iou"]["status"] == "DATA_NOT_AVAILABLE"
    assert metrics["mean_iou"]["reason"] == "No verified ground-truth geometry available"
    assert metrics["defect_leakage"]["status"] == "DATA_NOT_AVAILABLE"
    assert metrics["defect_leakage"]["reason"] == "No authoritative defect leakage evidence available"
    assert metrics["inter_annotator_agreement"]["status"] == "DATA_NOT_AVAILABLE"
    assert metrics["inter_annotator_agreement"]["reason"] == "No independent double-annotation samples available"
    assert metrics["iou_acceptance_distribution"]["status"] == "DATA_NOT_AVAILABLE"
    assert metrics["iou_acceptance_distribution"]["reason"] == "No verified IoU evaluations available"


@pytest.mark.asyncio
async def test_calculate_hitl_execution_metrics_calculations():
    """Test isolated calculations: Audit Pass Rate, Defect Leakage, Mean IoU, Distribution."""
    from app.services.qc_service import calculate_hitl_execution_metrics

    mock_db = MagicMock()
    # 480 PASS, 20 FAIL review notes -> total 500
    review_notes = [{"asset_id": f"a{i}", "qc_decision": "PASS", "checklist": {}} for i in range(480)]
    review_notes.extend([{"asset_id": f"b{i}", "qc_decision": "FAIL", "checklist": {}} for i in range(20)])

    mock_rn = MagicMock()
    mock_rn.to_list = AsyncMock(return_value=review_notes)

    mock_find_empty = MagicMock()
    mock_find_empty.to_list = AsyncMock(return_value=[])

    mock_db.review_notes.find.return_value = mock_rn
    mock_db.assets.find.return_value = mock_find_empty
    mock_db.decisions.find.return_value = mock_find_empty
    mock_db.annotations.find.return_value = mock_find_empty
    mock_db.audit_events.find.return_value = mock_find_empty

    metrics = await calculate_hitl_execution_metrics(mock_db, "test-project-001")

    assert metrics["audit_pass_rate"]["status"] == "AVAILABLE"
    assert metrics["audit_pass_rate"]["value"] == 96.0
    assert metrics["audit_pass_rate"]["passed_audited_samples"] == 480
    assert metrics["audit_pass_rate"]["total_audited_samples"] == 500

    assert metrics["defect_leakage"]["status"] == "AVAILABLE"
    assert metrics["defect_leakage"]["value"] == 4.0
    assert metrics["defect_leakage"]["defective_audited_samples"] == 20
    assert metrics["defect_leakage"]["total_audited_samples"] == 500


@pytest.mark.asyncio
async def test_project_service_cascade_delete():
    """Test ProjectService.delete executes cascade deletion across all project collections."""
    from app.services.projects import ProjectService

    mock_db = MagicMock()
    mock_db.projects.find_one = AsyncMock(return_value={"id": "proj_del_123", "name": "Test Delete Project"})
    mock_db.assets.find.return_value.to_list = AsyncMock(return_value=[])
    
    # Make any collection's delete_many awaitable
    for col in ("projects", "assets", "annotations", "decisions", "audit_events", "review_notes", "model_runs", "batch_jobs", "job_items", "color_maps", "batches", "masks", "project_recons", "taxonomies", "cloud_imports"):
        getattr(mock_db, col).delete_many = AsyncMock()

    svc = ProjectService(mock_db)
    result = await svc.delete("proj_del_123")

    assert result is True
    mock_db.projects.delete_many.assert_called_once_with({"$or": [{"id": "proj_del_123"}, {"_id": "proj_del_123"}]})
    mock_db.assets.delete_many.assert_called_once_with({"project_id": "proj_del_123"})
    mock_db.annotations.delete_many.assert_called_once_with({"project_id": "proj_del_123"})
    mock_db.decisions.delete_many.assert_called_once_with({"project_id": "proj_del_123"})
    mock_db.audit_events.delete_many.assert_called_once_with({"project_id": "proj_del_123"})




