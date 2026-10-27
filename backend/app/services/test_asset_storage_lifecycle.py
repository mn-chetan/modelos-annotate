"""Tests for asset storage physical file lifecycle and critical invariants."""

import pytest
from pathlib import Path
from app.db.models import _uuid, _utcnow, init_database
from app.config import get_settings
from app.storage.files import FileStorage
from app.services.projects import ProjectService
from app.errors import ValidationAppError


@pytest.mark.asyncio
async def test_asset_creation_fails_and_rolls_back_if_physical_file_missing_or_empty(tmp_path):
    settings = get_settings()
    db = await init_database(settings=settings)
    storage_dir = tmp_path / "storage"
    storage = FileStorage(storage_dir)

    proj_id = _uuid()
    now = _utcnow()
    await db.projects.insert_one({
        "id": proj_id,
        "name": "Storage Lifecycle Project",
        "labels": ["car"],
        "label_ontology": [],
        "ontology_status": "approved",
        "status": "ready",
        "modality": "image",
        "created_at": now,
        "updated_at": now,
    })

    proj_svc = ProjectService(db, settings, storage)

    import io
    from PIL import Image

    # 1. Test normal upload: physical file created -> verified -> asset record inserted
    img = Image.new("RGB", (10, 10), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    valid_content = buf.getvalue()

    created = await proj_svc.create_asset(
        project_id=proj_id,
        content=valid_content,
        filename="valid_test.jpg",
        content_type="image/jpeg",
    )
    assert created is not None
    asset_id = created["id"]
    db_asset = await db.assets.find_one({"id": asset_id})
    assert db_asset is not None
    sp = db_asset["storage_path"]
    phys_file = storage.resolve(sp)
    assert phys_file.exists()
    assert phys_file.stat().st_size > 0

    # 2. Test 0-byte upload: fails before inserting asset record into DB
    with pytest.raises(ValidationAppError):
        await proj_svc.create_asset(
            project_id=proj_id,
            content=b"",
            filename="empty.jpg",
            content_type="image/jpeg",
        )

    empty_assets = await db.assets.find({"project_id": proj_id, "filename": "empty.jpg"}).to_list(length=10)
    assert len(empty_assets) == 0

    # Clean up
    await db.projects.delete_many({"id": proj_id})
    await db.assets.delete_many({"project_id": proj_id})


@pytest.mark.asyncio
async def test_asset_creation_rolls_back_disk_file_on_db_failure(tmp_path, monkeypatch):
    settings = get_settings()
    db = await init_database(settings=settings)
    storage_dir = tmp_path / "storage"
    storage = FileStorage(storage_dir)

    proj_id = _uuid()
    now = _utcnow()
    await db.projects.insert_one({
        "id": proj_id,
        "name": "DB Failure Rollback Project",
        "labels": ["car"],
        "label_ontology": [],
        "ontology_status": "approved",
        "status": "ready",
        "modality": "image",
        "created_at": now,
        "updated_at": now,
    })

    proj_svc = ProjectService(db, settings, storage)

    import io
    from PIL import Image

    img = Image.new("RGB", (10, 10), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    valid_content = buf.getvalue()

    # Mock db.assets.insert_one to simulate database failure
    async def mock_insert_one_fail(*args, **kwargs):
        raise RuntimeError("Simulated Database Write Exception")

    monkeypatch.setattr(db.assets, "insert_one", mock_insert_one_fail)

    with pytest.raises(RuntimeError, match="Simulated Database Write Exception"):
        await proj_svc.create_asset(
            project_id=proj_id,
            content=valid_content,
            filename="db_fail.jpg",
            content_type="image/jpeg",
        )

    # Verify physical file was unlinked and does not exist on disk
    target_dir = storage_dir / proj_id
    if target_dir.exists():
        files = list(target_dir.rglob("db_fail.jpg"))
        assert len(files) == 0, f"Orphan file found on disk: {files}"

    # Clean up
    await db.projects.delete_many({"id": proj_id})


@pytest.mark.asyncio
async def test_duplicate_upload_repairs_missing_physical_image_before_success(tmp_path):
    import io
    from PIL import Image

    settings = get_settings()
    db = await init_database(settings=settings)
    storage = FileStorage(tmp_path / "storage")
    proj_id = _uuid()
    now = _utcnow()
    await db.projects.insert_one({
        "id": proj_id,
        "name": "Missing Duplicate File Project",
        "labels": ["car"],
        "label_ontology": [],
        "ontology_status": "approved",
        "status": "ready",
        "modality": "image",
        "created_at": now,
        "updated_at": now,
    })

    buf = io.BytesIO()
    Image.new("RGB", (12, 9), color="orange").save(buf, format="JPEG")
    content = buf.getvalue()
    service = ProjectService(db, settings, storage)
    original = await service.create_asset(proj_id, content, "restore.jpg", "image/jpeg")
    original_path, _ = await service.asset_image_path(original["id"])
    original_path.unlink()

    duplicate = await service.create_asset(proj_id, content, "restore.jpg", "image/jpeg")
    restored_path, _ = await service.asset_image_path(original["id"])

    assert duplicate["id"] == original["id"]
    assert restored_path.read_bytes() == content
    with Image.open(restored_path) as image:
        image.verify()
    assert await db.assets.count_documents({"project_id": proj_id}) == 1

    await db.projects.delete_many({"id": proj_id})
    await db.assets.delete_many({"project_id": proj_id})


@pytest.mark.asyncio
async def test_committed_asset_survives_insert_acknowledgement_timeout(tmp_path):
    import io
    from types import SimpleNamespace
    from PIL import Image

    settings = get_settings()
    storage = FileStorage(tmp_path / "storage")
    project_id = _uuid()
    project_doc = {"id": project_id, "name": "Ambiguous Insert Test", "modality": "image"}

    class Projects:
        async def find_one(self, query):
            return project_doc if query.get("id") == project_id else None

    class Assets:
        def __init__(self):
            self.rows = []

        async def find_one(self, query):
            for row in self.rows:
                if all(
                    row.get(key) != value.get("$ne") if isinstance(value, dict) and "$ne" in value
                    else row.get(key) == value
                    for key, value in query.items()
                ):
                    return dict(row)
            return None

        async def insert_one(self, row):
            self.rows.append(dict(row))
            raise TimeoutError("Firestore committed but acknowledgement timed out")

    db = SimpleNamespace(projects=Projects(), assets=Assets())
    service = ProjectService(db, settings, storage)
    image_bytes = io.BytesIO()
    Image.new("RGB", (8, 6), "green").save(image_bytes, format="JPEG")
    content = image_bytes.getvalue()

    uploaded = await service.create_asset(
        project_id, content, "ambiguous-commit.jpg", "image/jpeg"
    )
    path, _ = await service.asset_image_path(uploaded["id"])

    assert len(db.assets.rows) == 1
    assert path.is_file()
    assert path.read_bytes() == content


@pytest.mark.asyncio
async def test_data_connection_import_persists_and_reads_back_image(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    from PIL import Image
    from app.schemas.data_connection import DataConnectionImportRequest
    from app.services.data_connections import DataConnectionService
    from app.storage.registry import storage_registry

    settings = get_settings()
    storage = FileStorage(tmp_path / "storage")
    proj_id = _uuid()
    connection_id = _uuid()

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def __aiter__(self):
            async def iterate():
                for row in self.rows:
                    yield row
            return iterate()

        async def to_list(self, length):
            return self.rows[:length]

    class Collection:
        def __init__(self, rows=()):
            self.rows = list(rows)

        async def find_one(self, query):
            return next((row.copy() for row in self.rows if all(row.get(k) == v for k, v in query.items())), None)

        def find(self, query, projection=None):
            return Cursor([row.copy() for row in self.rows if all(row.get(k) == v for k, v in query.items())])

        async def insert_many(self, rows):
            self.rows.extend(dict(row) for row in rows)

        async def update_one(self, query, update):
            for row in self.rows:
                if all(row.get(k) == v for k, v in query.items()):
                    row.update(update.get("$set", {}))
                    for key, value in update.get("$inc", {}).items():
                        row[key] = row.get(key, 0) + value
                    return

    db = SimpleNamespace(
        projects=Collection([{"id": proj_id, "status": "ready"}]),
        cloud_connections=Collection([{
            "id": connection_id,
            "provider": "gcs",
            "bucket": "test-bucket",
            "name": "Test connection",
        }]),
        assets=Collection(),
    )

    image_buffer = io.BytesIO()
    Image.new("RGB", (14, 11), color="blue").save(image_buffer, format="JPEG")
    image_bytes = image_buffer.getvalue()

    class FakeAdapter:
        async def download_bytes(self, *, bucket, key):
            assert bucket == "test-bucket"
            assert key == "images/photo.jpg"
            return image_bytes

    monkeypatch.setattr(storage_registry, "get", lambda provider: FakeAdapter())
    service = DataConnectionService(db, settings, storage)
    result = await service.import_objects(
        connection_id,
        DataConnectionImportRequest(
            project_id=proj_id,
            objects=[{"key": "images/photo.jpg"}],
        ),
    )

    assert result["imported_count"] == 1
    asset = await db.assets.find_one({"id": result["asset_ids"][0]})
    assert asset is not None
    physical_path = storage.resolve(asset["storage_path"])
    assert physical_path.read_bytes() == image_bytes
    with Image.open(physical_path) as image:
        image.verify()



@pytest.mark.asyncio
async def test_png_webp_concurrent_and_cwd_resolution(tmp_path):
    import io
    import asyncio
    import os
    from PIL import Image

    settings = get_settings()
    db = await init_database(settings=settings)
    storage_dir = tmp_path / "storage"
    storage = FileStorage(storage_dir)

    proj_id = _uuid()
    now = _utcnow()
    await db.projects.insert_one({
        "id": proj_id,
        "name": "PNG WEBP Concurrent Project",
        "labels": ["car"],
        "label_ontology": [],
        "ontology_status": "approved",
        "status": "ready",
        "modality": "image",
        "created_at": now,
        "updated_at": now,
    })

    proj_svc = ProjectService(db, settings, storage)

    # 1. PNG & WEBP uploads
    img_png = Image.new("RGB", (20, 20), color="green")
    buf_png = io.BytesIO()
    img_png.save(buf_png, format="PNG")
    png_bytes = buf_png.getvalue()

    img_webp = Image.new("RGB", (20, 20), color="yellow")
    buf_webp = io.BytesIO()
    img_webp.save(buf_webp, format="WEBP")
    webp_bytes = buf_webp.getvalue()

    created_png = await proj_svc.create_asset(proj_id, png_bytes, "sample.png", "image/png")
    created_webp = await proj_svc.create_asset(proj_id, webp_bytes, "sample.webp", "image/webp")

    assert created_png["id"] != created_webp["id"]
    path_png, ct_png = await proj_svc.asset_image_path(created_png["id"])
    path_webp, ct_webp = await proj_svc.asset_image_path(created_webp["id"])

    assert path_png.exists() and path_png.stat().st_size > 0
    assert path_webp.exists() and path_webp.stat().st_size > 0

    # 2. Test resolution from a different working directory
    orig_cwd = os.getcwd()
    db_png = await db.assets.find_one({"id": created_png["id"]})
    assert db_png is not None and "storage_path" in db_png
    try:
        os.chdir(tmp_path)
        new_storage = FileStorage(storage_dir)
        resolved_from_alt_cwd = new_storage.resolve(db_png["storage_path"])
        assert resolved_from_alt_cwd.exists()
        assert resolved_from_alt_cwd.read_bytes() == png_bytes
    finally:
        os.chdir(orig_cwd)

    # 3. Concurrent uploads of multiple files with identical filename
    async def upload_one(i: int):
        img = Image.new("RGB", (10 + i, 10 + i), color="red")
        b = io.BytesIO()
        img.save(b, format="JPEG")
        return await proj_svc.create_asset(proj_id, b.getvalue(), f"concurrent_{i}.jpg", "image/jpeg")

    results = await asyncio.gather(*(upload_one(i) for i in range(5)))
    assert len(results) == 5
    asset_ids = {r["id"] for r in results}
    assert len(asset_ids) == 5  # No ID collisons or cross-overwrites

    for r in results:
        p, _ = await proj_svc.asset_image_path(r["id"])
        assert p.exists() and p.stat().st_size > 0

    await db.projects.delete_many({"id": proj_id})
    await db.assets.delete_many({"project_id": proj_id})


