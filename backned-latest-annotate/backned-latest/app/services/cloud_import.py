"""Cloud Storage dataset import service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.api.schemas import (
    AssetOut,
    BatchCreate,
    CloudImportOut,
    CloudImportRequest,
    CloudListObjectsOut,
    CloudStorageConfigOut,
)
from app.config import Settings
from app.db.models import MongoDoc
from app.domain.enums import AssetStatus, ProjectStatus, ReviewStatus
from app.errors import NotFoundError, ValidationAppError
from app.logging import get_logger
from app.services.batches import BatchService
from app.services.projects import _asset_out
from app.storage.cloud import CloudStorageService, is_supported_image
from app.storage.files import FileStorage, normalize_filename

logger = get_logger(__name__)


class CloudImportService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        storage: FileStorage,
        cloud_storage: CloudStorageService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.storage = storage
        self.cloud = cloud_storage or CloudStorageService(
            storage_provider=settings.storage_provider,
            gcs_bucket_name=settings.gcs_bucket_name,
            gcs_project_id=settings.gcs_project_id,
            gcs_prefix=settings.gcs_prefix,
            aws_s3_bucket=settings.aws_s3_bucket,
            aws_region=settings.aws_region,
            aws_endpoint_url=settings.aws_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

    def get_config(self) -> CloudStorageConfigOut:
        summary = self.cloud.get_config_summary()
        return CloudStorageConfigOut(**summary)

    async def validate_connection(
        self,
        project_id: str,
        *,
        provider: str,
        bucket: str,
    ) -> dict[str, Any]:
        """Tests cloud storage connectivity and verifies that the specified bucket exists and is accessible."""
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})

        return self.cloud.validate_bucket(provider=provider, bucket=bucket)

    async def list_objects(
        self,
        project_id: str,
        *,
        provider: str,
        bucket: str,
        prefix: str = "",
        page_size: int = 50,
        continuation_token: str | None = None,
    ) -> CloudListObjectsOut:
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})

        self.cloud.validate_bucket(provider=provider, bucket=bucket)
        res = self.cloud.list_objects(
            provider=provider,
            bucket=bucket,
            prefix=prefix,
            page_size=page_size,
            continuation_token=continuation_token,
        )
        return CloudListObjectsOut(**res)

    async def import_objects(
        self,
        project_id: str,
        payload: CloudImportRequest,
    ) -> CloudImportOut:
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        project = MongoDoc(project_doc)

        provider = (payload.provider or self.settings.storage_provider).lower().strip()
        bucket = (payload.bucket or "").strip()
        if not bucket:
            raise ValidationAppError("Bucket name is required for cloud import")

        if not payload.objects:
            raise ValidationAppError("No objects selected for import")

        # 1. Validate bucket existence and access permissions before creating any assets
        self.cloud.validate_bucket(provider=provider, bucket=bucket)

        # 2. Fetch existing storage paths for this project to ensure duplicate protection
        existing_cursor = self.db["assets"].find({"project_id": project_id}, {"storage_path": 1})
        existing_paths = {d.get("storage_path") async for d in existing_cursor if d.get("storage_path")}

        created_assets: list[MongoDoc] = []
        duplicate_count = 0
        failed_count = 0
        now = datetime.now(UTC)

        for obj in payload.objects:
            key = obj.name.strip()
            if not key or key.endswith("/"):
                continue

            storage_uri = f"{provider}://{bucket}/{key}"
            if storage_uri in existing_paths:
                duplicate_count += 1
                continue

            if not is_supported_image(key, obj.content_type):
                failed_count += 1
                continue

            # Client metadata is only a reference: verify the real object
            # before persisting an asset record.
            if not self.cloud.check_object_exists(provider, bucket, key):
                failed_count += 1
                logger.warning("cloud_import_object_missing", bucket=bucket, key=key)
                continue

            try:
                base_name = Path(key).name
                safe_name = normalize_filename(base_name)
            except Exception:
                safe_name = f"cloud-{key.replace('/', '_')}"

            asset = MongoDoc({
                "id": str(uuid.uuid4()),
                "project_id": project.id,
                "filename": safe_name,
                "content_type": obj.content_type or "image/jpeg",
                "width": 0,
                "height": 0,
                "storage_path": storage_uri,
                "preview_path": None,
                "byte_size": obj.size or 0,
                "status": AssetStatus.UPLOADED.value,
                "review_status": ReviewStatus.PENDING.value,
                "created_at": now,
                "updated_at": now,
            })
            created_assets.append(asset)
            existing_paths.add(storage_uri)

        if created_assets:
            await self.db["assets"].insert_many([dict(a) for a in created_assets])
            if project.get("status") == ProjectStatus.DRAFT.value:
                await self.db["projects"].update_one(
                    {"id": project.id},
                    {"$set": {"status": ProjectStatus.READY.value, "updated_at": datetime.now(UTC)}}
                )

        imported_count = len(created_assets)
        logger.info(
            "cloud_import_completed",
            project_id=project_id,
            provider=provider,
            bucket=bucket,
            imported=imported_count,
            duplicates=duplicate_count,
            failed=failed_count,
        )

        batch_id: str | None = None
        if payload.run_inference and created_assets:
            new_asset_ids = [a.id for a in created_assets]
            try:
                batch_svc = BatchService(self.db, self.settings)
                batch_res = await batch_svc.create(
                    project_id,
                    BatchCreate(asset_ids=new_asset_ids),
                    batch_creation_source="cloud_import_explicit_request",
                    explicit_ai_annotation_trigger=True,
                    caller_context="CloudImportRequest.run_inference=true",
                )
                batch_id = batch_res.get("id")
            except Exception as exc:
                logger.error("cloud_import_batch_start_failed", error=str(exc))
        else:
            logger.info(
                "cloud_import_asset_only",
                project_id=project_id,
                imported_asset_count=len(created_assets),
                batch_creation_source="cloud_import_asset_registration",
                explicit_ai_annotation_trigger=False,
            )

        asset_outs = [AssetOut.model_validate(_asset_out(a, 0)) for a in created_assets]

        message = (
            f"Successfully imported {imported_count} image{'s' if imported_count != 1 else ''}"
            + (f" ({duplicate_count} already existed)" if duplicate_count > 0 else "")
        )

        return CloudImportOut(
            job_id=batch_id,
            batch_id=batch_id,
            imported_count=imported_count,
            duplicate_count=duplicate_count,
            failed_count=failed_count,
            total_selected=len(payload.objects),
            assets=asset_outs,
            message=message,
        )

