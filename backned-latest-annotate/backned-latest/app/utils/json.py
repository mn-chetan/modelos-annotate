"""JSON safety helpers: convert NumPy / array types into native Python types.

Keep conversion minimal and preserve numeric fidelity (use .item() when available).
"""

from __future__ import annotations

from typing import Any


def to_json_safe(value: Any) -> Any:
    """Recursively convert objects to JSON-serializable Python primitives.

    - NumPy scalars: use .item()
    - NumPy arrays: use .tolist()
    - dict/list/tuple: recurse
    - otherwise return as-is
    """
    # None, booleans, ints, floats, strings are fine
    if value is None:
        return None
    if isinstance(value, (str, bool, int, float)):
        return value

    # Dictionaries
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}

    # Lists / tuples
    if isinstance(value, (list, tuple)):
        return [to_json_safe(v) for v in value]

    # Try NumPy / array-like scalar
    try:
        item = getattr(value, "item", None)
        if callable(item):
            return item()
    except Exception:
        pass

    # Try tolist for arrays
    try:
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            return to_json_safe(tolist())
    except Exception:
        pass

    # Fallback: attempt cast to primitive
    try:
        return float(value)
    except Exception:
        pass

    return value
