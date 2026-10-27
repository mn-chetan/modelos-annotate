"""Typed application errors."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application error with safe user-facing detail."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(
        self,
        message_or_entity: str,
        entity_id: str | None = None,
        *,
        code: str = "not_found",
        details: dict[str, Any] | None = None,
    ) -> None:
        if entity_id is not None:
            msg = f"{message_or_entity} not found: {entity_id}"
            det = details or {"entity": message_or_entity, "id": entity_id}
        else:
            msg = message_or_entity
            det = details
        super().__init__(msg, code=code, status_code=404, details=det)


class ValidationAppError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="validation_error", status_code=400, details=details)


class ConflictError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="conflict", status_code=409, details=details)


class ModelUnavailableError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="model_unavailable",
            status_code=503,
            details=details,
        )


class DuplicateProjectError(AppError):
    def __init__(
        self,
        message: str = "A project with this name already exists.",
        existing_project_id: str = "",
    ) -> None:
        super().__init__(
            message,
            code="duplicate_project",
            status_code=409,
            details={"existing_project_id": existing_project_id},
        )
        self.existing_project_id = existing_project_id
