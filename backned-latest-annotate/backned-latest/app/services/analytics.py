"""Deterministic, project-scoped production analytics."""

from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any, Iterable

from app.errors import ValidationAppError

class AnalyticsValidationError(ValidationAppError):
    """Raised when a KPI population cannot produce a consistent snapshot."""


_REVIEWED = {
    "approved",
    "auto_approved",
    "human_approved",
    "human_modified_approved",
    "reworked",
    "reprocess_required",
    "human_rejected",
    "rejected",
    "flagged",
}
_APPROVED = {"approved", "auto_approved", "human_approved", "human_modified_approved"}
_HUMAN_ROUTED = {
    "needs_review",
    "pending",
    "human_review",
    "review",
    "human_approved",
    "human_modified_approved",
    "human_rejected",
    "reprocess_required",
}
_COMPLETED = {"ready", "completed", "processed"}
_REWORKED = {"reworked", "human_modified_approved", "reprocess_required"}
_REJECTED = {"rejected", "human_rejected", "flagged"}


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100.0, 1) if denominator else None


def calculate_review_acceptance_rate(approved_first_pass: int, total_reviewed: int) -> float:
    """Calculate Review Acceptance Rate = (approved_first_pass / total_reviewed) * 100.

    Returns 0.0 if total_reviewed == 0 to avoid division by zero / NaN.
    """
    if not total_reviewed or total_reviewed <= 0:
        return 0.0
    return round((approved_first_pass / total_reviewed) * 100.0, 1)


def calculate_rework_rate(corrected_reworked: int, total_reviewed: int) -> float:
    """Calculate Rework Rate = (corrected_reworked / total_reviewed) * 100.

    Returns 0.0 if total_reviewed == 0 to avoid division by zero / NaN.
    """
    if not total_reviewed or total_reviewed <= 0:
        return 0.0
    return round((corrected_reworked / total_reviewed) * 100.0, 1)


def calculate_defect_rate(defective_annotations: int, total_reviewed: int) -> float:
    """Calculate Defect Rate = (defective_annotations / total_reviewed) * 100.

    Returns 0.0 if total_reviewed == 0 to avoid division by zero / NaN.
    """
    if not total_reviewed or total_reviewed <= 0:
        return 0.0
    return round((defective_annotations / total_reviewed) * 100.0, 1)


def calculate_reviewer_agreement(double_review_pairs: Iterable[tuple[str, str]]) -> float | None:
    """Calculate Reviewer Agreement using Cohen's Kappa.

    Formula:
        Kappa = (Po - Pe) / (1 - Pe)

    Where:
        Po = observed agreement = (matching decisions / total double-reviewed items)
        Pe = expected chance agreement = sum(P1(cat) * P2(cat))

    Returns:
        agreement_percentage = round(Kappa * 100.0, 1) as a float between 0.0 and 100.0,
        or None if total double-reviewed items == 0 or if (1 - Pe) == 0.
    """
    pairs = list(double_review_pairs)
    if not pairs:
        return None

    n = len(pairs)
    if n == 0:
        return None

    matching = sum(1 for r1, r2 in pairs if r1 == r2)
    po = matching / n

    cats = sorted(set(r1 for r1, _ in pairs) | set(r2 for _, r2 in pairs))
    if not cats:
        return None

    r1_counts = {c: sum(1 for r1, _ in pairs if r1 == c) for c in cats}
    r2_counts = {c: sum(1 for _, r2 in pairs if r2 == c) for c in cats}

    pe = sum((r1_counts[c] / n) * (r2_counts[c] / n) for c in cats)

    denom = 1.0 - pe
    if abs(denom) < 1e-9:
        return None

    kappa = (po - pe) / denom
    result = round(kappa * 100.0, 1)
    return max(0.0, min(100.0, result))


def calculate_quality_index(
    review_acceptance_rate: float | None,
    reviewer_agreement: float | None,
    rework_rate: float | None,
    defect_rate: float | None,
) -> float | None:
    """Calculate Quality Index composite score:
    Quality Index = (0.40 * review_acceptance_rate)
                  + (0.30 * reviewer_agreement)
                  + (0.20 * (100 - rework_rate))
                  + (0.10 * (100 - defect_rate))

    Returns None if any required input metric is None.
    """
    if (
        review_acceptance_rate is None
        or reviewer_agreement is None
        or rework_rate is None
        or defect_rate is None
    ):
        return None

    score = (
        0.40 * float(review_acceptance_rate)
        + 0.30 * float(reviewer_agreement)
        + 0.20 * (100.0 - float(rework_rate))
        + 0.10 * (100.0 - float(defect_rate))
    )
    return round(score, 1)


def calculate_average_review_time(total_review_minutes: float | None, reviewed_images: int) -> float | None:
    """Calculate Average Review Time = total_review_minutes / reviewed_images.

    Returns None if reviewed_images == 0 or total_review_minutes is None.
    """
    if not reviewed_images or reviewed_images <= 0 or total_review_minutes is None:
        return None
    return round(total_review_minutes / reviewed_images, 1)


def calculate_escalation_rate(escalated_items: int, reviewed_items: int) -> float | None:
    """Calculate Escalation Rate = (escalated_items / reviewed_items) * 100.

    Returns None if reviewed_items == 0.
    """
    if not reviewed_items or reviewed_items <= 0:
        return None
    return round((escalated_items / reviewed_items) * 100.0, 1)


def calculate_consensus_pass_rate(majority_approved: int, consensus_reviews: int) -> float | None:
    """Calculate Consensus Pass Rate = (majority_approved / consensus_reviews) * 100.

    Returns None if consensus_reviews == 0.
    """
    if not consensus_reviews or consensus_reviews <= 0:
        return None
    return round((majority_approved / consensus_reviews) * 100.0, 1)


def calculate_annotation_productivity(annotations_completed: int, annotator_hours: float | None) -> float | None:
    """Calculate Annotation Productivity = annotations_completed / annotator_hours.

    Returns None if annotator_hours is None or annotator_hours <= 0.
    """
    if annotator_hours is None or annotator_hours <= 0:
        return None
    return round(annotations_completed / annotator_hours, 1)


def _is_valid_confidence(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _is_human_modified(asset: Any, annotations: Iterable[Any]) -> bool:
    status = str(getattr(asset, "review_status", "") or "").lower()
    if status in {"human_modified_approved", "reprocess_required"}:
        return True
    reason = str(getattr(asset, "review_reason", "") or "").lower()
    if any(term in reason for term in ("modified", "reworked", "corrected", "relabeled")):
        return True
    for annotation in annotations:
        source = str(getattr(annotation, "source", "") or "").lower()
        provenance = getattr(annotation, "provenance", None) or {}
        if source in {"human", "human_edited", "manual", "reviewer_edited", "decision_applied"}:
            return True
        if any(provenance.get(key) is True for key in ("human_modified", "edited_by_human", "human_correction")):
            return True
    return False


def validate_kpi_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    population = snapshot["population"]
    total = population["total_assets"]
    completed = population["completed_assets"]
    ai_annotated = population.get("ai_annotated_assets", 0)
    reviewed = population["reviewed_assets"]
    approved = population["approved_assets"]
    eligible = population["eligible_assets"]
    human_review = population["human_review_assets"]
    escalated = population["escalated_assets"]
    modified = population["human_modified_assets"]
    if (
        approved > reviewed
        or approved > total
        or completed > total
        or ai_annotated > total
        or human_review > eligible
        or escalated > eligible
        or modified > escalated
    ):
        raise AnalyticsValidationError(
            "Inconsistent KPI populations: approved/reviewed, completed/total, "
            "escalated/eligible, or modified/escalated constraint was violated."
        )
    for key in (
        "completion_rate",
        "approval_rate",
        "annotation_confidence",
        "quality_yield",
        "quality_index",
        "automation_rate",
        "hitl_rate",
        "low_confidence_escalation_rate",
        "human_override_rate",
        "review_acceptance_rate",
        "rework_rate",
        "defect_rate",
        "reviewer_agreement",
        "escalation_rate",
        "consensus_pass_rate",
    ):
        value = snapshot.get(key)
        if value is not None and not 0.0 <= value <= 100.0:
            raise AnalyticsValidationError(f"KPI {key} is outside the range 0..100.")
    return snapshot


def calculate_project_kpis(
    *,
    project_id: str,
    assets: Iterable[Any],
    annotations: Iterable[Any],
    confidence_threshold: float | None,
    total_production_cost: float | None,
    approved_annotations: int,
    ontology: Iterable[Any],
    throughput_per_hour: float | None,
    target_images: int | None,
    double_review_events: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Calculate all dashboard KPIs from already project-scoped persisted rows."""
    active_assets = [a for a in assets if str(getattr(a, "status", "") or "").lower() != "deleted"]
    asset_map = {a.id: a for a in active_assets}
    annotations_by_asset: dict[str, list[Any]] = {asset_id: [] for asset_id in asset_map}
    valid_confidences: list[float] = []
    ontology_names = {}
    for entry in ontology:
        val = entry.get("name") if isinstance(entry, dict) else str(entry)
        if val and str(val).strip():
            clean = str(val).strip()
            ontology_names[clean.lower()] = clean

    class_counts: dict[str, dict[str, Any]] = {}
    for _, display_name in ontology_names.items():
        class_counts[display_name] = {"annotation_count": 0, "image_ids": set(), "approved_count": 0}

    for annotation in annotations:
        if annotation.asset_id not in asset_map:
            continue
        annotations_by_asset[annotation.asset_id].append(annotation)
        provenance = getattr(annotation, "provenance", None) or {}
        if provenance.get("deleted") is True:
            continue
        raw_label = str(getattr(annotation, "label", "") or "Uncategorized").strip()
        label = ontology_names.get(raw_label.lower(), raw_label)
        class_entry = class_counts.setdefault(label, {"annotation_count": 0, "image_ids": set(), "approved_count": 0})
        class_entry["annotation_count"] += 1
        class_entry["image_ids"].add(annotation.asset_id)
        asset_item = asset_map.get(annotation.asset_id)
        if asset_item and (asset_item.get("review_status") if isinstance(asset_item, dict) else getattr(asset_item, "review_status", None)) in _APPROVED:
            class_entry["approved_count"] += 1
        if (
            str(getattr(annotation, "source", "") or "").lower() == "ai"
            and provenance.get("deleted") is not True
            and _is_valid_confidence(getattr(annotation, "confidence", None))
        ):
            valid_confidences.append(float(annotation.confidence))

    total_assets = len(active_assets)
    ai_annotated_assets = [
        asset for asset in active_assets
        if any(
            str(getattr(annotation, "source", "") or "").lower() == "ai"
            and (getattr(annotation, "provenance", None) or {}).get("deleted") is not True
            for annotation in annotations_by_asset[asset.id]
        )
    ]
    annotated_asset_ids = {
        annotation.asset_id
        for annotation in annotations
        if annotation.asset_id in asset_map
        and (getattr(annotation, "provenance", None) or {}).get("deleted") is not True
    }
    completed_assets = [
        a for a in active_assets
        if str(getattr(a, "status", "") or "").lower() in (_COMPLETED | {"uploaded"})
        or str(getattr(a, "review_status", "") or "").lower() in (_REVIEWED | _HUMAN_ROUTED)
    ]
    reviewed_assets = [a for a in active_assets if str(getattr(a, "review_status", "") or "").lower() in _REVIEWED]
    approved_assets = [a for a in active_assets if str(getattr(a, "review_status", "") or "").lower() in _APPROVED]
    eligible_assets = [
        a for a in completed_assets
        if str(getattr(a, "review_status", "") or "").lower() in (_REVIEWED | _HUMAN_ROUTED)
    ]
    auto_approved_assets = [
        a for a in eligible_assets if str(getattr(a, "review_status", "") or "").lower() == "auto_approved"
    ]
    human_review_assets = [
        a for a in eligible_assets if str(getattr(a, "review_status", "") or "").lower() in _HUMAN_ROUTED
    ]

    threshold = confidence_threshold if confidence_threshold is not None else None
    escalated_assets = []
    if threshold is not None:
        for asset in eligible_assets:
            status = str(getattr(asset, "review_status", "") or "").lower()
            reason = str(getattr(asset, "review_reason", "") or "").lower()
            asset_confidences = [
                float(getattr(annotation, "confidence"))
                for annotation in annotations_by_asset[asset.id]
                if str(getattr(annotation, "source", "") or "").lower() == "ai"
                and _is_valid_confidence(getattr(annotation, "confidence", None))
            ]
            low_confidence = bool(asset_confidences) and sum(asset_confidences) / len(asset_confidences) < threshold
            explicit_escalation = status in _HUMAN_ROUTED and (
                "confidence" in reason or "threshold" in reason or low_confidence
            )
            if explicit_escalation:
                escalated_assets.append(asset)

    modified_escalated_assets = [
        asset for asset in escalated_assets if _is_human_modified(asset, annotations_by_asset[asset.id])
    ]

    approved_first_pass_count = 0
    corrected_reworked_count = 0
    defective_annotations_count = 0
    for asset in reviewed_assets:
        status = str(getattr(asset, "review_status", "") or "").lower()
        reprocess_count = int(getattr(asset, "reprocess_count", 0) or 0)
        review_reason = str(getattr(asset, "review_reason", "") or "").lower()
        asset_id = getattr(asset, "id", "")
        is_modified = _is_human_modified(asset, annotations_by_asset.get(asset_id, []))

        if (
            status in _APPROVED
            and status != "human_modified_approved"
            and reprocess_count == 0
            and not is_modified
            and not any(term in review_reason for term in ("modify", "reworked", "reprocess", "corrected"))
        ):
            approved_first_pass_count += 1

        is_reworked = (
            status in _REWORKED
            or reprocess_count > 0
            or is_modified
            or any(term in review_reason for term in ("modify", "modified", "reworked", "reprocess", "corrected", "add_missing", "edit"))
        )
        if is_reworked:
            corrected_reworked_count += 1

        is_defective = (
            status in _REJECTED
            or any(term in review_reason for term in ("defect", "wrong_class", "missing_object", "incorrect_polygon", "poor_segmentation", "wrong_bbox", "invalid_geometry", "out_of_bounds", "quality_policy", "rejected"))
        )
        if is_defective:
            defective_annotations_count += 1

    total_reviewed_count = len(reviewed_assets)
    review_acceptance_rate = calculate_review_acceptance_rate(approved_first_pass_count, total_reviewed_count)
    rework_rate = calculate_rework_rate(corrected_reworked_count, total_reviewed_count)
    defect_rate = calculate_defect_rate(defective_annotations_count, total_reviewed_count)

    # Double-review pairing for Cohen's Kappa Reviewer Agreement
    double_review_pairs: list[tuple[str, str]] = []
    seen_assets: set[str] = set()

    for asset in active_assets:
        r1 = getattr(asset, "reviewer_1_decision", None) or (asset.get("reviewer_1_decision") if isinstance(asset, dict) else None)
        r2 = getattr(asset, "reviewer_2_decision", None) or (asset.get("reviewer_2_decision") if isinstance(asset, dict) else None)
        if r1 and r2:
            double_review_pairs.append((str(r1).lower().strip(), str(r2).lower().strip()))
            asset_id = str(getattr(asset, "id", None) or (asset.get("id") if isinstance(asset, dict) else ""))
            if asset_id:
                seen_assets.add(asset_id)

    if double_review_events:
        events_by_asset: dict[str, dict[str, str]] = {}
        for ev in double_review_events:
            asset_id = str(getattr(ev, "asset_id", None) or (ev.get("asset_id") if isinstance(ev, dict) else None) or "")
            if not asset_id or asset_id in seen_assets:
                continue
            reviewer = str(
                (getattr(ev, "metadata", {}) or {}).get("reviewer_tier")
                or getattr(ev, "actor_id", None)
                or (ev.get("actor_id") if isinstance(ev, dict) else None)
                or (ev.get("metadata", {}) if isinstance(ev, dict) else {}).get("reviewer_tier")
                or ""
            )
            action = str(getattr(ev, "action", None) or (ev.get("action") if isinstance(ev, dict) else None) or "").lower().strip()
            if reviewer and action in {"approve", "reject", "modify", "add_missing", "reprocess", "escalate", "human_approved", "human_rejected"}:
                events_by_asset.setdefault(asset_id, {})[reviewer] = action

        for asset_id, reviewers_dict in events_by_asset.items():
            if len(reviewers_dict) >= 2:
                rev_keys = sorted(reviewers_dict.keys())
                r1_dec = reviewers_dict[rev_keys[0]]
                r2_dec = reviewers_dict[rev_keys[1]]
                double_review_pairs.append((r1_dec, r2_dec))

    reviewer_agreement = calculate_reviewer_agreement(double_review_pairs)
    quality_index = calculate_quality_index(
        review_acceptance_rate,
        reviewer_agreement,
        rework_rate,
        defect_rate,
    )

    # 4 New Analytics Metrics
    escalated_items_count = sum(
        1 for asset in reviewed_assets
        if str(getattr(asset, "review_status", "") or "").lower() in {"escalated", "human_escalated"}
        or "escalat" in str(getattr(asset, "review_reason", "") or "").lower()
    )
    escalation_rate = calculate_escalation_rate(escalated_items_count, len(reviewed_assets))

    majority_approved_count = sum(
        1 for r1, r2 in double_review_pairs
        if r1 in _APPROVED and r2 in _APPROVED
    )
    consensus_pass_rate = calculate_consensus_pass_rate(majority_approved_count, len(double_review_pairs))

    total_review_minutes = None
    if double_review_events:
        valid_durations = []
        for ev in double_review_events:
            dur_ms = (getattr(ev, "metadata", {}) or {}).get("duration_ms") or (ev.get("metadata", {}) if isinstance(ev, dict) else {}).get("duration_ms")
            if dur_ms and isinstance(dur_ms, (int, float)) and dur_ms > 0:
                valid_durations.append(dur_ms / 60000.0)
            else:
                dur_sec = (getattr(ev, "metadata", {}) or {}).get("time_spent_seconds") or (ev.get("metadata", {}) if isinstance(ev, dict) else {}).get("time_spent_seconds")
                if dur_sec and isinstance(dur_sec, (int, float)) and dur_sec > 0:
                    valid_durations.append(dur_sec / 60.0)
        if valid_durations:
            total_review_minutes = sum(valid_durations)

    average_review_time = calculate_average_review_time(total_review_minutes, len(reviewed_assets))

    annotator_hours = (total_review_minutes / 60.0) if total_review_minutes is not None and total_review_minutes > 0 else (
        (throughput_per_hour and throughput_per_hour > 0 and len(completed_assets) > 0)
        and round(len(completed_assets) / throughput_per_hour, 2)
        or None
    )

    annotation_productivity = calculate_annotation_productivity(approved_annotations, annotator_hours)

    confidence = round(sum(valid_confidences) / len(valid_confidences) * 100.0, 1) if valid_confidences else None
    unit_production_cost = (
        round(total_production_cost / approved_annotations, 2)
        if total_production_cost is not None and approved_annotations > 0
        else None
    )
    processed_images = len(active_assets)
    approved_images = len(approved_assets)
    effective_run_target = target_images if (target_images and target_images > 0) else total_assets
    class_breakdown = [
        {
            "label": label,
            "annotation_count": values["annotation_count"],
            "image_count": len(values["image_ids"]),
            "approved_annotation_count": values["approved_count"],
            # The dashboard card is a completion breakdown, so show the
            # portion of the target dataset containing this class. Approval
            # remains available through approved_annotation_count.
            "approved_percentage": _percentage(len(values["image_ids"]), effective_run_target),
        }
        for label, values in sorted(class_counts.items())
    ]
    # Dataset completion measures annotation/processing progress. Approval is
    # reported separately, so pending HITL items must still count as completed
    # work once their annotation or processing result is persisted.
    completed_annotation_assets = sum(
        1
        for asset in active_assets
        if asset.id in annotated_asset_ids
        or str(getattr(asset, "status", "") or "").lower() in _COMPLETED
        or str(getattr(asset, "review_status", "") or "").lower() in (_REVIEWED | _HUMAN_ROUTED)
    )
    completion_rate_val = _percentage(completed_annotation_assets, effective_run_target) if effective_run_target > 0 else 0.0

    snapshot = {
        "project_id": project_id,
        "images_processed": total_assets,
        "completion_rate": completion_rate_val,
        "approval_rate": _percentage(len(approved_assets), len(reviewed_assets)),
        "review_acceptance_rate": review_acceptance_rate,
        "rework_rate": rework_rate,
        "defect_rate": defect_rate,
        "reviewer_agreement": reviewer_agreement,
        "quality_yield": quality_index,
        "quality_index": quality_index,
        "average_review_time": average_review_time,
        "escalation_rate": escalation_rate,
        "consensus_pass_rate": consensus_pass_rate,
        "annotation_productivity": annotation_productivity,
        "annotation_confidence": confidence,
        "automation_rate": _percentage(len(auto_approved_assets), total_assets),
        "hitl_rate": _percentage(len(human_review_assets), total_assets),
        "low_confidence_escalation_rate": _percentage(len(escalated_assets), len(eligible_assets)),
        "human_override_rate": _percentage(len(modified_escalated_assets), len(escalated_assets)),
        "unit_production_cost": unit_production_cost,
        "production_overview": {
            "processed_images": processed_images,
            "approved_images": approved_images,
            "approved_yield": _percentage(approved_images, processed_images),
            "reworked_images": corrected_reworked_count,
            "rework_rate": rework_rate,
            "rejected_images": defective_annotations_count,
            "rejection_rate": defect_rate,
            "defect_rate": defect_rate,
            "throughput_per_hour": throughput_per_hour,
            "target_images": target_images,
            "completion_progress": (
                round(min(100.0, max(0.0, completed_annotation_assets / target_images * 100.0)), 1)
                if target_images and target_images > 0
                else (round(min(100.0, max(0.0, completed_annotation_assets / total_assets * 100.0)), 1) if total_assets > 0 else 0.0)
            ),
            "class_breakdown": class_breakdown,
            "throughput_trend": [],
        },
        "population": {
            "total_assets": total_assets,
            "ai_annotated_assets": len(ai_annotated_assets),
            "completed_assets": len(completed_assets),
            "reviewed_assets": len(reviewed_assets),
            "approved_assets": len(approved_assets),
            "approved_first_pass_assets": approved_first_pass_count,
            "pending_final_assets": max(0, total_assets - approved_images),
            "reworked_assets": corrected_reworked_count,
            "defective_assets": defective_annotations_count,
            "double_reviewed_assets": len(double_review_pairs),
            "eligible_assets": len(eligible_assets),
            "human_review_assets": len(human_review_assets),
            "escalated_assets": len(escalated_assets),
            "human_modified_assets": len(modified_escalated_assets),
        },
        "calculation_metadata": {
            "confidence_threshold": threshold,
            "generated_at": datetime.now(UTC).isoformat(),
            "data_source": "persisted_project_data",
        },
    }
    return validate_kpi_snapshot(snapshot)


__all__ = [
    "AnalyticsValidationError",
    "calculate_project_kpis",
    "calculate_defect_rate",
    "calculate_rework_rate",
    "calculate_review_acceptance_rate",
    "calculate_reviewer_agreement",
    "calculate_quality_index",
    "calculate_average_review_time",
    "calculate_escalation_rate",
    "calculate_consensus_pass_rate",
    "calculate_annotation_productivity",
    "validate_kpi_snapshot",
]
