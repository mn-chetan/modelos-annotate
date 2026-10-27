from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import torch
from PIL import Image

from app.agent.quality_review import _structured_requested_label_coverage
from app.db.models import MongoDoc, MongoSession
from app.inference.adapters.dino import GroundingDinoAdapter, canonicalize_dino_label
from app.inference.contracts import BoundingBoxPercent, NormalizedDetection
from app.inference.merge import merge_detections
from app.inference.ontology_map import build_ontology_index, map_raw_label


def _detection(label: str, *, asset_id: str = "asset-1", provenance=None):
    return NormalizedDetection(
        id=f"det-{label}",
        asset_id=asset_id,
        label=label,
        class_id=None,
        bbox=BoundingBoxPercent(10, 10, 20, 20),
        confidence=0.9,
        model_id="dino-test",
        model_key="dino",
        inferred_at=datetime.now(UTC),
        provenance=provenance or {"raw_label": label},
    )


def test_dino_auto_rickshaw_aliases_resolve_to_project_auto():
    index = build_ontology_index(["auto"])
    for raw in ("auto-rickshaws", "auto rickshaw", "autorickshaw", "rickshaw", "three-wheeler", "three wheeler"):
        result = map_raw_label(raw, index)
        assert result.accepted is True
        assert result.canonical_label == "auto"


def test_dino_prompt_aliases_map_to_requested_target_without_car_cross_mapping():
    assert canonicalize_dino_label("auto-rickshaws", ["auto"]) == "auto-rickshaws"
    assert canonicalize_dino_label("auto rickshaw", ["auto-rickshaw"]) == "auto-rickshaws"
    assert canonicalize_dino_label("auto rickshaws", ["auto"]) == "auto-rickshaws"
    assert canonicalize_dino_label("auto - rickshaws", ["auto"]) == "auto-rickshaws"
    assert canonicalize_dino_label("Unmapped", ["auto"]) == "auto-rickshaws"
    assert canonicalize_dino_label("car", ["auto"]) is None


def test_instruction_phrase_canonicalization_to_car():
    from app.inference.ontology_map import clean_canonical_label
    assert clean_canonical_label("Cars should be identified") == "car"
    assert clean_canonical_label("car should be identified") == "car"
    assert clean_canonical_label("Please identify all cars") == "car"
    assert clean_canonical_label("Cars to be detected in traffic images") == "car"
    assert clean_canonical_label("Pedestrians should be identified") == "person"
    assert clean_canonical_label("Traffic lights should be identified") == "traffic light"


def test_dino_canonicalize_with_instruction_phrase():
    assert canonicalize_dino_label("car", ["Cars should be identified"]) == "cars"
    assert canonicalize_dino_label("cars", ["Cars should be identified"]) == "cars"


def test_ontology_normalization_cleans_instruction_phrases():
    from app.services.projects import validate_and_normalize_ontology
    is_valid, concepts, labels, status = validate_and_normalize_ontology(
        None,
        ["Cars should be identified"],
        "object_detection",
    )
    assert is_valid is True
    assert labels == ["car"]
    assert concepts[0]["name"] == "car"


def test_fusion_merges_yolo_car_and_dino_instruction_label():
    yolo_det = NormalizedDetection(
        id="yolo-car-1",
        asset_id="asset-1",
        label="car",
        class_id=None,
        bbox=BoundingBoxPercent(10, 10, 20, 20),
        confidence=0.98,
        model_id="yolo26",
        model_key="yolo26",
        inferred_at=datetime.now(UTC),
    )
    dino_det = NormalizedDetection(
        id="dino-car-1",
        asset_id="asset-1",
        label="Cars should be identified",
        class_id=None,
        bbox=BoundingBoxPercent(10.5, 10.2, 19.8, 19.9),
        confidence=0.54,
        model_id="dino",
        model_key="dino",
        inferred_at=datetime.now(UTC),
        provenance={"raw_label": "Cars should be identified", "mapping_status": "MAPPED", "canonical_label": "car"},
    )
    index = build_ontology_index(["Cars should be identified"])
    merged, stats = merge_detections([yolo_det, dino_det], index, iou_threshold=0.5)
    assert len(merged) == 1
    assert merged[0].label == "car"


def test_mapped_dino_detection_reaches_fusion_and_keeps_asset_id():
    merged, stats = merge_detections(
        [_detection("auto-rickshaws", asset_id="authoritative-asset")],
        build_ontology_index(["auto"]),
    )
    assert len(merged) == 1
    assert merged[0].label == "auto"
    assert merged[0].asset_id == "authoritative-asset"
    assert stats.mapped_accepted == 1


def test_unusable_dino_label_uses_requested_prompt_in_fusion():
    detections = [
        _detection(
            "Unmapped",
            asset_id="authoritative-asset",
            provenance={
                "raw_label": "Unmapped",
                "requested_label": ["auto"],
                "mapping_status": "UNMAPPED_DETECTION",
            },
        ),
        NormalizedDetection(
            id="det-auto-2",
            asset_id="authoritative-asset",
            label="Unmapped",
            class_id=None,
            bbox=BoundingBoxPercent(60, 60, 20, 20),
            confidence=0.8,
            model_id="dino-test",
            model_key="dino",
            inferred_at=datetime.now(UTC),
            provenance={
                "raw_label": "Unmapped",
                "requested_label": "auto",
                "mapping_status": "UNMAPPED_DETECTION",
            },
        ),
    ]
    merged, stats = merge_detections(detections, build_ontology_index(["auto"]))
    assert stats.mapped_accepted == 2
    assert stats.unmapped_suppressed == 0
    assert stats.final_candidates == 2
    assert {d.label for d in merged} == {"auto"}
    assert {d.asset_id for d in merged} == {"authoritative-asset"}


def test_unmapped_dino_evidence_is_uncertain_not_true_negative():
    coverage = _structured_requested_label_coverage(
        requested_labels=["auto"],
        detections=[],
        execution_plan={
            "executed_models": ["dino"],
            "runtime_capabilities": [{
                "model_key": "dino",
                "capabilities": ["open_vocab_detection"],
                "vocabulary": [],
            }],
            "execution_history": [{"actions": [{"model": "dino", "labels": ["auto"]}]}],
            "unmapped_detections": [{
                "raw_label": "mystery vehicle",
                "requested_label": "auto",
                "mapping_status": "UNMAPPED_DETECTION",
            }],
        },
    )
    assert coverage[0]["status"] == "UNCERTAIN"
    assert coverage[0]["true_negative"] is False


@pytest.mark.asyncio
async def test_two_requested_auto_dino_detections_reach_persistence(tmp_path):
    class FakeModel:
        def __call__(self, **inputs):
            return object()

    class FakeProcessor:
        def __call__(self, *, images, text, return_tensors):
            assert text == "auto-rickshaws ."
            return {
                "input_ids": torch.zeros((1, 2), dtype=torch.long),
                "pixel_values": torch.zeros((1, 3, images.height, images.width)),
            }

        def post_process_grounded_object_detection(self, *args, **kwargs):
            return [{
                "boxes": torch.tensor([[10, 10, 30, 30], [60, 60, 80, 80]], dtype=torch.float32),
                "scores": torch.tensor([0.9, 0.8]),
                "text_labels": ["Unmapped", "Unmapped"],
            }]

    image_path = tmp_path / "dino-auto-regression.png"
    Image.new("RGB", (100, 100)).save(image_path)
    adapter = GroundingDinoAdapter(device_preference="cpu")
    adapter._loaded = True
    adapter._model = FakeModel()
    adapter._processor = FakeProcessor()

    detections = adapter.predict(image_path, asset_id="authoritative-asset", labels=["auto"])
    mapped_count = sum(
        detection.provenance.get("mapping_status") == "MAPPED"
        for detection in detections
    )
    assert mapped_count == 2
    assert {detection.label for detection in detections} == {"auto"}
    assert {detection.provenance["canonical_label"] for detection in detections} == {"auto"}
    assert {detection.asset_id for detection in detections} == {"authoritative-asset"}

    merged, stats = merge_detections(detections, build_ontology_index(["auto"]))
    assert stats.final_candidates == 2
    assert stats.mapped_accepted == 2
    assert {detection.label for detection in merged} == {"auto"}

    state = {
        "session": MongoSession(db=MagicMock()),
        "merged_detections": merged,
        "masks": [],
        "review_decision": None,
        "asset_id": "authoritative-asset",
        "project_id": "project-1",
        "asset_snapshot": {"id": "authoritative-asset"},
        "project_snapshot": {"id": "project-1", "modality": "image"},
        "batch_id": "batch-1",
        "job_id": "job-1",
        "audit_record": None,
        "execution_models": ["dino"],
        "models_executed": ["dino"],
        "actions_taken": [],
        "timings": {},
        "reprocess_count": 0,
        "planner_source": "agentic",
    }
    persisted = [MongoDoc({"id": "annotation-1"}), MongoDoc({"id": "annotation-2"})]
    mock_db = MagicMock()
    with patch("app.db.models.get_database", return_value=mock_db), \
         patch(
             "app.services.annotations.AnnotationService.replace_ai_detections",
             new_callable=AsyncMock,
             return_value=(persisted, 0.85),
         ) as replace_detections, \
         patch(
             "app.services.annotations.AnnotationService._require_asset",
             new_callable=AsyncMock,
             return_value=MongoDoc({"id": "authoritative-asset", "project_id": "project-1", "status": "pending"}),
         ), \
         patch(
             "app.services.annotations.AnnotationService.verify_ai_detections_readback",
             new_callable=AsyncMock,
         ):
        from app.agent.graphs.agentic_pipeline_graph import persist_and_analytics_node

        result = await persist_and_analytics_node(state)

    assert len(merged) == 2
    assert len(replace_detections.await_args.kwargs["raw_detections"]) == 2
    assert replace_detections.await_args.kwargs["asset_id"] == "authoritative-asset"
    assert result["persisted_count"] == 2
