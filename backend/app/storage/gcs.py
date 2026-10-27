"""Google Cloud Storage (GCS) adapter implementation using Application Default Credentials."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Sequence

from app.errors import NotFoundError, ValidationAppError
from app.logging import get_logger
from app.storage.base import StorageAdapter
from app.storage.cloud import parse_gcs_scope

logger = get_logger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"
}


class GCSAdapter(StorageAdapter):
    """GCS Storage Adapter that uses google.auth.default() (ADC)."""

    def __init__(self, project_id: str | None = None) -> None:
        self.project_id = project_id
        self._client: Any | None = None

    @property
    def provider_name(self) -> str:
        return "gcs"

    def get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import storage
            import google.auth

            credentials, detected_project = google.auth.default()
            project = self.project_id or detected_project
            self._client = storage.Client(project=project, credentials=credentials)
            return self._client
        except Exception as exc:
            logger.error("gcs_adapter_auth_failed", error=str(exc))
            raise ValidationAppError(
                f"Google Cloud authentication is required: {exc}",
                details={"code": "cloud_unauthorized", "provider": "gcs", "status_code": 401},
            ) from exc

    def validate_bucket(self, bucket: str) -> dict[str, Any]:
        bucket_name = (bucket or "").strip()
        if not bucket_name:
            raise ValidationAppError("Bucket name is required", details={"code": "missing_bucket", "provider": "gcs"})

        client = self.get_client()
        try:
            b = client.get_bucket(bucket_name)
            return {
                "valid": True,
                "provider": "gcs",
                "bucket": bucket_name,
                "location": getattr(b, "location", "US"),
                "message": f"Google Cloud Storage bucket '{bucket_name}' validated successfully",
            }
        except Exception as exc:
            err_msg = str(exc)
            logger.error("gcs_bucket_validation_failed", bucket=bucket_name, error=err_msg)
            if "404" in err_msg or "Not Found" in err_msg:
                raise NotFoundError(
                    "Bucket not found.",
                    code="cloud_bucket_not_found",
                    details={"code": "cloud_bucket_not_found", "bucket": bucket_name, "provider": "gcs", "status_code": 404},
                ) from exc
            if "403" in err_msg or "AccessDenied" in err_msg or "Permission" in err_msg:
                raise ValidationAppError(
                    "Access denied. Check bucket permissions.",
                    details={"code": "cloud_access_denied", "bucket": bucket_name, "provider": "gcs", "status_code": 403},
                ) from exc
            if "401" in err_msg or "Unauthenticated" in err_msg or "reauthentication" in err_msg.lower():
                raise ValidationAppError(
                    "Google Cloud authentication is required.",
                    details={"code": "cloud_unauthorized", "bucket": bucket_name, "provider": "gcs", "status_code": 401},
                ) from exc
            raise ValidationAppError(
                f"Unable to reach Google Cloud Storage: {exc}",
                details={"code": "cloud_network_error", "bucket": bucket_name, "provider": "gcs"},
            ) from exc

    def validate_prefix(self, bucket: str, prefix: str) -> dict[str, Any]:
        self.validate_bucket(bucket)
        clean_prefix = (prefix or "").lstrip("/")
        client = self.get_client()
        try:
            b = client.bucket(bucket)
            iterator = client.list_blobs(b, prefix=clean_prefix or None, max_results=1)
            next(iterator.pages, [])
            return {"valid": True, "provider": "gcs", "bucket": bucket, "prefix": clean_prefix}
        except Exception as exc:
            err_msg = str(exc)
            if "403" in err_msg or "Permission" in err_msg:
                raise ValidationAppError(
                    "Access denied. Check bucket permissions.",
                    details={"code": "cloud_access_denied", "status_code": 403, "prefix": clean_prefix},
                ) from exc
            if "404" in err_msg or "Not Found" in err_msg:
                raise NotFoundError(
                    "Bucket not found.",
                    code="cloud_bucket_not_found",
                    details={"code": "cloud_bucket_not_found", "status_code": 404, "prefix": clean_prefix},
                ) from exc
            raise ValidationAppError(
                f"Unable to access the configured GCS prefix: {exc}",
                details={"code": "cloud_prefix_validation_error", "prefix": clean_prefix},
            ) from exc

    def list_objects(
        self,
        *,
        bucket: str,
        prefix: str = "",
        allowed_extensions: Sequence[str] | None = None,
        page_size: int = 50,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        self.validate_prefix(bucket, prefix)
        clean_prefix = (prefix or "").lstrip("/")
        page_size = max(1, min(page_size, 500))
        valid_exts = set(allowed_extensions) if allowed_extensions else SUPPORTED_IMAGE_EXTENSIONS

        client = self.get_client()
        try:
            b = client.bucket(bucket)
            iterator = client.list_blobs(
                b,
                prefix=clean_prefix or None,
                max_results=page_size,
                page_token=continuation_token,
            )
            page = next(iterator.pages, [])
            items = []
            for blob in page:
                name = blob.name
                if name.endswith("/"):
                    continue
                # Enforce strict scope prefix matching
                if clean_prefix and not name.startswith(clean_prefix):
                    continue
                ext = Path(name).suffix.lower()
                if ext not in valid_exts:
                    continue

                content_type = blob.content_type or mimetypes.guess_type(name)[0] or "image/jpeg"
                updated_iso = blob.updated.isoformat() if blob.updated else None
                uri = f"gs://{bucket}/{name}"

                items.append({
                    "name": name,
                    "size": blob.size or 0,
                    "content_type": content_type,
                    "updated": updated_iso,
                    "updated_at": updated_iso,
                    "uri": uri,
                })

            return {
                "items": items,
                "objects": items,
                "next_page_token": iterator.next_page_token,
                "next_token": iterator.next_page_token,
                "count": len(items),
            }
        except Exception as exc:
            err_msg = str(exc)
            logger.error("gcs_adapter_list_failed", bucket=bucket, prefix=prefix, error=err_msg)
            if "403" in err_msg or "Permission" in err_msg:
                raise ValidationAppError(
                    "Access denied. Check bucket permissions.",
                    details={"code": "cloud_access_denied", "status_code": 403, "bucket": bucket},
                ) from exc
            if "404" in err_msg or "Not Found" in err_msg:
                raise NotFoundError(
                    "Bucket not found.",
                    code="cloud_bucket_not_found",
                    details={"code": "cloud_bucket_not_found", "status_code": 404, "bucket": bucket},
                ) from exc
            raise ValidationAppError(
                f"Unable to reach Google Cloud Storage: {exc}",
                details={"code": "cloud_list_error", "bucket": bucket},
            ) from exc
