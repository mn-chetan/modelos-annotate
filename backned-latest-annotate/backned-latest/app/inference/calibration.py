"""Opt-in temperature scaling for labelled image detections."""

from __future__ import annotations

import math
from dataclasses import dataclass


def _logit(score: float) -> float:
    score = min(1.0 - 1e-6, max(1e-6, float(score)))
    return math.log(score / (1.0 - score))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def apply_temperature(score: float, temperature: float) -> float:
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    return _sigmoid(_logit(score) / temperature)


def _nll(scores: list[float], labels: list[int], temperature: float) -> float:
    total = 0.0
    for score, label in zip(scores, labels, strict=True):
        probability = apply_temperature(score, temperature)
        total -= label * math.log(max(probability, 1e-12))
        total -= (1 - label) * math.log(max(1 - probability, 1e-12))
    return total / len(labels)


@dataclass(frozen=True)
class TemperatureCalibrationResult:
    temperature: float
    baseline_nll: float
    calibrated_nll: float
    improved: bool
    sample_count: int


def fit_temperature(scores: list[float], labels: list[int]) -> TemperatureCalibrationResult:
    if not scores or len(scores) != len(labels):
        raise ValueError("scores and labels must be non-empty and have equal length")
    if any(label not in (0, 1) for label in labels):
        raise ValueError("labels must contain only 0 or 1")
    if any(not 0.0 <= float(score) <= 1.0 for score in scores):
        raise ValueError("scores must be in [0, 1]")
    baseline = _nll(scores, labels, 1.0)
    candidates = [0.05 + 0.01 * i for i in range(496)]
    temperature = min(candidates, key=lambda value: _nll(scores, labels, value))
    calibrated = _nll(scores, labels, temperature)
    return TemperatureCalibrationResult(
        temperature=temperature,
        baseline_nll=baseline,
        calibrated_nll=calibrated,
        improved=calibrated < baseline,
        sample_count=len(scores),
    )
