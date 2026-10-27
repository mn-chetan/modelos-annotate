"""Async helper wrappers for MongoDB execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


async def commit_with_retry(
    session: Any = None,
    *,
    attempts: int = 4,
    base_delay: float = 0.05,
    operation: str = "commit",
    asset_id: str | None = None,
) -> None:
    """Async helper for pending session operations under MongoDB."""
    if session is not None and hasattr(session, "flush") and callable(getattr(session, "flush")):
        res = session.flush()
        if hasattr(res, "__await__"):
            await res
    return None


async def run_write_transaction(
    session: Any,
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    operation_name: str = "write_transaction",
    asset_id: str | None = None,
) -> T:
    """Run an operation directly under MongoDB."""
    return await operation()
