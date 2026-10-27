from __future__ import annotations

import numpy as np

from app.inference.adapters.yolo26 import Yolo26Adapter
from app.inference.merge import merge_detections
from app.inference.ontology_map import build_ontology_index


class _Tensor:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def numpy(self):
        return np.asarray(self.value)

    def astype(self, dtype):
        return self


class _Boxes:
    def __init__(self, boxes, confidences, classes):
        self.xyxy = _Tensor(boxes)
        self.conf = _Tensor(confidences)
        self.cls = _Tensor(classes)


class _Result:
    def __init__(self, boxes, names, orig_shape=(100, 100)):
        self.boxes = _Boxes(boxes, [0.213], [0])
        self.names = names
        self.orig_shape = orig_shape


def _adapter() -> Yolo26Adapter:
    adapter = Yolo26Adapter.__new__(Yolo26Adapter)
    adapter.key = "yolo26"
    adapter.model_id = "test-yolo26"
    return adapter


def test_tiled_detection_above_threshold_survives_label_filter_and_restoration():
    result = _Result([[10, 20, 50, 70]], {0: "bus"})

    detections = _adapter()._normalize_result(
        result=result,
        asset_id="asset-1",
        image_width=200,
        image_height=200,
        offset_x=50.0,
        offset_y=25.0,
        source_width=100,
        source_height=100,
        tile_id=3,
        strategy="tiled",
        labels=["bus", "truck"],
        confidence_threshold=0.20,
        plan_source="agent",
        plan_reason="missing bus",
    )

    assert len(detections) == 1
    assert detections[0].label == "bus"
    assert detections[0].confidence == 0.213
    assert detections[0].provenance["global_xyxy"] == [60.0, 45.0, 100.0, 95.0]
    fused, _ = merge_detections(detections, build_ontology_index(["bus", "truck"]))
    assert len(fused) == 1
    assert fused[0].label == "bus"


def test_tiled_model_input_coordinates_are_scaled_before_offset():
    result = _Result([[20, 40, 80, 160]], ["truck"], orig_shape=(200, 200))
    detections = _adapter()._normalize_result(
        result=result,
        asset_id="asset-1",
        image_width=300,
        image_height=300,
        offset_x=100.0,
        offset_y=50.0,
        source_width=100,
        source_height=200,
        tile_id=1,
        strategy="tiled",
        labels=["truck"],
        confidence_threshold=0.20,
        plan_source="agent",
        plan_reason="missing truck",
    )

    assert len(detections) == 1
    assert detections[0].provenance["global_xyxy"] == [110.0, 90.0, 140.0, 210.0]
