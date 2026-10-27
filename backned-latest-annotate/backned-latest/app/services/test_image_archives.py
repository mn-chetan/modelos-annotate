from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from app.errors import ValidationAppError
from app.services.image_archives import iter_image_members


def _image_bytes(fmt: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (3, 3), "red").save(output, format=fmt)
    return output.getvalue()


def _zip_file(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


def test_nested_zip_yields_supported_images_and_ignores_other_files():
    archive = _zip_file({
        "traffic/image001.png": _image_bytes(),
        "traffic/image002.jpg": _image_bytes("JPEG"),
        "traffic/notes.txt": b"ignore me",
    })

    members = list(iter_image_members(archive, max_member_bytes=1024 * 1024))

    assert [name for name, _ in members] == ["image001.png", "image002.jpg"]


def test_zip_with_no_supported_images_is_empty():
    archive = _zip_file({"notes.txt": b"not an image"})

    assert list(iter_image_members(archive, max_member_bytes=1024 * 1024)) == []


def test_zip_slip_path_is_rejected():
    archive = _zip_file({"../../outside.jpg": _image_bytes("JPEG")})

    with pytest.raises(ValidationAppError, match="Unsafe path"):
        list(iter_image_members(archive, max_member_bytes=1024 * 1024))


@pytest.mark.parametrize("name", [r"C:\\outside.jpg", r"\\server\share\outside.jpg"])
def test_windows_absolute_zip_paths_are_rejected(name: str):
    archive = _zip_file({name: _image_bytes("JPEG")})

    with pytest.raises(ValidationAppError, match="Unsafe path"):
        list(iter_image_members(archive, max_member_bytes=1024 * 1024))


@pytest.mark.asyncio
async def test_assets_route_dispatches_zip_members_through_asset_service(monkeypatch):
    from app.api import routes_main

    archive = _zip_file({
        "Traffic/car1.jpg": _image_bytes("JPEG"),
        "Traffic/car2.jpg": _image_bytes("JPEG"),
        "Traffic/pedestrian.png": _image_bytes(),
        "Traffic/notes.txt": b"ignore me",
    })
    uploaded: list[tuple[str, str | None, bytes]] = []

    class FakeProjectService:
        def __init__(self, session, settings, storage):
            pass

        async def get_project_modality(self, project_id):
            return "image"

        async def upload_asset(self, project_id, filename, content_type, data):
            uploaded.append((filename, content_type, data))
            return {"filename": filename}

    class FakeAssetOut:
        @classmethod
        def model_validate(cls, value):
            return value

    monkeypatch.setattr(routes_main, "ProjectService", FakeProjectService)
    monkeypatch.setattr(routes_main, "AssetOut", FakeAssetOut)
    upload = UploadFile(filename="images.zip", file=io.BytesIO(archive), headers=None)
    settings = SimpleNamespace(
        max_image_upload_mb=2,
        max_video_upload_mb=2,
        max_text_upload_mb=2,
        max_document_upload_mb=2,
        max_upload_bytes=1024 * 1024,
    )

    assets = await routes_main.upload_assets(
        "project-1", session=object(), settings=settings, storage=object(), files=[upload]
    )

    assert [asset["filename"] for asset in assets] == ["car1.jpg", "car2.jpg", "pedestrian.png"]
    assert [item[0] for item in uploaded] == ["car1.jpg", "car2.jpg", "pedestrian.png"]
    assert all(content_type is None for _, content_type, _ in uploaded)


@pytest.mark.asyncio
async def test_assets_route_returns_validation_error_for_zip_without_images(monkeypatch):
    from app.api import routes_main

    class FakeProjectService:
        def __init__(self, session, settings, storage):
            pass

        async def get_project_modality(self, project_id):
            return "image"

        async def upload_asset(self, project_id, filename, content_type, data):
            pytest.fail("No assets should be created from an archive without images")

    monkeypatch.setattr(routes_main, "ProjectService", FakeProjectService)
    archive = _zip_file({"notes.txt": b"ignore me"})
    upload = UploadFile(filename="images.zip", file=io.BytesIO(archive), headers=None)
    settings = SimpleNamespace(
        max_image_upload_mb=2,
        max_video_upload_mb=2,
        max_text_upload_mb=2,
        max_document_upload_mb=2,
        max_upload_bytes=1024 * 1024,
    )

    with pytest.raises(ValidationAppError, match="No supported image files"):
        await routes_main.upload_assets(
            "project-1", session=object(), settings=settings, storage=object(), files=[upload]
        )


@pytest.mark.asyncio
async def test_assets_route_keeps_valid_images_when_mixed_with_empty_archive(monkeypatch):
    from app.api import routes_main

    uploaded: list[str] = []

    class FakeProjectService:
        def __init__(self, session, settings, storage):
            pass

        async def get_project_modality(self, project_id):
            return "image"

        async def upload_asset(self, project_id, filename, content_type, data):
            uploaded.append(filename)
            return {"filename": filename}

    class FakeAssetOut:
        @classmethod
        def model_validate(cls, value):
            return value

    monkeypatch.setattr(routes_main, "ProjectService", FakeProjectService)
    monkeypatch.setattr(routes_main, "AssetOut", FakeAssetOut)
    settings = SimpleNamespace(
        max_image_upload_mb=2,
        max_video_upload_mb=2,
        max_text_upload_mb=2,
        max_document_upload_mb=2,
        max_upload_bytes=1024 * 1024,
    )
    empty_archive = _zip_file({"notes.txt": b"ignore me"})
    uploads = [
        UploadFile(filename="images.zip", file=io.BytesIO(empty_archive), headers=None),
        UploadFile(filename="car.jpg", file=io.BytesIO(_image_bytes("JPEG")), headers=None),
    ]

    assets = await routes_main.upload_assets(
        "project-1", session=object(), settings=settings, storage=object(), files=uploads
    )

    assert [asset["filename"] for asset in assets] == ["car.jpg"]
    assert uploaded == ["car.jpg"]


@pytest.mark.asyncio
async def test_upload_route_persists_multipart_and_zip_images_to_served_paths(tmp_path):
    from types import SimpleNamespace

    from app.api import routes_main
    from app.config import get_settings
    from app.db.models import _uuid, _utcnow
    from app.services.projects import ProjectService
    from app.storage.files import FileStorage

    class Collection:
        def __init__(self, rows=()):
            self.rows = [dict(row) for row in rows]

        async def find_one(self, query):
            def matches(row, filters):
                for key, expected in filters.items():
                    if key == "$or":
                        if not any(matches(row, option) for option in expected):
                            return False
                    elif isinstance(expected, dict) and "$ne" in expected:
                        if row.get(key) == expected["$ne"]:
                            return False
                    elif row.get(key) != expected:
                        return False
                return True

            return next((dict(row) for row in self.rows if matches(row, query)), None)

        async def insert_one(self, row):
            self.rows.append(dict(row))

    project_id = _uuid()
    now = _utcnow()
    db = SimpleNamespace(
        projects=Collection([{
            "id": project_id,
            "name": "Upload Route Storage Test",
            "status": "ready",
            "modality": "image",
            "labels": ["car"],
            "created_at": now,
            "updated_at": now,
        }]),
        assets=Collection(),
    )
    settings = get_settings()
    storage = FileStorage(tmp_path / "storage")

    class ProjectServiceWithFakeDb(ProjectService):
        def __init__(self, session, settings, storage):
            super().__init__(db, settings, storage)

    direct_buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(direct_buffer, format="JPEG")
    direct_bytes = direct_buffer.getvalue()
    direct_upload = UploadFile(
        filename="direct.jpg", file=io.BytesIO(direct_bytes), headers=None
    )
    direct_assets = await routes_main.upload_assets(
        project_id,
        session=db,
        settings=settings,
        storage=storage,
        files=[direct_upload],
    )
    direct_path, _ = await ProjectServiceWithFakeDb(db, settings, storage).asset_image_path(
        direct_assets[0].id
    )
    assert direct_path.read_bytes() == direct_bytes
    with Image.open(direct_path) as image:
        image.verify()

    archive_bytes = _zip_file({
        "folder/car-red.jpg": _image_bytes("JPEG"),
        "folder/pedestrian.png": _image_bytes("PNG"),
    })
    archive_upload = UploadFile(
        filename="dataset.zip", file=io.BytesIO(archive_bytes), headers=None
    )
    archive_assets = await routes_main.upload_assets(
        project_id,
        session=db,
        settings=settings,
        storage=storage,
        files=[archive_upload],
    )

    assert len(archive_assets) == 2
    assert len(db.assets.rows) == 3
    for asset in archive_assets:
        path, _ = await ProjectServiceWithFakeDb(db, settings, storage).asset_image_path(asset.id)
        assert path.is_file() and path.stat().st_size > 0
        with Image.open(path) as image:
            image.verify()
