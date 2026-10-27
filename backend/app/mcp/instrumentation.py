"""Timing + structured-error instrumentation shared by all MCP tools.

Every MCP tool call emits ``mcp_tool_start`` / ``mcp_tool_complete`` (or
``mcp_tool_failed``) structlog events with ``duration_ms``, following the
same event-naming convention already used across ``app/`` (see
``app/logging.py``). Exceptions are never allowed to cross the MCP
boundary; they are translated into a structured :class:`MCPResult` so a
model/server outage cannot crash the batch workflow.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, TypeVar, overload

from app.errors import AppError, ModelUnavailableError
from app.logging import get_logger
from app.mcp.contracts import INTERNAL_ERROR, MODEL_UNAVAILABLE, MCPResult, fail, ok

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _result_count(value: Any) -> int | None:
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return None


def _log_start(capability: str, kwargs: dict[str, Any]) -> None:
    logger.info(
        "mcp_tool_start",
        capability=capability,
        asset_id=kwargs.get("asset_id"),
        model=kwargs.get("model") or kwargs.get("model_key"),
    )


def _handle_success(capability: str, kwargs: dict[str, Any], duration_ms: int, result: Any) -> MCPResult[Any]:
    if isinstance(result, MCPResult):
        logger.info(
            "mcp_tool_complete",
            capability=capability,
            asset_id=kwargs.get("asset_id"),
            model=kwargs.get("model") or kwargs.get("model_key"),
            duration_ms=duration_ms,
            success=result.success,
            result_count=_result_count(result.data),
        )
        return result
    logger.info(
        "mcp_tool_complete",
        capability=capability,
        asset_id=kwargs.get("asset_id"),
        model=kwargs.get("model") or kwargs.get("model_key"),
        duration_ms=duration_ms,
        success=True,
        result_count=_result_count(result),
    )
    return ok(result)


def _handle_error(capability: str, kwargs: dict[str, Any], duration_ms: int, exc: Exception) -> MCPResult[Any]:
    asset_id = kwargs.get("asset_id")
    model = kwargs.get("model") or kwargs.get("model_key")
    if isinstance(exc, ModelUnavailableError):
        logger.warning(
            "mcp_tool_failed",
            capability=capability,
            asset_id=asset_id,
            model=model,
            duration_ms=duration_ms,
            error_code=MODEL_UNAVAILABLE,
            error=str(exc),
        )
        return fail(MODEL_UNAVAILABLE, str(exc), details=exc.details)
    if isinstance(exc, AppError):
        logger.warning(
            "mcp_tool_failed",
            capability=capability,
            asset_id=asset_id,
            model=model,
            duration_ms=duration_ms,
            error_code=exc.code.upper(),
            error=str(exc),
        )
        return fail(exc.code.upper(), str(exc), details=exc.details)
    logger.error(
        "mcp_tool_failed",
        capability=capability,
        asset_id=asset_id,
        model=model,
        duration_ms=duration_ms,
        error_code=INTERNAL_ERROR,
        error=str(exc),
    )
    return fail(INTERNAL_ERROR, str(exc))


P = ParamSpec("P")
R = TypeVar("R")


class mcp_tool:
    """Wrap a sync or async MCP tool function with logging + error translation."""

    def __init__(self, capability: str) -> None:
        self.capability = capability

    @overload
    def __call__(  # type: ignore[overload-overlap]
        self, func: Callable[P, Coroutine[Any, Any, R]]
    ) -> Callable[P, Coroutine[Any, Any, MCPResult[R]]]:
        ...

    @overload
    def __call__(
        self, func: Callable[P, R]
    ) -> Callable[P, MCPResult[R]]:
        ...

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        capability = self.capability
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> MCPResult[Any]:
                _log_start(capability, kwargs)
                started = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - MCP boundary must never raise
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    return _handle_error(capability, kwargs, duration_ms, exc)
                duration_ms = int((time.perf_counter() - started) * 1000)
                return _handle_success(capability, kwargs, duration_ms, result)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> MCPResult[Any]:
            _log_start(capability, kwargs)
            started = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - MCP boundary must never raise
                duration_ms = int((time.perf_counter() - started) * 1000)
                return _handle_error(capability, kwargs, duration_ms, exc)
            duration_ms = int((time.perf_counter() - started) * 1000)
            return _handle_success(capability, kwargs, duration_ms, result)

        return sync_wrapper
