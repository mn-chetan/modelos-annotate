"""Filesystem asset storage with path-traversal protection."""

from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.errors import ValidationAppError

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def normalize_filename(filename: str) -> str:
    name = Path(filename).name
    name = name.replace("\x00", "")
    name = _SAFE_NAME.sub("_", name).strip("._")
    if not name or name in {".", ".."}:
        raise ValidationAppError("Invalid filename", details={"filename": filename})
    if len(name) > 200:
        name = name[-200:]
    return name


@dataclass
class StorageResult:
    storage_path: str
    preview_path: str | None = None


class FileStorage:
    def __init__(self, root: Path, cloud_storage: object | None = None) -> None:
        p = Path(root)
        if not p.is_absolute():
            base_dir = Path(__file__).resolve().parent.parent
            self.root = (base_dir / p).resolve()
        else:
            self.root = p.resolve()
        self.cloud_storage = cloud_storage
        self.root.mkdir(parents=True, exist_ok=True)

    def asset_dir(self, project_id: str, asset_id: str) -> Path:
        safe_proj = normalize_filename(project_id)
        safe_asset = normalize_filename(asset_id)
        path = (self.root / safe_proj / safe_asset).resolve()
        if not str(path).lower().startswith(str(self.root).lower()):
            raise ValidationAppError("Invalid storage path")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_bytes(self, project_id: str, asset_id: str, filename: str, data: bytes) -> Path:
        if not data:
            raise ValidationAppError("Cannot persist an empty asset file")
        safe = normalize_filename(filename)
        dest = self.asset_dir(project_id, asset_id) / safe
        temporary = dest.with_name(f".{dest.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, dest)
        finally:
            temporary.unlink(missing_ok=True)
        if not dest.is_file() or dest.stat().st_size != len(data):
            raise ValidationAppError(f"Physical storage write verification failed for '{safe}'")
        return dest

    def save_image(self, project_id: str, asset_id: str, filename: str, content: bytes) -> StorageResult:
        file_path = self.write_bytes(project_id, asset_id, filename, content)
        rel_storage_path = self.relative_path(file_path)
        preview_file = self.asset_dir(project_id, asset_id) / "preview.jpg"
        preview_path = None
        try:
            from app.services.images import write_jpeg_preview
            write_jpeg_preview(content, preview_file)
            preview_path = self.relative_path(preview_file)
        except Exception:
            pass
        return StorageResult(storage_path=rel_storage_path, preview_path=preview_path)

    def resolve(self, relative_or_absolute: str) -> Path:
        str_path = str(relative_or_absolute).strip()
        if str_path.startswith("gcs://") or str_path.startswith("s3://"):
            parts = str_path.split("://", 1)
            provider = normalize_filename(parts[0])
            rest = parts[1]
            bucket_str, key_str = rest.split("/", 1) if "/" in rest else (rest, "")
            safe_bucket = normalize_filename(bucket_str)
            key_segments = [normalize_filename(seg) for seg in key_str.replace("\\", "/").split("/") if seg and seg not in {".", ".."}]
            safe_key = "/".join(key_segments)
            cache_dir = (self.root / "cloud_cache" / provider / safe_bucket).resolve()
            cache_file = cache_dir.joinpath(*key_segments).resolve() if key_segments else (cache_dir / "index").resolve()
            
            if not str(cache_file).lower().startswith(str(self.root).lower()):
                raise ValidationAppError("Path traversal rejected")

            if not cache_file.exists():
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                from app.storage.cloud import CloudStorageService
                cloud_svc = self.cloud_storage or CloudStorageService()
                cloud_svc.download_file(provider=provider, bucket=safe_bucket, key=safe_key, dest_path=cache_file)
            return cache_file

        path = Path(relative_or_absolute)
        if not path.is_absolute():
            path = (self.root / path).resolve()
        else:
            path = path.resolve()
        if not str(path).lower().startswith(str(self.root).lower()):
            raise ValidationAppError("Path traversal rejected")
        return path

    def relative_path(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.root)).replace("\\", "/")
