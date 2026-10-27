from __future__ import annotations

from app.config import Settings
from app.inference.registry import create_registry_from_settings


def test_startup_loads_all_configured_vision_models_and_is_fault_isolated(monkeypatch):
    settings = Settings(DEBUG=False, SKIP_MODEL_LOAD=False, FORCE_FAKE=True)
    registry = create_registry_from_settings(settings, force_fake=True)

    failing = registry._adapters["dino"]

    def fail_load():
        raise RuntimeError("checkpoint unavailable")

    monkeypatch.setattr(failing, "load", fail_load)
    registry.load_eager()
    statuses = {status.key: status for status in registry.status()}

    assert statuses["yolo26"].availability == "available"
    assert statuses["faster_rcnn"].availability == "available"
    assert statuses["dino"].availability == "unavailable"
    assert statuses["dino"].error == "checkpoint unavailable"
    assert statuses["florence"].availability == "available"
    assert statuses["sam2"].availability == "available"
    assert statuses["clip"].availability == "available"


def test_startup_load_is_idempotent_for_loaded_adapters():
    settings = Settings(DEBUG=False, SKIP_MODEL_LOAD=False, FORCE_FAKE=True)
    registry = create_registry_from_settings(settings, force_fake=True)
    registry.load_eager()
    first = {status.key: status.load_duration_ms for status in registry.status()}
    registry.load_eager()
    second = {status.key: status.load_duration_ms for status in registry.status()}
    assert first == second
