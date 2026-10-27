"""Request-scoped context variables (e.g. current URL prefix)."""
from __future__ import annotations

import contextvars
import os

_current_base_prefix: contextvars.ContextVar[str] = contextvars.ContextVar("_current_base_prefix", default="")


def set_current_base_prefix(prefix: str) -> None:
    _current_base_prefix.set(prefix)


def get_current_base_prefix() -> str:
    ctx = _current_base_prefix.get()
    if ctx:
        return ctx
    env_prefix = (os.getenv("BASE_PATH") or os.getenv("URL_PREFIX") or "").strip()
    if env_prefix:
        return "/" + env_prefix.strip("/")
    return ""
