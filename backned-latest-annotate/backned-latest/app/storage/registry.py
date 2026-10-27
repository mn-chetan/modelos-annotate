"""Storage adapter registry for dynamic provider resolution."""

from __future__ import annotations

from typing import Dict

from app.errors import ValidationAppError
from app.storage.base import StorageAdapter
from app.storage.gcs import GCSAdapter


class StorageRegistry:
    """Registry managing available storage adapters."""

    def __init__(self) -> None:
        self._adapters: Dict[str, StorageAdapter] = {}

    def register(self, adapter: StorageAdapter) -> None:
        name = adapter.provider_name.lower().strip()
        self._adapters[name] = adapter

    def get(self, provider: str) -> StorageAdapter:
        name = (provider or "").lower().strip()
        if name in {"gcs", "google", "google_cloud_storage"}:
            name = "gcs"

        if name not in self._adapters:
            if name == "gcs":
                gcs_adapter = GCSAdapter()
                self._adapters["gcs"] = gcs_adapter
                return gcs_adapter
            raise ValidationAppError(
                f"Unsupported storage provider: '{provider}'",
                details={"code": "unsupported_provider", "supported": list(self._adapters.keys())},
            )
        return self._adapters[name]


storage_registry = StorageRegistry()
storage_registry.register(GCSAdapter())
