"""Cheap per-image profiling and duplicate detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class AssetProfile:
    asset_id: str
    filename: str
    content_type: str
    format: str | None
    width: int
    height: int
    aspect_ratio: float | None
    orientation: int
    byte_size: int
    content_hash: str | None
    perceptual_hash: str | None
    decode_error: str | None
    is_duplicate: bool = False
    duplicate_of_asset_id: str | None = None
    near_duplicate_of: list[str] | None = None


def hamming_hex(a: str, b: str) -> int:
    if not a or not b or len(a) != len(b):
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def mark_duplicates(profiles: list[AssetProfile], *, near_threshold: int = 6) -> list[AssetProfile]:
    by_hash: dict[str, list[AssetProfile]] = defaultdict(list)
    for p in profiles:
        if p.content_hash:
            by_hash[p.content_hash].append(p)
    for group in by_hash.values():
        if len(group) < 2:
            continue
        canonical = group[0]
        for other in group[1:]:
            other.is_duplicate = True
            other.duplicate_of_asset_id = canonical.asset_id

    # near-duplicates among non-exact duplicates
    with_phash = [p for p in profiles if p.perceptual_hash and not p.is_duplicate]
    for i, a in enumerate(with_phash):
        near: list[str] = []
        for b in with_phash[i + 1 :]:
            if hamming_hex(a.perceptual_hash or "", b.perceptual_hash or "") <= near_threshold:
                near.append(b.asset_id)
                b.near_duplicate_of = list(set((b.near_duplicate_of or []) + [a.asset_id]))
        if near:
            a.near_duplicate_of = list(set((a.near_duplicate_of or []) + near))
    return profiles


def dataset_stats(profiles: list[AssetProfile]) -> dict[str, Any]:
    formats: dict[str, int] = defaultdict(int)
    decode_errors = 0
    exact_dups = 0
    near_dups = 0
    widths: list[int] = []
    heights: list[int] = []
    aspects: list[float] = []
    for p in profiles:
        formats[p.format or p.content_type or "unknown"] += 1
        if p.decode_error:
            decode_errors += 1
        if p.is_duplicate:
            exact_dups += 1
        if p.near_duplicate_of:
            near_dups += 1
        if p.width and p.height:
            widths.append(p.width)
            heights.append(p.height)
        if p.aspect_ratio:
            aspects.append(p.aspect_ratio)

    def _pct(vals: list[float] | list[int], q: float) -> float | None:
        if not vals:
            return None
        s = sorted(float(v) for v in vals)
        idx = min(len(s) - 1, max(0, int(round((len(s) - 1) * q))))
        return s[idx]

    return {
        "image_count": len(profiles),
        "formats": dict(formats),
        "decode_errors": decode_errors,
        "exact_duplicates": exact_dups,
        "near_duplicates": near_dups,
        "width_p50": _pct(widths, 0.5),
        "height_p50": _pct(heights, 0.5),
        "aspect_p50": _pct(aspects, 0.5),
        "profiles": [asdict(p) for p in profiles],
    }
