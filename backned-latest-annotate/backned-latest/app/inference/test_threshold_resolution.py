from __future__ import annotations

from pathlib import Path

from app.inference.registry import ModelRegistry


class _Adapter:
    confidence_threshold = 0.20
    _loaded = True
    model_id = "test-model"

    def __init__(self) -> None:
        self.received: list[float | None] = []

    def predict(self, image_path: Path, *, asset_id: str, labels=None, confidence_threshold=None, **kwargs):
        self.received.append(confidence_threshold)
        return []


def _registry(adapter: _Adapter) -> ModelRegistry:
    registry = ModelRegistry()
    registry.register("yolo26", adapter)
    return registry


def test_closed_set_agent_threshold_is_clamped_to_production_floor(tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"test")
    adapter = _Adapter()

    _registry(adapter).predict_detections(
        "yolo26", image, asset_id="asset-1",
        execution_options={"execution_id": "e1", "confidence_threshold": 0.20},
    )
    _registry(adapter).predict_detections(
        "yolo26", image, asset_id="asset-1",
        execution_options={"execution_id": "e2", "confidence_threshold": 0.50},
    )

    assert adapter.received == [0.50, 0.50]


def test_missing_agent_threshold_uses_model_default(tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"test")
    adapter = _Adapter()

    _registry(adapter).predict_detections(
        "yolo26", image, asset_id="asset-1",
        execution_options={"execution_id": "e1"},
    )

    assert adapter.received == [0.50]
