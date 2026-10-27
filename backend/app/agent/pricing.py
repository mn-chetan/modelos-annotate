"""Versioned Vertex pricing estimates (not billing reconciliation)."""

from __future__ import annotations

# Estimate table version for Gemini 3.6 Flash (USD per 1M tokens).
# Source: documented estimate for planning UI; not a billing feed.
PRICING_VERSION = "2026-07-gemini-3.6-flash-estimate-v1"

# Approximate list prices used only for UI estimates.
INPUT_USD_PER_1M = 0.15
OUTPUT_USD_PER_1M = 0.60


def estimate_cost_usd(*, tokens_in: int, tokens_out: int) -> float:
    return (tokens_in / 1_000_000.0) * INPUT_USD_PER_1M + (
        tokens_out / 1_000_000.0
    ) * OUTPUT_USD_PER_1M
