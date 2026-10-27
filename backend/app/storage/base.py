"""Base storage adapter interface for cloud storage providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence


class StorageAdapter(ABC):
    """Abstract base class for cloud storage provider adapters."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns normalized provider name (e.g. 'gcs', 's3')."""
        pass

    @abstractmethod
    def validate_bucket(self, bucket: str) -> dict[str, Any]:
        """Validates that the cloud bucket exists and is accessible."""
        pass

    @abstractmethod
    def validate_prefix(self, bucket: str, prefix: str) -> dict[str, Any]:
        """Validates that the configured prefix exists and can be listed."""
        pass

    @abstractmethod
    def list_objects(
        self,
        *,
        bucket: str,
        prefix: str = "",
        allowed_extensions: Sequence[str] | None = None,
        page_size: int = 50,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        """Lists objects inside bucket + prefix with optional extension filtering and pagination."""
        pass
