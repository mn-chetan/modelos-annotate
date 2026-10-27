"""Cloud Storage abstraction for Google Cloud Storage (GCS) and AWS S3."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from app.errors import NotFoundError, ValidationAppError
from app.logging import get_logger

logger = get_logger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".avif", ".tiff", ".tif"
}


def parse_gcs_scope(scope: str) -> tuple[str, str]:
    value = (scope or "").strip()
    if not value.startswith("gs://"):
        raise ValidationAppError(
            "GCS scope must use gs://bucket/prefix format.",
            details={"code": "invalid_gcs_scope"},
        )
    remainder = value[5:]
    bucket, _, prefix = remainder.partition("/")
    if not bucket or "?" in bucket or "#" in bucket:
        raise ValidationAppError("A valid GCS bucket is required.", details={"code": "invalid_gcs_bucket"})
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def is_key_in_scope(key: str, bucket: str, prefix: str) -> bool:
    clean_key = (key or "").lstrip("/")
    return bool(clean_key) and clean_key.startswith(prefix) and clean_key != prefix


def is_supported_image(filename_or_key: str, content_type: str | None = None) -> bool:
    if content_type and content_type.startswith("image/"):
        return True
    suffix = Path(filename_or_key).suffix.lower()
    return suffix in SUPPORTED_IMAGE_EXTENSIONS


class CloudStorageService:
    def __init__(
        self,
        *,
        storage_provider: str = "gcs",
        gcs_bucket_name: str | None = None,
        gcs_project_id: str | None = None,
        gcs_prefix: str | None = None,
        aws_s3_bucket: str | None = None,
        aws_region: str | None = None,
        aws_endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        self.storage_provider = storage_provider.lower().strip() if storage_provider else "gcs"
        self.gcs_bucket_name = gcs_bucket_name or os.getenv("GCS_BUCKET_NAME", "")
        self.gcs_project_id = gcs_project_id or os.getenv("GCS_PROJECT_ID", "")
        self.gcs_prefix = (gcs_prefix if gcs_prefix is not None else os.getenv("GCS_PREFIX", "")).strip().lstrip("/")
        self.aws_s3_bucket = aws_s3_bucket or os.getenv("AWS_S3_BUCKET", "")
        self.aws_region = aws_region or os.getenv("AWS_REGION", "us-east-1")
        self.aws_endpoint_url = aws_endpoint_url or os.getenv("AWS_ENDPOINT_URL", "")
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID", "")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY", "")

        self._gcs_client: Any | None = None
        self._s3_client: Any | None = None

    def get_config_summary(self) -> dict[str, Any]:
        """Returns safe summary of configured cloud providers (no secrets exposed)."""
        providers = []
        # Check GCS availability
        try:
            from google.cloud import storage as gcs_module  # noqa: F401
            providers.append("gcs")
        except ImportError:
            pass

        # Check S3 availability
        try:
            import boto3  # noqa: F401
            providers.append("s3")
        except ImportError:
            pass

        if not providers:
            providers = ["gcs", "s3"]

        return {
            "configured_provider": self.storage_provider,
            "available_providers": providers,
            "default_gcs_bucket": self.gcs_bucket_name,
            "default_s3_bucket": self.aws_s3_bucket,
            "aws_region": self.aws_region,
            "gcs_prefix": self.gcs_prefix,
            "cloud_storage_status": "configured" if self.gcs_bucket_name and self.gcs_project_id else "not_configured",
            "cloud_storage_message": "" if self.gcs_bucket_name and self.gcs_project_id else "Cloud Storage is not configured.",
        }

    def _get_gcs_client(self) -> Any:
        if self._gcs_client is not None:
            return self._gcs_client
        try:
            from google.cloud import storage
            import google.auth
            credentials, detected_project = google.auth.default()
            credential_name = credentials.__class__.__module__ + "." + credentials.__class__.__name__
            if credential_name == "google.oauth2.credentials.Credentials" and not getattr(credentials, "quota_project_id", None):
                raise ValidationAppError(
                    "Google Cloud end-user credentials have no quota project. Configure one with `gcloud auth application-default set-quota-project <PROJECT_ID>`.",
                    details={"code": "gcp_quota_project_missing", "provider": "gcs"},
                )
            project = self.gcs_project_id or os.getenv("GOOGLE_CLOUD_PROJECT", None) or detected_project
            self._gcs_client = storage.Client(project=project, credentials=credentials)
            return self._gcs_client
        except Exception as exc:
            logger.error("gcs_client_init_failed", error=str(exc))
            raise ValidationAppError(
                f"Google Cloud Storage client initialization failed: {exc}",
                details={"provider": "gcs", "hint": "Ensure Google Application Default Credentials are configured"},
            ) from exc

    def _get_s3_client(self) -> Any:
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3
            client_kwargs: dict[str, Any] = {
                "region_name": self.aws_region or "us-east-1",
            }
            if self.aws_endpoint_url:
                client_kwargs["endpoint_url"] = self.aws_endpoint_url
            if self.aws_access_key_id and self.aws_secret_access_key:
                client_kwargs["aws_access_key_id"] = self.aws_access_key_id
                client_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

            self._s3_client = boto3.client("s3", **client_kwargs)
            return self._s3_client
        except Exception as exc:
            logger.error("s3_client_init_failed", error=str(exc))
            raise ValidationAppError(
                f"AWS S3 client initialization failed: {exc}",
                details={"provider": "s3", "hint": "Check AWS credentials and region configuration"},
            ) from exc

    def validate_bucket(self, provider: str, bucket: str) -> dict[str, Any]:
        """Validates that the cloud bucket exists and is accessible with current credentials."""
        prov = (provider or self.storage_provider).lower().strip()
        bucket_name = (bucket or "").strip()
        if not bucket_name:
            raise ValidationAppError("Bucket name is required", details={"provider": prov})

        if prov in {"gcs", "google"}:
            client = self._get_gcs_client()
            try:
                if self.gcs_project_id and isinstance(getattr(client, "project", None), str) and client.project != self.gcs_project_id:
                    raise ValidationAppError(
                        f"Configured GCP project '{self.gcs_project_id}' does not match the authenticated project '{client.project}'.",
                        details={"code": "gcp_project_mismatch", "provider": "gcs"},
                    )
                # get_bucket performs an API call to verify existence & access permissions
                b = client.get_bucket(bucket_name)
                return {
                    "valid": True,
                    "provider": "gcs",
                    "bucket": bucket_name,
                    "location": getattr(b, "location", "US"),
                    "message": f"Successfully connected to Google Cloud Storage bucket '{bucket_name}'.",
                }
            except Exception as exc:
                err_msg = str(exc)
                logger.error("gcs_bucket_validation_failed", bucket=bucket_name, error=err_msg)
                if "404" in err_msg or "Not Found" in err_msg:
                    raise NotFoundError(
                        "Configured GCS bucket does not exist or is not accessible.",
                        code="cloud_bucket_not_found",
                        details={"bucket": bucket_name, "provider": "gcs"},
                    ) from exc
                if "403" in err_msg or "AccessDenied" in err_msg or "Permission" in err_msg:
                    raise ValidationAppError(
                        f"Access denied to GCS bucket '{bucket_name}'. Check GCP IAM permissions.",
                        details={"code": "cloud_access_denied", "bucket": bucket_name, "provider": "gcs"},
                    ) from exc
                raise ValidationAppError(
                    f"GCS bucket validation failed for '{bucket_name}': {exc}",
                    details={"code": "cloud_validation_error", "bucket": bucket_name, "provider": "gcs"},
                ) from exc

        elif prov in {"s3", "aws"}:
            s3 = self._get_s3_client()
            try:
                s3.head_bucket(Bucket=bucket_name)
                return {
                    "valid": True,
                    "provider": "s3",
                    "bucket": bucket_name,
                    "region": self.aws_region,
                    "message": f"Successfully connected to AWS S3 bucket '{bucket_name}'.",
                }
            except Exception as exc:
                err_msg = str(exc)
                logger.error("s3_bucket_validation_failed", bucket=bucket_name, error=err_msg)
                if "NoSuchBucket" in err_msg or "404" in err_msg:
                    raise NotFoundError(
                        f"Configured S3 bucket '{bucket_name}' does not exist or is not accessible.",
                        details={"code": "cloud_bucket_not_found", "bucket": bucket_name, "provider": "s3"},
                    ) from exc
                if "AccessDenied" in err_msg or "403" in err_msg:
                    raise ValidationAppError(
                        f"Access denied to S3 bucket '{bucket_name}'. Check AWS credentials.",
                        details={"code": "cloud_access_denied", "bucket": bucket_name, "provider": "s3"},
                    ) from exc
                raise ValidationAppError(
                    f"S3 bucket validation failed for '{bucket_name}': {exc}",
                    details={"code": "cloud_validation_error", "bucket": bucket_name, "provider": "s3"},
                ) from exc
        else:
            raise ValidationAppError(f"Unsupported cloud storage provider: {provider}", details={"supported": ["gcs", "s3"]})

    def validate_prefix(self, *, provider: str, bucket: str, prefix: str) -> dict[str, Any]:
        """Validate that the configured prefix can be listed by the ADC identity."""
        self.validate_bucket(provider=provider, bucket=bucket)
        clean_prefix = prefix.lstrip("/")
        try:
            if provider.lower().strip() in {"gcs", "google", "google_cloud_storage"}:
                client = self._get_gcs_client()
                iterator = client.list_blobs(client.bucket(bucket), prefix=clean_prefix or None, max_results=1)
                next(iterator.pages, [])
            else:
                self.list_objects(provider=provider, bucket=bucket, prefix=clean_prefix, page_size=1)
            return {"valid": True, "prefix": clean_prefix}
        except Exception as exc:
            msg = str(exc)
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if status == 401 or "401" in msg or "Unauthorized" in msg:
                raise ValidationAppError("GCS authorization expired or is invalid.", details={"code": "cloud_unauthorized", "status_code": 401}) from exc
            if status == 403 or "403" in msg or "Permission" in msg:
                raise ValidationAppError("Access denied to the configured GCS prefix.", details={"code": "cloud_access_denied", "status_code": 403, "prefix": clean_prefix}) from exc
            if status == 404 or "404" in msg or "Not Found" in msg:
                raise NotFoundError("The configured GCS bucket or prefix was not found.", code="cloud_prefix_not_found", details={"status_code": 404, "prefix": clean_prefix}) from exc
            raise ValidationAppError(f"Unable to access the configured GCS prefix: {exc}", details={"code": "cloud_prefix_validation_error"}) from exc

    def check_object_exists(self, provider: str, bucket: str, key: str) -> bool:
        """Checks whether an object exists in cloud storage without downloading it."""
        prov = (provider or self.storage_provider).lower().strip()
        bucket_name = (bucket or "").strip()
        clean_key = (key or "").strip()
        if not bucket_name or not clean_key:
            return False

        if prov in {"gcs", "google"}:
            try:
                client = self._get_gcs_client()
                b = client.bucket(bucket_name)
                blob = b.blob(clean_key)
                return blob.exists()
            except Exception:
                return False
        elif prov in {"s3", "aws"}:
            try:
                s3 = self._get_s3_client()
                s3.head_object(Bucket=bucket_name, Key=clean_key)
                return True
            except Exception:
                return False
        return False

    def object_not_found_error(self, provider: str, bucket: str, key: str) -> NotFoundError:
        normalized = provider.lower().strip()
        return NotFoundError(
            f"{normalized.upper()} object '{key}' was not found in bucket '{bucket}'.",
            code="cloud_object_not_found",
            details={"code": "cloud_object_not_found", "provider": normalized, "bucket": bucket, "key": key},
        )

    def list_objects(
        self,
        *,
        provider: str,
        bucket: str,
        prefix: str = "",
        page_size: int = 50,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        prov = (provider or self.storage_provider).lower().strip()
        bucket_name = (bucket or "").strip()
        if not bucket_name:
            raise ValidationAppError("Bucket name is required", details={"provider": prov})

        clean_prefix = prefix.lstrip("/") if prefix else (self.gcs_prefix if prov in {"gcs", "google"} else "")
        page_size = max(1, min(page_size, 500))

        if prov in {"gcs", "google"}:
            return self._list_gcs_objects(bucket_name, clean_prefix, page_size, continuation_token)
        elif prov in {"s3", "aws"}:
            return self._list_s3_objects(bucket_name, clean_prefix, page_size, continuation_token)
        else:
            raise ValidationAppError(f"Unsupported cloud storage provider: {provider}", details={"supported": ["gcs", "s3"]})

    def _list_gcs_objects(
        self,
        bucket_name: str,
        prefix: str,
        page_size: int,
        continuation_token: str | None,
    ) -> dict[str, Any]:
        client = self._get_gcs_client()
        try:
            bucket = client.bucket(bucket_name)
            iterator = client.list_blobs(
                bucket,
                prefix=prefix or None,
                max_results=page_size,
                page_token=continuation_token,
            )
            # Retrieve current page of items
            page = next(iterator.pages, [])
            objects = []
            for blob in page:
                # Filter out folder markers
                if blob.name.endswith("/"):
                    continue
                content_type = blob.content_type or mimetypes.guess_type(blob.name)[0] or "image/jpeg"
                if is_supported_image(blob.name, content_type):
                    objects.append({
                        "name": blob.name,
                        "size": blob.size or 0,
                        "content_type": content_type,
                        "updated_at": blob.updated.isoformat() if blob.updated else None,
                        "uri": f"gcs://{bucket_name}/{blob.name}",
                    })
            return {
                "provider": "gcs",
                "bucket": bucket_name,
                "prefix": prefix,
                "objects": objects,
                "next_token": iterator.next_page_token,
                "count": len(objects),
            }
        except Exception as exc:
            err_msg = str(exc)
            logger.error("gcs_list_failed", bucket=bucket_name, prefix=prefix, error=err_msg)
            if "404" in err_msg or "Not Found" in err_msg:
                raise NotFoundError(
                    f"Configured GCS bucket '{bucket_name}' does not exist or is not accessible.",
                    details={"code": "cloud_bucket_not_found", "bucket": bucket_name, "provider": "gcs"},
                ) from exc
            if "403" in err_msg or "AccessDenied" in err_msg or "Permission" in err_msg:
                raise ValidationAppError(
                    f"Access denied to GCS bucket '{bucket_name}'. Check IAM permissions.",
                    details={"code": "cloud_access_denied", "bucket": bucket_name, "provider": "gcs"},
                ) from exc
            raise ValidationAppError(f"Failed to list GCS objects in '{bucket_name}': {exc}", details={"bucket": bucket_name}) from exc

    def _list_s3_objects(
        self,
        bucket_name: str,
        prefix: str,
        page_size: int,
        continuation_token: str | None,
    ) -> dict[str, Any]:
        s3 = self._get_s3_client()
        try:
            kwargs: dict[str, Any] = {
                "Bucket": bucket_name,
                "MaxKeys": page_size,
            }
            if prefix:
                kwargs["Prefix"] = prefix
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = s3.list_objects_v2(**kwargs)
            raw_contents = response.get("Contents", [])
            objects = []
            for item in raw_contents:
                key = item.get("Key", "")
                if not key or key.endswith("/"):
                    continue
                size = item.get("Size", 0)
                content_type = mimetypes.guess_type(key)[0] or "image/jpeg"
                if is_supported_image(key, content_type):
                    updated = item.get("LastModified")
                    objects.append({
                        "name": key,
                        "size": size,
                        "content_type": content_type,
                        "updated_at": updated.isoformat() if updated else None,
                        "uri": f"s3://{bucket_name}/{key}",
                    })
            return {
                "provider": "s3",
                "bucket": bucket_name,
                "prefix": prefix,
                "objects": objects,
                "next_token": response.get("NextContinuationToken"),
                "count": len(objects),
            }
        except Exception as exc:
            err_msg = str(exc)
            logger.error("s3_list_failed", bucket=bucket_name, prefix=prefix, error=err_msg)
            if "NoSuchBucket" in err_msg or "404" in err_msg:
                raise NotFoundError(
                    f"Configured S3 bucket '{bucket_name}' does not exist or is not accessible.",
                    details={"code": "cloud_bucket_not_found", "bucket": bucket_name, "provider": "s3"},
                ) from exc
            if "AccessDenied" in err_msg or "403" in err_msg:
                raise ValidationAppError(
                    f"Access denied to S3 bucket '{bucket_name}'. Check AWS IAM credentials.",
                    details={"code": "cloud_access_denied", "bucket": bucket_name, "provider": "s3"},
                ) from exc
            raise ValidationAppError(f"Failed to list S3 objects in '{bucket_name}': {exc}", details={"bucket": bucket_name}) from exc

    def download_file(
        self,
        *,
        provider: str,
        bucket: str,
        key: str,
        dest_path: Path,
    ) -> Path:
        """Downloads object from cloud storage directly to a local filesystem path."""
        prov = provider.lower().strip()
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if prov in {"gcs", "google"}:
            client = self._get_gcs_client()
            try:
                gcs_bucket = client.bucket(bucket)
                blob = gcs_bucket.blob(key)
                blob.download_to_filename(str(dest_path))
                return dest_path
            except Exception as exc:
                err_msg = str(exc)
                logger.error("gcs_download_failed", bucket=bucket, key=key, error=err_msg)
                raise self.object_not_found_error("gcs", bucket, key) from exc

        elif prov in {"s3", "aws"}:
            s3 = self._get_s3_client()
            try:
                s3.download_file(bucket, key, str(dest_path))
                return dest_path
            except Exception as exc:
                err_msg = str(exc)
                logger.error("s3_download_failed", bucket=bucket, key=key, error=err_msg)
                raise NotFoundError(
                    f"S3 object '{key}' was not found in bucket '{bucket}'.",
                    details={"code": "cloud_object_not_found", "provider": "s3", "bucket": bucket, "key": key},
                ) from exc
        else:
            raise ValidationAppError(f"Unsupported cloud provider: {provider}")

    def get_object_bytes(
        self,
        *,
        provider: str,
        bucket: str,
        key: str,
    ) -> tuple[bytes, str]:
        """Downloads object directly into bytes in memory (for lightweight metadata inspection)."""
        prov = provider.lower().strip()
        content_type = mimetypes.guess_type(key)[0] or "image/jpeg"

        if prov in {"gcs", "google"}:
            client = self._get_gcs_client()
            try:
                gcs_bucket = client.bucket(bucket)
                blob = gcs_bucket.blob(key)
                data = blob.download_as_bytes()
                return data, blob.content_type or content_type
            except Exception as exc:
                raise self.object_not_found_error("gcs", bucket, key) from exc

        elif prov in {"s3", "aws"}:
            s3 = self._get_s3_client()
            try:
                resp = s3.get_object(Bucket=bucket, Key=key)
                data = resp["Body"].read()
                return data, resp.get("ContentType") or content_type
            except Exception as exc:
                raise self.object_not_found_error("s3", bucket, key) from exc
        else:
            raise ValidationAppError(f"Unsupported cloud provider: {provider}")
