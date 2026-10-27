"""Normalize messy live-agent JSON into ontology schema shapes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_PREVALENCE_WORDS = {
    "none": 0.0,
    "rare": 0.05,
    "low": 0.15,
    "medium": 0.4,
    "moderate": 0.4,
    "common": 0.6,
    "high": 0.75,
    "very high": 0.9,
    "ubiquitous": 0.95,
}

_KIND_MAP = {
    "object": "object",
    "objects": "object",
    "primary": "object",
    "secondary": "object",
    "instance": "object",
    "box": "object",
    "bbox": "object",
    "image": "image",
    "scene": "image",
    "global": "image",
    "attribute": "attribute",
    "attr": "attribute",
    "property": "attribute",
}


def _as_str(value: Any, *, join_with: str = ", ") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [_as_str(v) for v in value]
        return join_with.join(p for p in parts if p)
    if isinstance(value, dict):
        # Prefer common text keys
        for key in ("text", "value", "name", "label", "description"):
            if key in value:
                return _as_str(value[key])
        return join_with.join(f"{k}: {_as_str(v)}" for k, v in value.items())
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(";", ",").split(",")]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            s = _as_str(item)
            if s:
                out.append(s)
        return out
    s = _as_str(value)
    return [s] if s else []


def _as_float_01(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1.0 and v <= 100.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))
    if isinstance(value, str):
        text = value.strip().lower().replace("%", "")
        if text in _PREVALENCE_WORDS:
            return _PREVALENCE_WORDS[text]
        try:
            return _as_float_01(float(text))
        except ValueError:
            return None
    return None


def _as_kind(value: Any) -> str:
    text = _as_str(value).lower()
    return _KIND_MAP.get(text, "object")


def _as_relations(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        return [{"relation": value}]
    if isinstance(value, (list, tuple)):
        out: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, str) and item.strip():
                out.append({"relation": item.strip()})
            elif item is not None:
                out.append({"relation": str(item)})
        return out
    return [{"relation": str(value)}]


def _as_model_recs(value: Any) -> list[dict[str, Any]]:
    allowed = {"yolo26", "florence", "dino", "sam2"}
    if not value:
        return []
    if not isinstance(value, list):
        value = [value]
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            key = item.strip().lower()
            if key in allowed:
                out.append({"key": key, "purpose": key, "required": key == "yolo26"})
            continue
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("model_key") or "").strip().lower()
        if key not in allowed:
            continue
        out.append(
            {
                "key": key,
                "purpose": _as_str(item.get("purpose") or key),
                "required": bool(item.get("required", key == "yolo26")),
            }
        )
    return out


def _as_questions(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(value):
        if isinstance(item, str):
            out.append(
                {
                    "id": f"q{i + 1}",
                    "question": item,
                    "options": [],
                    "rationale": "",
                    "decision_type": "boundary",
                    "proposed_default": "",
                    "affects_count": 0,
                    "example_asset_ids": [],
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "id": _as_str(item.get("id") or f"q{i + 1}") or f"q{i + 1}",
                "question": _as_str(item.get("question") or item.get("prompt")),
                "options": _as_str_list(item.get("options")),
                "rationale": _as_str(item.get("rationale")),
                "decision_type": _as_str(item.get("decision_type") or "boundary") or "boundary",
                "proposed_default": _as_str(item.get("proposed_default")),
                "affects_count": int(item.get("affects_count") or 0)
                if str(item.get("affects_count") or "0").replace(".", "", 1).isdigit()
                else 0,
                "example_asset_ids": _as_str_list(item.get("example_asset_ids")),
            }
        )
    return out


def normalize_ontology_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce common live-model drifts into OntologyAgentResult-compatible dict."""
    labels_in = data.get("proposed_labels") or []
    if not isinstance(labels_in, list):
        labels_in = []
    labels_out: list[dict[str, Any]] = []
    for item in labels_in:
        if isinstance(item, str):
            labels_out.append(
                {
                    "name": item.strip(),
                    "definition": f"Suggested label: {item.strip()}",
                    "includes": "",
                    "excludes": "",
                    "aliases": [],
                    "relations": [],
                    "evidence_asset_ids": [],
                    "prevalence_estimate": None,
                    "kind": "object",
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        name = _as_str(item.get("name") or item.get("label") or item.get("class"))
        if not name:
            continue
        labels_out.append(
            {
                "name": name,
                "definition": _as_str(item.get("definition") or item.get("description")),
                "includes": _as_str(item.get("includes")),
                "excludes": _as_str(item.get("excludes")),
                "aliases": _as_str_list(item.get("aliases")),
                "relations": _as_relations(item.get("relations")),
                "evidence_asset_ids": _as_str_list(item.get("evidence_asset_ids")),
                "prevalence_estimate": _as_float_01(item.get("prevalence_estimate")),
                "kind": _as_kind(item.get("kind")),
            }
        )

    strategy = _as_str(data.get("label_strategy") or "detailed").lower()
    if strategy not in {"generic", "detailed", "custom"}:
        strategy = "detailed"

    return {
        "summary": _as_str(data.get("summary")),
        "proposed_labels": labels_out,
        "needs_decision": bool(data.get("needs_decision") or data.get("needs_clarification")),
        "clarifying_questions": _as_questions(data.get("clarifying_questions")),
        "recommended_models": _as_model_recs(data.get("recommended_models")),
        "risks": _as_str_list(data.get("risks")),
        "review_policy_notes": _as_str(data.get("review_policy_notes")),
        "label_strategy": strategy,
    }


def normalize_project_plan_response(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize only nullable plan containers before schema validation.

    None means the agent supplied no entries. Other incorrect container types
    are intentionally preserved so the Pydantic contract reports them.
    """
    if not isinstance(data, dict):
        raise TypeError("Project plan response must be an object")
    normalized = deepcopy(data)
    if normalized.get("ambiguities") is None:
        normalized["ambiguities"] = []
    if normalized.get("review_policy") is None:
        normalized["review_policy"] = {}
    if normalized.get("clarifications") is None:
        normalized["clarifications"] = {}
    return normalized
