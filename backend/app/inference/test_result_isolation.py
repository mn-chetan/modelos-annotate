"""Regression coverage for concurrent per-image model result isolation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
import threading
import time

from PIL import Image

from app.inference.contracts import (
    BoundingBoxPercent,
    ModelCapability,
    ModelKey,
    NormalizedDetection,
)
from app.inference.registry import ModelRegistry
from app.services.annotations import AnnotationService


class _IdentityAdapter:
    model_id = "identity-test"
    capabilities = [ModelCapability.DETECTION]
    device = "cpu"

    def __init__(self) -> None:
        self._loaded = False
        self.active = 0
        self.max_active = 0
        self._active_lock = threading.Lock()
        self.execution_ids: list[str] = []

    def load(self) -> None:
        self._loaded = True

    def predict(self, image_path: Path, *, asset_id: str, labels=None, **kwargs):
        self.execution_ids.append(str(kwargs.get("execution_id")))
        with self._active_lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            # Deliberately hold the critical section: an unsafe shared model
            # would overlap here and is what this regression protects.
            time.sleep(0.02)
            color = Image.open(image_path).getpixel((0, 0))
            return [NormalizedDetection(
                id=f"{asset_id}-detection",
                asset_id=asset_id,
                label="red" if color[0] > color[2] else "blue",
                class_id=0,
                bbox=BoundingBoxPercent(10.0, 10.0, 20.0, 20.0),
                confidence=0.91 if color[0] > color[2] else 0.73,
                model_id=self.model_id,
                model_key=ModelKey.YOLO26.value,
                inferred_at=datetime.now(UTC),
            )]
        finally:
            with self._active_lock:
                self.active -= 1


def test_concurrent_images_keep_independent_results(tmp_path: Path) -> None:
    image_a = tmp_path / "image-a.png"
    image_b = tmp_path / "image-b.png"
    image_c = tmp_path / "image-c.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(image_a)
    Image.new("RGB", (8, 8), (0, 0, 255)).save(image_b)
    Image.new("RGB", (8, 8), (0, 255, 0)).save(image_c)

    registry = ModelRegistry()
    adapter = _IdentityAdapter()
    registry.register(ModelKey.YOLO26.value, adapter)

    def run(image: Path, asset_id: str):
        return registry.predict_detections(
            ModelKey.YOLO26.value,
            image,
            asset_id=asset_id,
            labels=["object"],
            execution_options={
                "strategy": "full_image",
                "execution_id": f"execution-{asset_id}",
            },
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        result_a, result_b, result_c = list(pool.map(
            lambda args: run(*args),
            [(image_a, "asset-a"), (image_b, "asset-b"), (image_c, "asset-c")],
        ))

    assert adapter.max_active == 1
    assert result_a[0].asset_id == "asset-a"
    assert result_b[0].asset_id == "asset-b"
    assert result_c[0].asset_id == "asset-c"
    assert result_a[0].label == "red"
    assert result_b[0].label == "blue"
    assert result_c[0].label == "blue"
    assert result_a[0].confidence != result_b[0].confidence
    assert set(adapter.execution_ids) == {
        "execution-asset-a",
        "execution-asset-b",
        "execution-asset-c",
    }
    assert result_a[0].provenance["execution_id"] == "execution-asset-a"
    assert result_b[0].provenance["execution_id"] == "execution-asset-b"
    assert result_c[0].provenance["execution_id"] == "execution-asset-c"


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, length=None):
        return list(self.rows)


class _Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    @staticmethod
    def _matches(row, query):
        for key, expected in query.items():
            if isinstance(expected, dict) and "$ne" in expected:
                if row.get(key) == expected["$ne"]:
                    return False
            elif row.get(key) != expected:
                return False
        return True

    async def find_one(self, query):
        return next((row for row in self.rows if self._matches(row, query)), None)

    def find(self, query):
        return _Cursor([row for row in self.rows if self._matches(row, query)])

    async def delete_many(self, query):
        self.rows[:] = [row for row in self.rows if not self._matches(row, query)]

    async def insert_many(self, rows):
        self.rows.extend(dict(row) for row in rows)

    async def update_one(self, query, update):
        row = await self.find_one(query)
        if row and "$set" in update:
            row.update(update["$set"])


class _ResultDb:
    def __init__(self):
        self.assets = _Collection([
            {"id": "asset-a", "project_id": "project-1", "status": "uploaded"},
            {"id": "asset-b", "project_id": "project-1", "status": "uploaded"},
        ])
        self.projects = _Collection([{"id": "project-1", "labels": ["red", "blue"]}])
        self.annotations = _Collection()


def test_persisted_annotations_remain_scoped_to_asset_and_job_item():
    """Persistence/readback must not return another image's annotations."""
    import asyncio

    db = _ResultDb()
    service = AnnotationService(db)

    async def persist_and_read():
        await service.replace_ai_detections(
            "asset-a",
            [{"label": "red", "confidence": 0.91, "bbox": [10, 20, 30, 40]}],
            model_id="yolo26",
            project_id="project-1",
            job_item_id="job-item-a",
            batch_id="batch-1",
            run_provenance={"execution_id": "execution-a"},
        )
        await service.replace_ai_detections(
            "asset-b",
            [{"label": "blue", "confidence": 0.73, "bbox": [50, 60, 20, 20]}],
            model_id="yolo26",
            project_id="project-1",
            job_item_id="job-item-b",
            batch_id="batch-1",
            run_provenance={"execution_id": "execution-b"},
        )
        return await service.list_for_asset("asset-a"), await service.list_for_asset("asset-b")

    rows_a, rows_b = asyncio.run(persist_and_read())
    assert [row["label"] for row in rows_a] == ["red"]
    assert [row["label"] for row in rows_b] == ["blue"]
    assert rows_a[0]["asset_id"] == "asset-a"
    assert rows_b[0]["asset_id"] == "asset-b"
    assert rows_a[0]["provenance"]["job_item_id"] == "job-item-a"
    assert rows_b[0]["provenance"]["job_item_id"] == "job-item-b"
    assert rows_a[0]["provenance"]["execution_id"] != rows_b[0]["provenance"]["execution_id"]
