"""Data Connections domain service backed by MongoDB."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import hashlib

from app.config import Settings
from app.db.models import MongoDoc, to_mongo_doc, to_mongo_docs, get_database, _uuid, _utcnow
from app.domain.enums import AssetStatus, ReviewStatus
from app.errors import NotFoundError, ValidationAppError
from app.logging import get_logger
from app.schemas.data_connection import DataConnectionCreate, DataConnectionImportRequest
from app.services.images import decode_and_validate_image, write_jpeg_preview
from app.services.projects import _asset_out
from app.storage.files import FileStorage, normalize_filename
from app.storage.registry import storage_registry

logger = get_logger(__name__)

IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _format_connection_out(row: Any) -> dict[str, Any]:
    doc = to_mongo_doc(row) or MongoDoc()
    last_val = doc.get("last_validated_at")
    last_ver = "Not verified yet"
    if last_val:
        if isinstance(last_val, datetime):
            last_ver = last_val.strftime("%b %d, %Y %H:%M UTC")
        else:
            last_ver = str(last_val)

    st = doc.get("status", "unverified")
    state = "verified" if st in {"active", "verified", "authorized"} else "needs_attention"
    return {
        "id": doc.get("id", ""),
        "name": doc.get("name", ""),
        "provider": doc.get("provider", "gcs"),
        "bucket": doc.get("bucket", ""),
        "prefix": doc.get("prefix", ""),
        "scope": doc.get("scope", f"gs://{doc.get('bucket', '')}/"),
        "status": st,
        "state": state,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "last_validated_at": last_val,
        "last_verified": last_ver,
        "used_by_projects": doc.get("used_by_projects", 0),
        "auth_mode": "Application Default Credentials",
    }


class DataConnectionService:
    def __init__(
        self,
        db: Any,
        settings: Settings | None = None,
        storage: FileStorage | None = None,
    ) -> None:
        if hasattr(db, "cloud_connections"):
            self.db = db
        elif callable(db):
            self.db = db()
        else:
            self.db = get_database()
        self.settings = settings
        self.storage = storage

    async def get_row(self, connection_id: str) -> MongoDoc:
        raw = await self.db.cloud_connections.find_one({"id": connection_id})
        if not raw:
            raise NotFoundError("DataConnection", connection_id)
        return to_mongo_doc(raw)  # type: ignore

    async def create(self, payload: DataConnectionCreate) -> dict[str, Any]:
        adapter = storage_registry.get(payload.provider)
        now = _utcnow()
        doc = {
            "id": _uuid(),
            "name": payload.name.strip(),
            "provider": adapter.provider_name,
            "bucket": payload.bucket.strip() if payload.bucket else "",
            "prefix": payload.prefix.strip().lstrip("/") if payload.prefix else "",
            "scope": payload.scope or f"gs://{payload.bucket}/",
            "status": "unverified",
            "created_at": now,
            "updated_at": now,
            "last_validated_at": None,
        }
        await self.db.cloud_connections.insert_one(doc)
        logger.info("data_connection_created", connection_id=doc["id"], name=doc["name"], scope=doc["scope"])

        try:
            val = await self.validate(doc["id"])
            doc["status"] = val.get("status", "active")
        except Exception as exc:
            logger.warning("data_connection_initial_validation_failed", error=str(exc))

        return _format_connection_out(doc)

    async def list_connections(self) -> list[dict[str, Any]]:
        raw_docs = await self.db.cloud_connections.find().sort("created_at", -1).to_list(length=1000)
        return [_format_connection_out(r) for r in raw_docs]

    async def get(self, connection_id: str) -> dict[str, Any]:
        doc = await self.get_row(connection_id)
        return _format_connection_out(doc)

    async def validate(self, connection_id: str) -> dict[str, Any]:
        doc = await self.get_row(connection_id)
        adapter = storage_registry.get(doc.provider)

        result = await adapter.validate_connection(
            bucket=doc.bucket,
            prefix=doc.prefix,
        )

        now = _utcnow()
        new_status = "active" if result.get("valid") else "needs_attention"
        await self.db.cloud_connections.update_one(
            {"id": connection_id},
            {"$set": {"status": new_status, "last_validated_at": now, "updated_at": now}}
        )
        doc["status"] = new_status
        doc["last_validated_at"] = now
        return _format_connection_out(doc)

    async def list_objects(
        self,
        connection_id: str,
        prefix: str | None = None,
        page_size: int = 50,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        doc = await self.get_row(connection_id)
        adapter = storage_registry.get(doc.provider)

        effective_prefix = doc.prefix
        if prefix:
            effective_prefix = f"{doc.prefix.rstrip('/')}/{prefix.lstrip('/')}".strip("/")

        res = await adapter.list_objects(
            bucket=doc.bucket,
            prefix=effective_prefix,
            page_size=page_size,
            continuation_token=continuation_token,
        )

        raw_objects = res.get("objects", [])
        filtered_objects = [
            obj for obj in raw_objects
            if Path(obj.get("name", "")).suffix.lower() in IMPORT_IMAGE_EXTENSIONS
        ]

        return {
            "connection_id": connection_id,
            "prefix": effective_prefix,
            "page_size": page_size,
            "continuation_token": res.get("next_continuation_token"),
            "next_page_token": res.get("next_continuation_token"),
            "objects": filtered_objects,
        }

    async def import_objects(
        self,
        connection_id: str,
        payload: DataConnectionImportRequest,
    ) -> dict[str, Any]:
        if not self.settings or not self.storage:
            raise ValidationAppError("Storage environment not configured for object import")

        doc = await self.get_row(connection_id)
        project = await self.db.projects.find_one({"id": payload.project_id})
        if not project:
            raise NotFoundError("Project", payload.project_id)

        adapter = storage_registry.get(doc.provider)

        keys_to_import = [item.object_key for item in payload.objects if item.object_key]
        if not keys_to_import:
            list_res = await self.list_objects(
                connection_id,
                prefix=str(doc.get("prefix") or ""),
                page_size=500,
            )
            keys_to_import = [obj["key"] for obj in list_res["objects"]]

        if not keys_to_import:
            raise ValidationAppError("No valid image objects found to import")

        now = _utcnow()
        imported_assets = []
        persisted_files: list[tuple[Path, str | None]] = []

        for key in keys_to_import:
            ext = Path(key).suffix.lower()
            if ext not in IMPORT_IMAGE_EXTENSIONS:
                continue

            asset_id = _uuid()
            clean_filename = normalize_filename(Path(key).name)

            content = await adapter.download_bytes(bucket=doc.bucket, key=key)
            decoded = decode_and_validate_image(
                content,
                filename=clean_filename,
                content_type=None,
                max_bytes=self.settings.max_upload_bytes,
                allowed_types=self.settings.allowed_content_types,
            )

            logger.info(
                "physical_write_started",
                project_id=payload.project_id,
                asset_id=asset_id,
                filename=clean_filename,
                storage_root=str(self.storage.root),
                upload_target_directory=str(self.storage.root / payload.project_id / asset_id),
                upload_target_file=str(self.storage.root / payload.project_id / asset_id / clean_filename),
                upload_size=len(content),
                import_source=key,
            )
            storage_result = self.storage.save_image(
                project_id=payload.project_id,
                asset_id=asset_id,
                filename=clean_filename,
                content=content,
            )
            physical_path = self.storage.resolve(storage_result.storage_path)
            if (
                not physical_path.is_file()
                or physical_path.stat().st_size != len(content)
                or hashlib.sha256(physical_path.read_bytes()).hexdigest() != decoded.content_hash
            ):
                physical_path.unlink(missing_ok=True)
                raise ValidationAppError(
                    f"Physical storage verification failed for imported image '{clean_filename}'"
                )
            try:
                from PIL import Image

                with Image.open(physical_path) as image:
                    image.verify()
            except Exception as exc:
                physical_path.unlink(missing_ok=True)
                if storage_result.preview_path:
                    self.storage.resolve(storage_result.preview_path).unlink(missing_ok=True)
                raise ValidationAppError(
                    f"Persisted imported image '{clean_filename}' cannot be opened"
                ) from exc
            persisted_files.append((physical_path, storage_result.preview_path))
            logger.info(
                "physical_write_completed",
                project_id=payload.project_id,
                asset_id=asset_id,
                filename=clean_filename,
                storage_path=storage_result.storage_path,
                resolved_path=str(physical_path),
                physical_file_exists=physical_path.exists(),
                physical_file_size=physical_path.stat().st_size,
                sha256=decoded.content_hash,
                import_source=key,
            )

            asset_doc = {
                "id": asset_id,
                "project_id": payload.project_id,
                "filename": clean_filename,
                "content_type": decoded.content_type,
                "width": decoded.width,
                "height": decoded.height,
                "storage_path": storage_result.storage_path,
                "preview_path": storage_result.preview_path,
                "byte_size": len(content),
                "status": AssetStatus.UPLOADED.value,
                "review_status": ReviewStatus.PENDING.value,
                "review_reason": f"Imported from {doc.name}",
                "mean_confidence": None,
                "content_hash": hashlib.sha256(content).hexdigest(),
                "perceptual_hash": None,
                "aspect_ratio": round(decoded.width / decoded.height, 4) if decoded.height > 0 else 1.0,
                "orientation": 1,
                "image_format": decoded.format,
                "cluster_id": None,
                "is_outlier": 0,
                "is_duplicate": 0,
                "review_priority": 0.0,
                "source_provider": doc.provider,
                "source_connection_id": doc.id,
                "source_bucket": doc.bucket,
                "source_object": key,
                "created_at": now,
                "updated_at": now,
            }
            imported_assets.append(asset_doc)

        if imported_assets:
            try:
                await self.db.assets.insert_many(imported_assets)
                for asset_doc in imported_assets:
                    readback = await self.db.assets.find_one({"id": asset_doc["id"]})
                    resolved = self.storage.resolve((readback or {}).get("storage_path") or "")
                    if (
                        not readback
                        or readback.get("storage_path") != asset_doc["storage_path"]
                        or resolved != self.storage.resolve(asset_doc["storage_path"])
                        or not resolved.is_file()
                        or resolved.stat().st_size != asset_doc["byte_size"]
                    ):
                        raise ValidationAppError(
                            f"Persisted asset reference verification failed for '{asset_doc['filename']}'"
                        )
                    logger.info(
                        "asset_document_created",
                        project_id=payload.project_id,
                        asset_id=asset_doc["id"],
                        storage_path=readback["storage_path"],
                        resolved_path=str(resolved),
                        byte_size=resolved.stat().st_size,
                        import_source=asset_doc["source_object"],
                    )
                await self.db.cloud_connections.update_one(
                    {"id": connection_id},
                    {"$inc": {"used_by_projects": 1}, "$set": {"updated_at": now}}
                )
            except Exception:
                await self.db.assets.delete_many({"id": {"$in": [item["id"] for item in imported_assets]}})
                for physical_path, preview_path in persisted_files:
                    physical_path.unlink(missing_ok=True)
                    if preview_path:
                        self.storage.resolve(preview_path).unlink(missing_ok=True)
                raise

        return {
            "connection_id": connection_id,
            "project_id": payload.project_id,
            "imported_count": len(imported_assets),
            "asset_ids": [a["id"] for a in imported_assets],
        }

    async def delete(self, connection_id: str) -> None:
        doc = await self.get_row(connection_id)
        await self.db.cloud_connections.delete_one({"id": doc["id"]})
