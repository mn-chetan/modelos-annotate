"""Pydantic schemas for Data Connections."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.errors import ValidationAppError
from app.storage.cloud import parse_gcs_scope


class DataConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Connection display name")
    provider: str = Field(default="gcs", description="Storage provider (e.g. gcs, s3)")
    bucket: str | None = Field(default=None, description="Cloud storage bucket name")
    prefix: str | None = Field(default="", description="Folder / prefix scope")
    scope: str | None = Field(default=None, description="Full URI scope (e.g. gs://bucket/prefix)")

    @model_validator(mode="before")
    @classmethod
    def normalize_scope_and_bucket(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        provider = (data.get("provider") or "gcs").lower().strip()
        data["provider"] = provider

        scope = data.get("scope")
        bucket = data.get("bucket")
        prefix = data.get("prefix") or ""

        if scope and scope.strip():
            clean_scope = scope.strip()
            if provider == "gcs":
                b, p = parse_gcs_scope(clean_scope)
                data["bucket"] = b
                data["prefix"] = p
                data["scope"] = f"gs://{b}/{p}"
            else:
                data["scope"] = clean_scope
        elif bucket and bucket.strip():
            clean_bucket = bucket.strip()
            clean_prefix = prefix.strip().lstrip("/")
            if clean_prefix and not clean_prefix.endswith("/"):
                clean_prefix += "/"
            data["bucket"] = clean_bucket
            data["prefix"] = clean_prefix
            if provider == "gcs":
                data["scope"] = f"gs://{clean_bucket}/{clean_prefix}"
            else:
                data["scope"] = f"{provider}://{clean_bucket}/{clean_prefix}"
        else:
            raise ValidationAppError(
                "Either bucket or scope must be provided for a Data Connection.",
                details={"code": "missing_bucket_or_scope"},
            )

        return data


class DataConnectionOut(BaseModel):
    id: str
    name: str
    provider: str
    bucket: str
    prefix: str
    scope: str
    status: str
    state: str
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    last_validated_at: datetime | str | None = None
    last_verified: str = "Not verified yet"
    used_by_projects: int = 0
    auth_mode: str = "Application Default Credentials"

    model_config = ConfigDict(from_attributes=True)


class DataConnectionValidateOut(BaseModel):
    status: str = "active"
    provider: str = "gcs"
    bucket: str
    prefix: str = ""
    message: str = "Google Cloud Storage connection validated successfully"


class CloudObjectItem(BaseModel):
    name: str
    size: int = 0
    content_type: str = "image/jpeg"
    updated: str | None = None
    uri: str


class CloudObjectsResponse(BaseModel):
    items: list[CloudObjectItem] = Field(default_factory=list)
    objects: list[CloudObjectItem] = Field(default_factory=list)
    next_page_token: str | None = None
    next_token: str | None = None
    count: int = 0


DataConnectionObjectsOut = CloudObjectsResponse


class DataConnectionImportObject(BaseModel):
    key: str | None = Field(default=None, description="Object key inside the connection scope")
    name: str | None = Field(default=None, description="Legacy object key alias")
    size: int | None = None
    format: str | None = None
    content_type: str | None = None
    updated: str | None = None

    @model_validator(mode="after")
    def require_key(self) -> "DataConnectionImportObject":
        if not (self.key or self.name):
            raise ValueError("Object key is required")
        return self

    @property
    def object_key(self) -> str:
        return (self.key or self.name or "").strip().lstrip("/")


class DataConnectionImportRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    objects: list[DataConnectionImportObject] = Field(default_factory=list)
    destination_path: str | None = None


class DataConnectionImportResult(BaseModel):
    object_key: str
    asset_id: str | None = None
    status: str
    source_uri: str | None = None
    reason: str | None = None


class DataConnectionImportOut(BaseModel):
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[DataConnectionImportResult] = Field(default_factory=list)
