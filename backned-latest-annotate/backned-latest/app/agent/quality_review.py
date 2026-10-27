"""Quality / verification agent. Decisions come from evidence, not fixed thresholds."""

from __future__ import annotations

from typing import Any

from app.inference.agent_reasoning import call_json_agent
from app.inference.detection_quality import ALLOWED_QUALITY_ACTIONS
from app.logging import get_logger

logger = get_logger(__name__)

QUALITY_SYSTEM_PROMPT = """You are the annotation quality agent.
Return ONLY compact JSON with exactly these fields:
{"action":"accept|retry|alternate_model|additional_tool|segment|human_review|fail|no_detections_expected","reason":"brief one-line explanation","suggested_models":[],"suggested_strategy":null,"missing_labels":[]}
Rules:
- action: use 'retry' when a requested label was not evaluated by any executed model but a capable model exists in runtime_capabilities.
- action: use 'human_review' when the coverage gap cannot be resolved by any available model.
- suggested_models: list only model_key values from runtime_capabilities that can cover missing_labels. Leave [] if action is not retry/alternate_model.
- suggested_strategy: one of full_image|high_resolution|tiled|high_resolution_tiled, or null.
- missing_labels: list of requested labels that are absent from detected_labels.
Do not invent confidence or apply fixed thresholds. Do not provide chain-of-thought or verbose explanation.
Focus on whether all requested labels were actually evaluated, which labels are missing, and whether the selected models are capable of covering them.
APPROVE means coverage/model-evidence is sufficient to proceed to final verification. It never means the annotations are accepted or approved.
"""


def _normalize_label(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _requested_label_evidence(execution_plan: dict[str, Any] | None) -> dict[str, list[str]]:
    requested = list((execution_plan or {}).get("requested_labels", []) or [])
    runtime_capabilities = list((execution_plan or {}).get("runtime_capabilities", []) or [])
    executed_models = list((execution_plan or {}).get("executed_models", []) or [])
    model_vocabulary: dict[str, set[str]] = {}
    for model in runtime_capabilities:
        if not isinstance(model, dict):
            continue
        key = str(model.get("model_key") or "")
        vocab = model.get("vocabulary") or []
        if key and isinstance(vocab, list):
            model_vocabulary[key] = {_normalize_label(str(item)) for item in vocab}
    supported = []
    unsupported = []
    evaluated = []
    not_evaluated = []
    for label in requested:
        norm = _normalize_label(label)
        if not norm:
            continue
        capable_models = [
            str(model.get("model_key") or "")
            for model in runtime_capabilities
            if isinstance(model, dict)
            and str(model.get("model_key") or "") in set(executed_models)
            and norm in model_vocabulary.get(str(model.get("model_key") or ""), set())
        ]
        all_capable_models = [
            str(model.get("model_key") or "")
            for model in runtime_capabilities
            if isinstance(model, dict)
            and norm in model_vocabulary.get(str(model.get("model_key") or ""), set())
        ]
        if all_capable_models:
            supported.append(str(label))
            if capable_models:
                evaluated.append(str(label))
            else:
                not_evaluated.append(str(label))
        else:
            unsupported.append(str(label))
    return {
        "requested": requested,
        "supported": supported,
        "unsupported": unsupported,
        "evaluated": evaluated,
        "not_evaluated": not_evaluated,
    }


def _structured_requested_label_coverage(
    *,
    requested_labels: list[str],
    detections: list[Any],
    execution_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Classify requested labels using model coverage, not detection presence.

    A closed-vocabulary model evaluates every class in its vocabulary during a
    full-image run.  Therefore an absent class is an evaluated true negative;
    requiring a tiled/high-resolution retry for that case creates a replan
    loop.  Open-vocabulary models are different: the label must be present in
    the executed action's label list before it counts as evaluated.
    """
    capabilities = [
        item for item in execution_plan.get("runtime_capabilities", [])
        if isinstance(item, dict)
    ]
    executed_models = {str(model) for model in execution_plan.get("executed_models", [])}
    vocabularies = {
        str(item.get("model_key")): {
            _normalize_label(str(label)) for label in (item.get("vocabulary") or [])
        }
        for item in capabilities
    }
    open_vocabulary_models = {
        str(item.get("model_key"))
        for item in capabilities
        if "open_vocab_detection" in {
            str(capability) for capability in (item.get("capabilities") or [])
        }
    }
    history = [item for item in execution_plan.get("execution_history", []) if isinstance(item, dict)]
    execution_errors = list(execution_plan.get("execution_errors", []) or [])
    unmapped_candidates = [
        item for item in (execution_plan.get("unmapped_detections") or [])
        if isinstance(item, dict)
    ]
    coverage: list[dict[str, Any]] = []
    for raw_label in requested_labels:
        label = str(raw_label)
        normalized = _normalize_label(label)
        capable_executed = [
            model for model in executed_models
            if normalized in vocabularies.get(model, set())
            or model in open_vocabulary_models
        ]
        evaluated_models = []
        for model in capable_executed:
            if model not in open_vocabulary_models:
                # Closed-vocabulary inference evaluates its configured
                # vocabulary even when the label is absent from detections.
                evaluated_models.append(model)
                continue
            # Open-vocabulary inference only evaluates labels explicitly sent
            # in an execution action.
            if any(
                str(action.get("model") or "") == model
                and normalized in {
                    _normalize_label(str(value)) for value in (action.get("labels") or [])
                }
                for item in history
                for action in (item.get("actions") or [])
                if isinstance(action, dict)
            ):
                evaluated_models.append(model)
        matching = [
            det for det in detections
            if _normalize_label(str(getattr(det, "label", ""))) == normalized
        ]
        # An open-vocabulary model can produce a real box whose raw label
        # failed ontology mapping. That is evidence of uncertainty, never a
        # true negative. These candidates are retained separately from the
        # persistable canonical detections by the graph.
        unmapped_for_label = [
            item for item in unmapped_candidates
            if normalized in {
                _normalize_label(str(item.get("requested_label") or "")),
                _normalize_label(str(item.get("raw_label") or "")),
            }
        ]
        strategies = [
            str(action.get("strategy") or "full_image")
            for item in history
            for action in (item.get("actions") or [])
            if isinstance(action, dict)
            and str(action.get("model") or "") in capable_executed
            and normalized in {
                _normalize_label(str(value)) for value in (action.get("labels") or [label])
            }
        ]
        model_evaluated = bool(evaluated_models)
        true_negative = (
            model_evaluated
            and not matching
            and not execution_errors
            and not unmapped_for_label
        )
        uncertain = not model_evaluated or (not matching and not true_negative)
        status = (
            "DETECTED" if matching else
            "EVALUATED_TRUE_NEGATIVE" if true_negative else
            "UNCERTAIN" if model_evaluated else
            "NOT_EVALUATED"
        )
        coverage.append({
            "label": label,
            "requested": True,
            "status": status,
            "model_evaluated": model_evaluated,
            "candidate_count": len(matching),
            "accepted_count": len(matching),
            "true_negative": true_negative,
            "uncertain": uncertain,
            "evidence": {
                "executed_models": capable_executed,
                "evaluated_models": evaluated_models,
                "strategies": strategies,
                "reason": (
                    "accepted_candidates" if matching else
                    "evaluated_true_negative" if true_negative else
                    "execution_error" if execution_errors else
                    "unmapped_detection" if unmapped_for_label else
                    "not_evaluated"
                ),
                "unmapped_detection_count": len(unmapped_for_label),
            },
        })
    return coverage


def review_execution_quality(
    *,
    coverage: dict[str, Any],
    detections: list[Any],
    execution_plan: dict[str, Any] | None = None,
    previous_attempts: list[dict[str, Any]] | None = None,
    available_models: dict[str, bool] | None = None,
    settings: Any | None = None,
) -> dict[str, Any]:
    confidences = [float(det.confidence) for det in detections if isinstance(getattr(det, "confidence", None), (int, float))]
    requested_labels = list((execution_plan or {}).get("requested_labels", []) or [])
    detected_norm = {_normalize_label(str(getattr(det, "label", ""))) for det in detections}
    label_evidence = _requested_label_evidence(execution_plan)
    requested_label_coverage = _structured_requested_label_coverage(
        requested_labels=requested_labels,
        detections=detections,
        execution_plan=execution_plan or {},
    )
    retry_labels = [
        item["label"] for item in requested_label_coverage if item["uncertain"]
    ]
    detected_labels = [item["label"] for item in requested_label_coverage if item["status"] == "DETECTED"]
    evaluated_true_negative_labels = [
        item["label"] for item in requested_label_coverage
        if item["status"] == "EVALUATED_TRUE_NEGATIVE"
    ]
    uncertain_labels = [item["label"] for item in requested_label_coverage if item["status"] == "UNCERTAIN"]
    unevaluated_labels = [item["label"] for item in requested_label_coverage if item["status"] == "NOT_EVALUATED"]
    missing_detected_labels = [
        label for label in requested_labels
        if _normalize_label(label) not in detected_norm
    ]
    coverage_complete = bool(requested_labels) and not retry_labels and not (execution_plan or {}).get("execution_errors")
    executed_models = list((execution_plan or {}).get("executed_models", []) or [])
    payload = {
        "raw_count": coverage.get("raw_count", len(detections)),
        "merged_count": len(detections),
        "executed_models": executed_models,
        "models": list(dict.fromkeys(getattr(det, "model_key", None) for det in detections if getattr(det, "model_key", None))),
        "confidence": {"min": min(confidences) if confidences else None, "max": max(confidences) if confidences else None, "mean": sum(confidences) / len(confidences) if confidences else None},
        "requested_labels": requested_labels,
        "detected_labels": detected_labels,
        # Keep absent labels for audit. Only uncertain/unevaluated labels are
        # retryable and are exposed separately below.
        "missing_requested_labels": missing_detected_labels,
        "missing_detected_labels": missing_detected_labels,
        "retryable_labels": retry_labels,
        "evaluated_true_negative_labels": evaluated_true_negative_labels,
        "uncertain_labels": uncertain_labels,
        "unevaluated_labels": unevaluated_labels,
        "coverage_complete": coverage_complete,
        "requested_label_coverage": requested_label_coverage,
        "evaluated_requested_labels": label_evidence["evaluated"],
        "not_evaluated_requested_labels": label_evidence["not_evaluated"],
        "unsupported_requested_labels": label_evidence["unsupported"],
        "supported_requested_labels": label_evidence["supported"],
        "runtime_capabilities": (execution_plan or {}).get("runtime_capabilities", []),
        "coverage": coverage,
        "execution_errors": (execution_plan or {}).get("execution_errors", []),
        # Preserve the existing deterministic verification evidence for the
        # decision agent: conflicts, duplicates, geometry, and confidence are
        # observations, not routing rules invented here.
        "verification_evidence": (execution_plan or {}).get("quality_report", {}),
        "cross_model_conflicts": (execution_plan or {}).get("quality_report", {}).get("cross_model_conflicts", []),
        "unresolved_conflict_count": (execution_plan or {}).get("quality_report", {}).get("unresolved_conflict_count", 0),
        "unresolved_requested_label_conflicts": (execution_plan or {}).get("quality_report", {}).get("unresolved_requested_label_conflicts", []),
        "resolved_conflict_count": (execution_plan or {}).get("quality_report", {}).get("resolved_conflict_count", 0),
        "segmentation_required": bool((execution_plan or {}).get("segmentation_required")),
        "segmentation_observed": bool((execution_plan or {}).get("segmentation_observed")),
        "execution_history": (execution_plan or {}).get("execution_history", []),
    }
    parsed = call_json_agent(
        system_prompt=QUALITY_SYSTEM_PROMPT,
        user_payload=payload,
        settings=settings,
        max_output_tokens=220,
    )
    decision = _normalize_quality_decision(
        parsed,
        detections,
        {
            **coverage,
            "requested_label_coverage": requested_label_coverage,
            "retryable_labels": retry_labels,
            "coverage_complete": coverage_complete,
            "execution_errors": (execution_plan or {}).get("execution_errors", []),
        },
    )
    unresolved_conflict_count = int(payload.get("unresolved_conflict_count") or 0)
    if decision["action"] == "APPROVE" and unresolved_conflict_count:
        decision["quality_meaning"] = "coverage_sufficient_for_verification_with_unresolved_conflicts"
    logger.info(
        "quality_agent_decision",
        action=decision["action"],
        quality_meaning=decision.get("quality_meaning"),
        reason=decision["reason"],
        human_review_required=decision["human_review_required"],
        suggested_strategy=decision.get("suggested_strategy"),
        suggested_models=decision.get("suggested_models"),
        coverage_complete=coverage_complete,
        detected_labels=detected_labels,
        evaluated_true_negative_labels=evaluated_true_negative_labels,
        uncertain_labels=uncertain_labels,
        unevaluated_labels=unevaluated_labels,
        decision_source="quality_agent" if parsed else "quality_agent_unavailable_hitl",
    )
    logger.info(
        "next_action_selected",
        action=decision["action"],
        reason=decision["reason"],
    )
    return decision


def _normalize_quality_decision(
    parsed: dict[str, Any] | None,
    detections: list[Any],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    missing_labels = list(coverage.get("missing_requested_labels") or [])
    retryable_labels = list(coverage.get("retryable_labels") or [])
    structured_coverage = list(coverage.get("requested_label_coverage") or [])
    coverage_complete = bool(coverage.get("coverage_complete"))
    if not parsed:
        if retryable_labels:
            return {
                "action": "RETRY",
                "reason": f"Missing requested label(s): {', '.join(missing_labels)}",
                "suggested_strategy": "tiled",
                "suggested_models": ["yolo26"],
                "missing_labels": retryable_labels,
                "human_review_required": False,
                "uncertain_detection_ids": [],
                "coverage": coverage,
            }
        return {
            "action": "HUMAN_REVIEW",
            "reason": "Quality agent unavailable; preserving detections for human review",
            "suggested_strategy": None,
            "suggested_models": [],
            "missing_labels": [],
            "human_review_required": True,
            "uncertain_detection_ids": [
                getattr(det, "id", "")
                for det in detections
                if (getattr(det, "provenance", None) or {}).get("needs_review")
            ],
            "coverage": coverage,
        }

    action = str(parsed.get("action") or "HUMAN_REVIEW").upper()
    action = {"ACCEPT": "APPROVE"}.get(action, action)
    if action not in ALLOWED_QUALITY_ACTIONS:
        action = "HUMAN_REVIEW"

    parsed_missing = list(parsed.get("missing_labels") or [])
    if not missing_labels:
        missing_labels = parsed_missing or list(coverage.get("missing_requested_labels") or [])

    if action in {"APPROVE", "HUMAN_REVIEW"} and retryable_labels:
        action = "RETRY"
        missing_labels = retryable_labels

    # A model may have evaluated every requested label and produced only
    # evaluated true negatives. Do not let an LLM's stale RETRY response
    # recreate the same inference loop when there is no retryable evidence.
    if action in {"RETRY", "ALTERNATE_MODEL", "DIFFERENT_STRATEGY"} and (
        coverage_complete
        or (structured_coverage and not retryable_labels)
        or (coverage.get("evaluated_labels") and not retryable_labels)
    ):
        if not coverage.get("execution_errors"):
            action = "APPROVE"
            parsed = {**(parsed or {}), "reason": "All requested labels were evaluated; absent labels are true negatives."}

    suggested_models = list(parsed.get("suggested_models") or [])

    suggested_strategy = parsed.get("suggested_strategy")
    if not suggested_strategy and action == "RETRY":
        suggested_strategy = "tiled"

    human_review = bool(parsed.get("human_review_required")) or action in {
        "HUMAN_REVIEW",
        "FAIL",
        "VERIFY",
    }

    return {
        "action": action,
        "quality_meaning": (
            "coverage_sufficient_for_verification"
            if action == "APPROVE"
            else "additional_inference_or_review_required"
        ),
        "reason": str(parsed.get("reason") or "quality agent decision"),
        "suggested_strategy": suggested_strategy,
        "suggested_models": suggested_models,
        "missing_labels": missing_labels,
        "retryable_labels": retryable_labels,
        "coverage_complete": coverage_complete,
        "human_review_required": human_review,
        "uncertain_detection_ids": list(parsed.get("uncertain_detection_ids") or []),
        "coverage": coverage,
    }
