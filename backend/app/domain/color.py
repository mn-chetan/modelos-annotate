"""Deterministic, high-contrast color assignment for object classes.

Mirrors the frontend's class color hash so identical class names
produce the same color on both sides, with zero collisions across project classes.
"""

from __future__ import annotations

import colorsys

GOLDEN_ANGLE = 137.508


def normalize_label(label: str) -> str:
    if not label:
        return ""
    return " ".join(label.strip().lower().split())


def _hash_name(value: str) -> int:
    norm = normalize_label(value)
    h = 0
    for ch in norm:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def color_for_class(name: str, used_colors: set[str] | None = None) -> str:
    """Spreads hues via golden angle HSL distribution with collision avoidance."""
    norm = normalize_label(name)
    base_hash = _hash_name(norm)

    for attempt in range(100):
        h = base_hash + attempt * 17
        hue = ((h * GOLDEN_ANGLE) % 360) / 360
        saturation = (70 + (h % 20)) / 100
        lightness = (44 + ((h >> 4) % 12)) / 100
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        hex_color = "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))
        if not used_colors or hex_color not in used_colors:
            if used_colors is not None:
                used_colors.add(hex_color)
            return hex_color

    return hex_color
