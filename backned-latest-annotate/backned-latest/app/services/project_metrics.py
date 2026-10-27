"""Pure project-level review metrics from current asset statuses."""

from collections.abc import Iterable

PENDING_REVIEW_STATUSES = {"pending", "review", "human_review", "needs_review", "unassigned"}
AUTO_APPROVED_STATUSES = {"auto_approved", "high_confidence_auto_pass"}
HUMAN_APPROVED_STATUSES = {"human_approved", "human_modified_approved", "approved"}
REJECTED_STATUSES = {"human_rejected", "rejected", "flagged"}
REWORK_STATUSES = {"reprocess_required", "human_rework_required", "rework", "needs_rework"}


def calculate_scorecard_metrics(
    assets: Iterable[dict],
    *,
    confidence_threshold: float | None = None,
) -> dict[str, float | int]:
    """Calculate dashboard scorecard values from persisted asset state.

    The dashboard must not invent production volume or rates. Every value here
    is derived from the assets currently stored for the project.
    """
    asset_list = list(assets)
    total_docs = len(asset_list)
    statuses = [asset.get("review_status") or asset.get("status") for asset in asset_list]
    summary = summarize_review_statuses(statuses)
    auto_approved_docs = summary["auto_approved_count"]
    human_review_docs = max(0, total_docs - auto_approved_docs)
    rework_docs = summary["rework_count"]

    auto_rate = (auto_approved_docs / total_docs * 100) if total_docs else 0.0
    human_review_rate = (human_review_docs / total_docs * 100) if total_docs else 0.0
    human_edit_rate = (rework_docs / total_docs * 100) if total_docs else 0.0

    # Transparent business assumptions, applied only to real auto-approved work.
    manual_seconds_per_document = 45
    reviewer_cost_per_hour = 24
    time_saved_hrs = auto_approved_docs * manual_seconds_per_document / 3600
    cost_saved_dollars = time_saved_hrs * reviewer_cost_per_hour

    result: dict[str, float | int] = {
        "total_docs": total_docs,
        "auto_approved_docs": auto_approved_docs,
        "auto_rate": round(auto_rate, 1),
        "human_review_docs": human_review_docs,
        "human_review_rate": round(human_review_rate, 1),
        "human_edit_rate": round(human_edit_rate, 1),
        "cost_saved_dollars": round(cost_saved_dollars, 2),
        "time_saved_hrs": round(time_saved_hrs, 2),
        "workload_delta_pct": round(human_review_rate - 100, 1),
    }
    if confidence_threshold is not None:
        result["threshold"] = round(float(confidence_threshold), 4)
    return result


_TASK_LABELS = {
    "text_extraction": "Text Extraction",
    "ocr": "Text Extraction",
    "ner": "NER Annotation",
    "entity_extraction": "NER Annotation",
    "sentiment": "Sentiment Analysis",
    "sentiment_analysis": "Sentiment Analysis",
    "relation": "Relation Extraction",
    "relation_extraction": "Relation Extraction",
    "classification": "Text Classification",
    "text_classification": "Text Classification",
}


def calculate_annotation_breakdown(
    assets: Iterable[dict],
    annotations: Iterable[dict] = (),
) -> list[dict[str, object]]:
    """Group real assets by their persisted task type and review outcome."""
    groups: dict[str, list[dict]] = {}
    annotations_by_asset: dict[str, list[dict]] = {}
    for annotation in annotations:
        asset_id = str(annotation.get("asset_id") or "")
        if asset_id:
            annotations_by_asset.setdefault(asset_id, []).append(annotation)
    for asset in assets:
        raw_task = str(
            asset.get("task_type")
            or asset.get("annotation_type")
            or asset.get("workflow_type")
            or asset.get("text_analysis_type")
            or (asset.get("text_analysis") or {}).get("analysis_type")
            or "uncategorized"
        ).strip().lower().replace(" ", "_")
        label = _TASK_LABELS.get(raw_task, raw_task.replace("_", " ").title())
        groups.setdefault(label, []).append(asset)

    breakdown: list[dict[str, object]] = []
    for label, group in groups.items():
        total = len(group)
        auto = sum(
            str(asset.get("review_status") or asset.get("status") or "").lower()
            in AUTO_APPROVED_STATUSES
            for asset in group
        )
        hitl = total - auto
        confidence_values = [
            float(annotation["confidence"])
            for asset in group
            for annotation in annotations_by_asset.get(str(asset.get("id") or ""), [])
            if str(annotation.get("source") or "").lower() in {"ai", "model"}
            and isinstance(annotation.get("confidence"), (int, float))
            and 0 <= float(annotation["confidence"]) <= 1
        ]
        breakdown.append({
            "id": label.lower().replace(" ", "_"),
            "name": label,
            "total_docs": total,
            "ai_processed_docs": auto,
            "ai_processed_pct": round(auto / total * 100, 1) if total else 0,
            "hitl_docs": hitl,
            "hitl_pct": round(hitl / total * 100, 1) if total else 0,
            "accuracy": round(sum(confidence_values) / len(confidence_values) * 100, 1) if confidence_values else None,
            "cost_saved_dollars": round(auto * 45 / 3600 * 24, 2),
        })
    return sorted(breakdown, key=lambda item: str(item["name"]))


def calculate_area_identification(annotations: Iterable[dict], total_docs: int) -> list[dict[str, object]]:
    """Aggregate persisted annotations into the area-identification table."""
    groups: dict[str, list[dict]] = {}
    for annotation in annotations:
        label = str(annotation.get("label") or annotation.get("name") or "Unlabelled").strip()
        if label:
            groups.setdefault(label, []).append(annotation)

    rows: list[dict[str, object]] = []
    for label, items in groups.items():
        confidences = [float(item["confidence"]) for item in items if item.get("confidence") is not None]
        asset_ids = {str(item.get("asset_id")) for item in items if item.get("asset_id")}
        ai_items = [item for item in items if str(item.get("source") or "").lower() in {"ai", "model"}]
        sample = next(
            (
                item.get("text_span", {}).get("text")
                or item.get("geometry", {}).get("text")
                or label
            )
            for item in ai_items or items
        )
        raw_category = str(items[0].get("annotation_type") or items[0].get("geometry_type") or "Annotation").lower()
        category_map = {
            "text_span": "NER Span",
            "text_classification": "Classification",
            "text_relation": "Relation",
            "ner": "NER Span",
            "sentiment": "Sentiment Aspect",
            "clinical": "Clinical Concept",
            "box": "Detection Box",
            "polygon": "Polygon Mask",
        }
        category = category_map.get(raw_category, raw_category.replace("_", " ").title())
        rows.append({
            "area_name": label,
            "category": category,
            "ai_confidence": round(sum(confidences) / len(confidences) * 100, 1) if confidences else None,
            "identification_rate": round(len(asset_ids) / total_docs * 100, 1) if total_docs else 0,
            # No prior-period snapshot exists for a newly ingested project.
            # Do not present a fabricated percentage as historical movement.
            # The first observation is explicitly labelled as the baseline.
            "trend_direction": "stable",
            "trend_change": "Initial baseline",
            "sample_identified": str(sample)[:180],
            "volume": len(items),
        })
    return sorted(rows, key=lambda row: str(row["area_name"]))


def calculate_annotator_metrics(
    assets: Iterable[dict],
    decisions: Iterable[dict],
    review_notes: Iterable[dict],
) -> list[dict[str, object]]:
    """Calculate reviewer throughput and safeguard metrics from persisted records."""
    groups: dict[str, dict[str, object]] = {}

    def group_for(raw_id: object, raw_name: object = None) -> dict[str, object] | None:
        key = str(raw_id or raw_name or "").strip()
        if not key:
            return None
        return groups.setdefault(key, {"id": key, "name": str(raw_name or key), "assigned": 0, "completed": 0, "durations": [], "edits": 0, "audits": 0, "passes": 0, "fails": 0})

    for asset in assets:
        group = group_for(asset.get("assigned_to") or asset.get("annotator_id"), asset.get("assigned_to_name"))
        if not group:
            continue
        group["assigned"] = int(group["assigned"]) + 1
        status = str(asset.get("review_status") or "").lower()
        if status in {"human_approved", "human_modified_approved", "human_rejected", "final_approved", "approved", "rejected"}:
            group["completed"] = int(group["completed"]) + 1
        started = asset.get("review_started_at") or asset.get("started_at")
        finished = asset.get("review_completed_at") or asset.get("completed_at")
        if started and finished:
            try:
                duration = (finished - started).total_seconds()
                if duration >= 0:
                    group["durations"].append(duration)
            except (AttributeError, TypeError):
                pass

    for decision in decisions:
        group = group_for(decision.get("annotator_id") or decision.get("reviewer_id") or decision.get("assigned_to"), decision.get("annotator_name"))
        if not group:
            continue
        if decision.get("edited") or decision.get("human_modified") or decision.get("reviewer_edited"):
            group["edits"] = int(group["edits"]) + 1

    for note in review_notes:
        group = group_for(note.get("annotator_id") or note.get("reviewer_id") or note.get("created_by"), note.get("annotator_name"))
        if not group:
            continue
        group["audits"] = int(group["audits"]) + 1
        if str(note.get("qc_decision") or note.get("result") or "").upper() == "PASS":
            group["passes"] = int(group["passes"]) + 1
        else:
            group["fails"] = int(group["fails"]) + 1

    result = []
    for group in groups.values():
        assigned = int(group["assigned"])
        completed = int(group["completed"])
        audits = int(group["audits"])
        avg_time = sum(group["durations"]) / len(group["durations"]) if group["durations"] else None
        edit_rate = int(group["edits"]) / completed * 100 if completed else None
        pass_rate = int(group["passes"]) / audits * 100 if audits else None
        flagged = bool(avg_time is not None and avg_time < 15 and edit_rate is not None and edit_rate < 3)
        result.append({
            "id": group["id"], "name": group["name"], "role": "Reviewer",
            "assigned_docs": assigned, "completed_docs": completed,
            "avg_time_sec": round(avg_time, 1) if avg_time is not None else None,
            "ai_edit_rate": round(edit_rate, 1) if edit_rate is not None else None,
            "audit_pass_rate": round(pass_rate, 1) if pass_rate is not None else None,
            "status": "flagged" if flagged else "normal",
        })
    return sorted(result, key=lambda row: str(row["name"]))


def calculate_triage_metrics(
    assets: Iterable[dict], annotations: Iterable[dict], decisions: Iterable[dict], confidence_threshold: float = 0.9
) -> dict[str, int]:
    """Calculate actionable queue sizes from persisted review evidence."""
    disputed = 0
    low_latency = 0
    for decision in decisions:
        first = decision.get("reviewer_1_decision")
        second = decision.get("reviewer_2_decision")
        status = str(decision.get("status") or "").lower()
        if (first and second and first != second) or status in {"disputed", "conflict", "needs_arbitration"}:
            disputed += 1
        duration = decision.get("duration_sec") or decision.get("time_spent_sec")
        edited = decision.get("edited") or decision.get("human_modified") or decision.get("reviewer_edited")
        try:
            if float(duration) < 12 and not edited:
                low_latency += 1
        except (TypeError, ValueError):
            pass
    low_confidence = {
        str(asset.get("id")) for asset in assets
        if asset.get("mean_confidence") is not None and float(asset["mean_confidence"]) < confidence_threshold
    }
    low_confidence.update(
        str(annotation.get("asset_id")) for annotation in annotations
        if annotation.get("confidence") is not None and float(annotation["confidence"]) < confidence_threshold
    )
    return {
        "disputed_count": disputed,
        "low_latency_count": low_latency,
        "active_learning_count": len({item for item in low_confidence if item and item != "None"}),
    }


def summarize_review_statuses(statuses: Iterable[str | None]) -> dict[str, int]:
    normalized = [str(status or "pending").lower() for status in statuses]
    return {
        "pending_review_count": sum(status in PENDING_REVIEW_STATUSES for status in normalized),
        "auto_approved_count": sum(status in AUTO_APPROVED_STATUSES for status in normalized),
        "human_approved_count": sum(status in HUMAN_APPROVED_STATUSES for status in normalized),
        "rejected_count": sum(status in REJECTED_STATUSES for status in normalized),
        "rework_count": sum(status in REWORK_STATUSES for status in normalized),
    }
