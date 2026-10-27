"""Structured request/response envelope shared by every MCP tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")

# Stable error codes surfaced to the orchestrator so it can decide whether to
# retry, fall back, or route the asset to human review.
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
MODEL_TIMEOUT = "MODEL_TIMEOUT"
INVALID_INPUT = "INVALID_INPUT"
NOT_FOUND = "NOT_FOUND"
EMPTY_RESULT = "EMPTY_RESULT"
INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class MCPError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPResult(Generic[T]):
    success: bool
    data: T | None = None
    error: MCPError | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.success:
            return {"success": True, "data": self.data}
        assert self.error is not None
        return {
            "success": False,
            "error": {
                "code": self.error.code,
                "message": self.error.message,
                "details": self.error.details,
            },
        }


def ok(data: T | None = None) -> MCPResult[T]:
    return MCPResult(success=True, data=data)


def fail(code: str, message: str, *, details: dict[str, Any] | None = None) -> MCPResult[Any]:
    return MCPResult(success=False, error=MCPError(code=code, message=message, details=details or {}))
