"""Comprehensive tests for Expected Output Format as authoritative dataset export format.

Validates:
1. Expected Output Format persisted on project creation (COCO JSON, YOLO, Pascal VOC, LabelMe, CreateML, CSV, JSON).
2. Value survives page refresh / retrieval (GET /projects/{id}).
3. Export resolves from persisted Expected Output Format when no format query param is supplied.
4. Export validates explicit format against project's configured Expected Output Format.
5. All 7 target formats generate valid structures:
   - COCO JSON (valid COCO JSON structure in zip)
   - YOLO (valid classes.txt, data.yaml, normalized label coords in zip)
   - Pascal VOC (valid XML with <annotation><size><object><bndbox>)
   - LabelMe (valid LabelMe JSON with shapes, points)
   - CreateML (valid CreateML JSON with image, annotations, coordinates)
   - CSV (valid CSV text with correct columns)
   - JSON (valid generic JSON)
6. Only FINAL_APPROVED annotations and approved assets are exported.
7. Unrelated projects are isolated and unaffected by other projects' formats.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
import zipfile
import pytest
from datetime import UTC, datetime
import uuid
from contextlib import asynccontextmanager

from app.db.models import MongoDoc
from app.services.export import ExportService, normalize_export_format
from app.services.projects import ProjectService
from app.api.schemas import ProjectCreate, ProjectUpdate, ExportRequest
from app.storage.files import FileStorage
from app.errors import ValidationAppError


@asynccontextmanager
async def get_test_db(tmp_path):
    from app.db.firebase import FirebaseDatabase
    database = FirebaseDatabase()
    try:
        yield database
    finally:
        await database.close()


def get_mock_storage(tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return FileStorage(storage_dir)


@pytest.mark.asyncio
async def test_normalize_export_format():
    assert normalize_export_format("COCO JSON") == "coco"
    assert normalize_export_format("coco") == "coco"
    assert normalize_export_format("YOLO") == "yolo"
    assert normalize_export_format("YOLO TXT") == "yolo"
    assert normalize_export_format("Pascal VOC") == "pascal_voc"
    assert normalize_export_format("Pascal VOC XML") == "pascal_voc"
    assert normalize_export_format("LabelMe") == "labelme"
    assert normalize_export_format("LabelMe JSON") == "labelme"
    assert normalize_export_format("CreateML") == "createml"
    assert normalize_export_format("CreateML JSON") == "createml"
    assert normalize_export_format("CSV") == "csv"
    assert normalize_export_format("JSON") == "json"
    assert normalize_export_format("Custom JSON") == "json"
    assert normalize_export_format(None, default="coco") == "coco"


@pytest.mark.asyncio
async def test_project_persists_expected_output_format(tmp_path):
    async with get_test_db(tmp_path) as db:
        from app.config import get_settings
        settings = get_settings()
        mock_storage = get_mock_storage(tmp_path)
        svc = ProjectService(db, settings, mock_storage)

        now = datetime.now(UTC)
        # 1. Create with YOLO
        p_yolo = await svc.create(ProjectCreate(
            name=f"Project YOLO Test {now.timestamp()}",
            labels=["car", "person"],
            expected_output_format="YOLO",
        ))
        assert p_yolo["expected_output_format"] == "YOLO"

        # Verify retrieval preserves format
        fetched_yolo = await svc.get(p_yolo["id"])
        assert fetched_yolo["expected_output_format"] == "YOLO"

        # 2. Create with Pascal VOC
        p_voc = await svc.create(ProjectCreate(
            name=f"Project VOC Test {now.timestamp()}",
            labels=["car"],
            expected_output_format="Pascal VOC",
        ))
        assert p_voc["expected_output_format"] == "Pascal VOC"

        # 3. Verify unrelated project is unaffected
        refetched_yolo = await svc.get(p_yolo["id"])
        assert refetched_yolo["expected_output_format"] == "YOLO"

        # 4. Update expected_output_format
        updated_voc = await svc.update(p_voc["id"], ProjectUpdate(expected_output_format="LabelMe"))
        assert updated_voc["expected_output_format"] == "LabelMe"
        refetched_voc = await svc.get(p_voc["id"])
        assert refetched_voc["expected_output_format"] == "LabelMe"


@pytest.mark.asyncio
async def test_export_coco_json_structure(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-coco-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "COCO Test Project",
            "expected_output_format": "COCO JSON",
            "labels": ["car", "truck"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        asset_id = f"asset-coco-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_id,
            "project_id": proj_id,
            "filename": "image_1.jpg",
            "width": 1000,
            "height": 800,
            "review_status": "final_approved",
            "workflow_status": "FINAL_APPROVED",
            "is_locked": True,
            "created_at": now,
        })

        await db.annotations.insert_one({
            "id": f"ann-coco-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_id,
            "label": "car",
            "x": 10.0,
            "y": 20.0,
            "w": 30.0,
            "h": 40.0,
            "source": "human_approved",
            "review_status": "final_approved",
            "status": "active",
            "confidence": 0.98,
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        # When fmt is None, should resolve from project: "COCO JSON" -> "coco"
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        assert media_type == "application/zip"
        assert "coco" in filename
        assert summary["format"] == "COCO"

        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            assert "annotations/instances.json" in zf.namelist()
            coco_json = json.loads(zf.read("annotations/instances.json").decode("utf-8"))
            assert "images" in coco_json
            assert len(coco_json["images"]) == 1
            assert coco_json["images"][0]["file_name"] == "image_1.jpg"
            assert "annotations" in coco_json
            assert len(coco_json["annotations"]) == 1
            ann = coco_json["annotations"][0]
            assert ann["bbox"] == [100.0, 160.0, 300.0, 320.0]
            assert "categories" in coco_json
            assert any(c["name"] == "car" for c in coco_json["categories"])


@pytest.mark.asyncio
async def test_export_yolo_structure(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-yolo-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "YOLO Test Project",
            "expected_output_format": "YOLO",
            "labels": ["person"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        asset_id = f"asset-yolo-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_id,
            "project_id": proj_id,
            "filename": "sample.jpg",
            "width": 640,
            "height": 480,
            "review_status": "final_approved",
            "is_locked": True,
            "created_at": now,
        })

        await db.annotations.insert_one({
            "id": f"ann-yolo-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_id,
            "label": "person",
            "x": 20.0,
            "y": 20.0,
            "w": 40.0,
            "h": 60.0,
            "source": "human_approved",
            "review_status": "final_approved",
            "status": "active",
            "confidence": 0.95,
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        # Resolves from project: "YOLO" -> "yolo"
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        assert media_type == "application/zip"
        assert "yolo" in filename
        assert summary["format"] == "YOLO"

        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            assert "classes.txt" in zf.namelist()
            assert "data.yaml" in zf.namelist()
            assert "labels/sample.txt" in zf.namelist()
            classes = zf.read("classes.txt").decode("utf-8").strip().splitlines()
            assert "person" in classes
            labels = zf.read("labels/sample.txt").decode("utf-8").strip().splitlines()
            assert len(labels) == 1
            parts = labels[0].split()
            assert len(parts) == 5
            assert parts[0] == "0"


@pytest.mark.asyncio
async def test_export_pascal_voc_structure(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-voc-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "Pascal VOC Project",
            "expected_output_format": "Pascal VOC",
            "labels": ["dog"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        asset_id = f"asset-voc-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_id,
            "project_id": proj_id,
            "filename": "dog_photo.jpg",
            "width": 800,
            "height": 600,
            "review_status": "final_approved",
            "is_locked": True,
            "created_at": now,
        })

        await db.annotations.insert_one({
            "id": f"ann-voc-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_id,
            "label": "dog",
            "x": 25.0,
            "y": 25.0,
            "w": 50.0,
            "h": 50.0,
            "source": "human_approved",
            "review_status": "final_approved",
            "status": "active",
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        assert media_type == "application/zip"
        assert "voc" in filename
        assert summary["format"] == "PASCAL_VOC"

        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            assert "annotations/dog_photo.xml" in zf.namelist()
            xml_content = zf.read("annotations/dog_photo.xml").decode("utf-8")
            root = ET.fromstring(xml_content)
            assert root.tag == "annotation"
            assert root.find("filename").text == "dog_photo.jpg"
            assert root.find("size/width").text == "800"
            obj = root.find("object")
            assert obj is not None
            assert obj.find("name").text == "dog"
            bndbox = obj.find("bndbox")
            assert bndbox.find("xmin").text == "200"
            assert bndbox.find("ymin").text == "150"
            assert bndbox.find("xmax").text == "600"
            assert bndbox.find("ymax").text == "450"


@pytest.mark.asyncio
async def test_export_labelme_structure(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-labelme-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "LabelMe Project",
            "expected_output_format": "LabelMe",
            "labels": ["sign"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        asset_id = f"asset-lm-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_id,
            "project_id": proj_id,
            "filename": "sign.png",
            "width": 500,
            "height": 500,
            "review_status": "final_approved",
            "is_locked": True,
            "created_at": now,
        })

        await db.annotations.insert_one({
            "id": f"ann-lm-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_id,
            "label": "sign",
            "x": 10.0,
            "y": 10.0,
            "w": 40.0,
            "h": 40.0,
            "review_status": "final_approved",
            "status": "active",
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        assert media_type == "application/zip"
        assert "labelme" in filename

        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            assert "annotations/sign.json" in zf.namelist()
            doc = json.loads(zf.read("annotations/sign.json").decode("utf-8"))
            assert doc["version"] == "5.0.1"
            assert len(doc["shapes"]) == 1
            assert doc["shapes"][0]["label"] == "sign"
            assert doc["shapes"][0]["shape_type"] == "rectangle"
            assert doc["imageWidth"] == 500
            assert doc["imageHeight"] == 500


@pytest.mark.asyncio
async def test_export_createml_structure(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-cml-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "CreateML Project",
            "expected_output_format": "CreateML",
            "labels": ["box"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        asset_id = f"asset-cml-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_id,
            "project_id": proj_id,
            "filename": "cml.jpg",
            "width": 400,
            "height": 400,
            "review_status": "final_approved",
            "is_locked": True,
            "created_at": now,
        })

        await db.annotations.insert_one({
            "id": f"ann-cml-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_id,
            "label": "box",
            "x": 20.0,
            "y": 20.0,
            "w": 40.0,
            "h": 40.0,
            "review_status": "final_approved",
            "status": "active",
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        assert media_type == "application/zip"
        assert "createml" in filename

        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            assert "annotations.json" in zf.namelist()
            doc = json.loads(zf.read("annotations.json").decode("utf-8"))
            assert isinstance(doc, list)
            assert len(doc) == 1
            assert doc[0]["image"] == "cml.jpg"
            assert len(doc[0]["annotations"]) == 1
            coords = doc[0]["annotations"][0]["coordinates"]
            assert coords["width"] == 160.0
            assert coords["height"] == 160.0


@pytest.mark.asyncio
async def test_export_csv_structure(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-csv-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "CSV Project",
            "expected_output_format": "CSV",
            "labels": ["item"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        asset_id = f"asset-csv-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_id,
            "project_id": proj_id,
            "filename": "item.jpg",
            "width": 200,
            "height": 200,
            "review_status": "final_approved",
            "is_locked": True,
            "created_at": now,
        })

        await db.annotations.insert_one({
            "id": f"ann-csv-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_id,
            "label": "item",
            "x": 10.0,
            "y": 10.0,
            "w": 50.0,
            "h": 50.0,
            "confidence": 0.99,
            "source": "human_approved",
            "review_status": "final_approved",
            "status": "active",
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        assert media_type == "text/csv"
        assert filename.endswith(".csv")

        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["project_id"] == proj_id
        assert rows[0]["image_name"] == "item.jpg"
        assert rows[0]["label"] == "item"
        assert float(rows[0]["x1"]) == 20.0
        assert float(rows[0]["y1"]) == 20.0


@pytest.mark.asyncio
async def test_export_json_structure(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-json-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "JSON Project",
            "expected_output_format": "JSON",
            "labels": ["tag"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        asset_id = f"asset-json-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_id,
            "project_id": proj_id,
            "filename": "tag.jpg",
            "width": 100,
            "height": 100,
            "review_status": "final_approved",
            "is_locked": True,
            "created_at": now,
        })

        await db.annotations.insert_one({
            "id": f"ann-json-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_id,
            "label": "tag",
            "x": 10.0,
            "y": 10.0,
            "w": 50.0,
            "h": 50.0,
            "confidence": 0.88,
            "review_status": "final_approved",
            "status": "active",
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        assert media_type == "application/json"
        assert filename.endswith(".json")

        payload = json.loads(data.decode("utf-8"))
        assert payload["format"] == "ingenii_annotate"
        assert len(payload["images"]) == 1
        assert len(payload["annotations"]) == 1
        assert payload["annotations"][0]["label"] == "tag"


@pytest.mark.asyncio
async def test_only_final_approved_annotations_exported(tmp_path):
    async with get_test_db(tmp_path) as db:
        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-qc-filter-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "Approval Filter Test Project",
            "expected_output_format": "JSON",
            "labels": ["car", "pedestrian"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        # Asset 1: FINAL_APPROVED
        asset_approved = f"asset-approved-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_approved,
            "project_id": proj_id,
            "filename": "approved_image.jpg",
            "width": 640,
            "height": 480,
            "review_status": "final_approved",
            "workflow_status": "FINAL_APPROVED",
            "is_locked": True,
            "created_at": now,
        })

        ann_approved_id = f"ann-approved-1-{uuid.uuid4().hex[:8]}"
        # Approved annotation on Asset 1
        await db.annotations.insert_one({
            "id": ann_approved_id,
            "asset_id": asset_approved,
            "label": "car",
            "x": 10.0,
            "y": 10.0,
            "w": 20.0,
            "h": 20.0,
            "review_status": "final_approved",
            "status": "active",
            "created_at": now,
        })

        # Rejected annotation on Asset 1 (e.g. human marked rejected)
        await db.annotations.insert_one({
            "id": f"ann-rejected-1-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_approved,
            "label": "pedestrian",
            "x": 50.0,
            "y": 50.0,
            "w": 10.0,
            "h": 10.0,
            "review_status": "rejected",
            "status": "active",
            "created_at": now,
        })

        # Asset 2: NOT final approved (still in human review / qc pending)
        asset_pending = f"asset-pending-1-{uuid.uuid4().hex[:8]}"
        await db.assets.insert_one({
            "id": asset_pending,
            "project_id": proj_id,
            "filename": "unapproved_image.jpg",
            "width": 640,
            "height": 480,
            "review_status": "submitted_for_qc",
            "workflow_status": "QC_PENDING",
            "is_locked": False,
            "created_at": now,
        })

        # Annotation on unapproved Asset 2
        await db.annotations.insert_one({
            "id": f"ann-unapproved-2-{uuid.uuid4().hex[:8]}",
            "asset_id": asset_pending,
            "label": "car",
            "x": 15.0,
            "y": 15.0,
            "w": 25.0,
            "h": 25.0,
            "review_status": "active",
            "status": "active",
            "created_at": now,
        })

        export_svc = ExportService(db, mock_storage)
        data, media_type, filename, summary = await export_svc.export_project(proj_id, fmt=None, include_images=False)
        payload = json.loads(data.decode("utf-8"))

        # Verify only 1 image exported (the final approved one)
        assert len(payload["images"]) == 1
        assert payload["images"][0]["id"] == asset_approved

        # Verify only 1 annotation exported (the approved car on asset 1)
        assert len(payload["annotations"]) == 1
        assert payload["annotations"][0]["annotation_id"] == ann_approved_id
        assert payload["annotations"][0]["label"] == "car"


@pytest.mark.asyncio
async def test_format_validation_endpoint(tmp_path):
    """Test format validation: matching explicit format is accepted, conflicting is rejected."""
    async with get_test_db(tmp_path) as db:
        from app.api.routes_main import export_project, create_project_export

        mock_storage = get_mock_storage(tmp_path)
        now = datetime.now(UTC)
        proj_id = f"proj-val-{now.timestamp()}"
        await db.projects.insert_one({
            "id": proj_id,
            "name": "Validation Project",
            "expected_output_format": "Pascal VOC",
            "labels": ["car"],
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        })

        # Matching explicit format: "pascal_voc" or "Pascal VOC XML" -> OK
        res_ok = await export_project(
            project_id=proj_id,
            session=db,
            storage=mock_storage,
            format="pascal_voc",
            include_images=False,
        )
        assert res_ok.status_code == 200

        # Conflicting explicit format: "coco" on a Pascal VOC project -> 422 ValidationAppError
        with pytest.raises(ValidationAppError) as exc_info:
            await export_project(
                project_id=proj_id,
                session=db,
                storage=mock_storage,
                format="coco",
                include_images=False,
            )
        assert "does not match" in str(exc_info.value)

        # In POST /projects/{id}/exports:
        with pytest.raises(ValidationAppError) as exc_info2:
            await create_project_export(
                project_id=proj_id,
                body=ExportRequest(format="yolo"),
                session=db,
                storage=mock_storage,
            )
        assert "does not match" in str(exc_info2.value)

        # Default (no format passed) -> OK and resolves to Pascal VOC
        res_default = await export_project(
            project_id=proj_id,
            session=db,
            storage=mock_storage,
            format=None,
            include_images=False,
        )
        assert res_default.status_code == 200
        assert res_default.headers["X-Export-Format"] == "PASCAL_VOC"
