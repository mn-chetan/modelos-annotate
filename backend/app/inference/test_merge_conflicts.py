from datetime import UTC, datetime

from app.inference.contracts import BoundingBoxPercent, NormalizedDetection
from app.inference.merge import merge_detections
from app.inference.ontology_map import build_ontology_index


def _det(label: str, confidence: float, model: str) -> NormalizedDetection:
    return NormalizedDetection(
        id=f"{model}-{label}",
        asset_id="asset-1",
        label=label,
        class_id=None,
        bbox=BoundingBoxPercent(10, 10, 40, 30),
        confidence=confidence,
        model_id=model,
        model_key=model,
        inferred_at=datetime.now(UTC),
        provenance={"execution_id": f"exec-{model}"},
    )


def test_ambiguous_vehicle_conflict_is_preserved_as_unresolved():
    merged, stats = merge_detections(
        [_det("car", 0.80, "yolo26"), _det("truck", 0.76, "dino")],
        build_ontology_index(["car", "truck"]),
    )

    assert len(merged) == 1
    assert stats.conflict_records[0]["resolution_status"] == "unresolved"
    assert merged[0].provenance["semantic_conflict"] is True


def test_meaningful_vehicle_confidence_difference_can_resolve_conflict():
    _, stats = merge_detections(
        [_det("car", 0.95, "yolo26"), _det("truck", 0.60, "dino")],
        build_ontology_index(["car", "truck"]),
    )

    assert stats.conflict_records[0]["resolution_status"] == "resolved"


def test_cross_model_plural_labels_and_small_boxes_are_fused():
    """Equivalent detector labels must produce one canonical object."""
    yolo = NormalizedDetection(
        id="yolo-car",
        asset_id="asset-1",
        label="cars",
        class_id=None,
        bbox=BoundingBoxPercent(10, 10, 10, 10),
        confidence=0.82,
        model_id="yolo",
        model_key="yolo26",
        inferred_at=datetime.now(UTC),
    )
    dino = NormalizedDetection(
        id="dino-car",
        asset_id="asset-1",
        label="car",
        class_id=None,
        bbox=BoundingBoxPercent(13, 10, 10, 10),
        confidence=0.78,
        model_id="dino",
        model_key="dino",
        inferred_at=datetime.now(UTC),
    )

    merged, stats = merge_detections(
        [yolo, dino],
        build_ontology_index(["car"]),
        iou_threshold=0.45,
    )

    assert len(merged) == 1
    assert merged[0].label == "car"
    assert merged[0].provenance["model_agreement"] is True
    assert stats.duplicates_suppressed == 1
