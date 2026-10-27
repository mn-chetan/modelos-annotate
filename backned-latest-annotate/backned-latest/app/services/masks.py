"""Mask persistence helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.db.models import MongoDoc
from app.errors import NotFoundError
from app.inference.contracts import NormalizedMask
from app.logging import get_logger
from app.storage.files import FileStorage
from app.utils.json import to_json_safe
from app.context import get_current_base_prefix

logger = get_logger(__name__)


class MaskPersistenceError(Exception):
    """Raised when mask persistence cannot safely continue due to missing annotation or foreign-key failure."""


def _mask_out(m: MongoDoc) -> dict[str, Any]:
    return {
        "id": m.get("id"),
        "project_id": m.get("project_id"),
        "asset_id": m.get("asset_id"),
        "annotation_id": m.get("annotation_id"),
        "label": m.get("label"),
        "confidence": m.get("confidence"),
        "width": m.get("width"),
        "height": m.get("height"),
        "storage_path": m.get("storage_path"),
        "image_url": f"{get_current_base_prefix()}/api/v1/masks/{m.get('id')}/image",
        "mask_rle": m.get("mask_rle"),
        "model_id": m.get("model_id"),
        "model_key": m.get("model_key"),
        "provenance": m.get("provenance"),
        "created_at": m.get("created_at"),
    }


class MaskService:
    def __init__(self, db: AsyncIOMotorDatabase, storage: FileStorage) -> None:
        self.db = db
        self.storage = storage

    def _normalize_storage_path(self, mask_path: str | None) -> str | None:
        if not mask_path:
            return None
        path = Path(mask_path)
        try:
            if path.is_absolute():
                return self.storage.relative_path(path)
            # Already relative to storage root
            self.storage.resolve(mask_path)
            return mask_path
        except Exception:  # noqa: BLE001
            return str(path)

    async def save_or_update_mask(
        self,
        asset_id: str,
        mask: NormalizedMask,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist or update a single mask for an annotation, guaranteeing idempotency without creating duplicate masks."""
        logger.info(
            "mask_persistence_start",
            asset_id=asset_id,
            annotation_id=mask.annotation_id,
            mask_id=mask.id,
        )
        if mask.annotation_id:
            existing_anno = await self.db["annotations"].find_one({"id": mask.annotation_id})
            if existing_anno is None:
                logger.error(
                    "mask_annotation_missing",
                    asset_id=asset_id,
                    annotation_id=mask.annotation_id,
                    model_key=mask.model_key,
                )
                raise MaskPersistenceError(
                    f"Annotation {mask.annotation_id} missing for mask {mask.id}"
                )
            if not project_id:
                project_id = existing_anno.get("project_id")

        if not project_id:
            asset = await self.db["assets"].find_one({"id": asset_id})
            if asset:
                project_id = asset.get("project_id")

        existing_mask = None
        if mask.annotation_id:
            existing_mask = await self.db["masks"].find_one({
                "asset_id": asset_id,
                "annotation_id": mask.annotation_id,
            })

        now = datetime.now(UTC)
        mask_id = existing_mask["id"] if existing_mask else mask.id
        norm_path = self._normalize_storage_path(mask.mask_path)

        doc = {
            "id": mask_id,
            "project_id": project_id,
            "asset_id": asset_id,
            "annotation_id": mask.annotation_id,
            "label": mask.label,
            "confidence": mask.confidence,
            "width": mask.width,
            "height": mask.height,
            "storage_path": norm_path,
            "mask_rle": to_json_safe(mask.mask_rle),
            "model_id": mask.model_id,
            "model_key": mask.model_key,
            "provenance": to_json_safe(mask.provenance),
            "updated_at": now,
        }

        if existing_mask:
            await self.db["masks"].update_one(
                {"id": mask_id},
                {"$set": doc},
            )
            doc["created_at"] = existing_mask.get("created_at", now)
            logger.info("mask_updated_existing", mask_id=mask_id, annotation_id=mask.annotation_id)
        else:
            doc["created_at"] = now
            await self.db["masks"].insert_one(doc)
            logger.info("mask_inserted_new", mask_id=mask_id, annotation_id=mask.annotation_id)

        # Clean up old file if mask path changed
        if existing_mask and existing_mask.get("storage_path") and existing_mask.get("storage_path") != norm_path:
            try:
                old_file = self.storage.resolve(existing_mask["storage_path"])
                if old_file.exists() and old_file.is_file():
                    old_file.unlink()
            except Exception:
                pass

        return doc

    async def replace_ai_masks(
        self,
        asset_id: str,
        masks: list[NormalizedMask],
        *,
        commit: bool = True,
    ) -> int:
        logger.info(
            "mask_persistence_start",
            asset_id=asset_id,
            masks=len(masks),
            commit=commit,
        )
        annotation_ids = [mask.annotation_id for mask in masks if mask.annotation_id]
        if annotation_ids:
            cursor = self.db["annotations"].find({"id": {"$in": annotation_ids}}, {"id": 1})
            existing_ids = {d.get("id") async for d in cursor}
            for mask in masks:
                if mask.annotation_id is not None and mask.annotation_id not in existing_ids:
                    logger.error(
                        "mask_annotation_missing",
                        asset_id=asset_id,
                        annotation_id=mask.annotation_id,
                        model_key=mask.model_key,
                    )
                    raise MaskPersistenceError(
                        f"Annotation {mask.annotation_id} missing for mask {mask.id}"
                    )

        await self.db["masks"].delete_many({"asset_id": asset_id})

        count = 0
        docs_to_insert: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for mask in masks:
            logger.info(
                "mask_insert",
                mask_id=mask.id,
                annotation_id=mask.annotation_id,
                asset_id=asset_id,
                model_key=mask.model_key,
            )
            doc = {
                "id": mask.id,
                "asset_id": asset_id,
                "annotation_id": mask.annotation_id,
                "label": mask.label,
                "confidence": mask.confidence,
                "width": mask.width,
                "height": mask.height,
                "storage_path": self._normalize_storage_path(mask.mask_path),
                "mask_rle": to_json_safe(mask.mask_rle),
                "model_id": mask.model_id,
                "model_key": mask.model_key,
                "provenance": to_json_safe(mask.provenance),
                "created_at": now,
            }
            docs_to_insert.append(doc)
            count += 1

        if docs_to_insert:
            await self.db["masks"].insert_many(docs_to_insert)

        logger.info(
            "mask_persistence_commit",
            asset_id=asset_id,
            masks=count,
            commit=commit,
        )

        return count

    async def list_for_asset(self, asset_id: str) -> list[dict[str, Any]]:
        asset = await self.db["assets"].find_one({"id": asset_id})
        if asset is None:
            raise NotFoundError("Asset not found", details={"asset_id": asset_id})
        cursor = self.db["masks"].find({"asset_id": asset_id})
        docs = [MongoDoc(m) async for m in cursor]
        return [_mask_out(m) for m in docs]

    async def get(self, mask_id: str) -> dict[str, Any]:
        row = await self.db["masks"].find_one({"id": mask_id})
        if row is None:
            raise NotFoundError("Mask not found", details={"mask_id": mask_id})
        return _mask_out(MongoDoc(row))

    async def image_path(self, mask_id: str) -> Path:
        row_doc = await self.db["masks"].find_one({"id": mask_id})
        if row_doc is None:
            raise NotFoundError("Mask not found", details={"mask_id": mask_id})
        row = MongoDoc(row_doc)
        storage_path = row.get("storage_path")
        if not storage_path:
            raise NotFoundError("Mask image missing", details={"mask_id": mask_id})
        path = self.storage.resolve(storage_path)
        if not path.exists():
            # Legacy absolute paths written before relative normalization
            legacy = Path(storage_path)
            if legacy.is_absolute() and legacy.exists():
                return legacy
            raise NotFoundError("Mask file missing on disk", details={"mask_id": mask_id})
        return path

