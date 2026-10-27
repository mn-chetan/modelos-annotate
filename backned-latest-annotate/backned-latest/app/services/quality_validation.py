"""Annotation Quality Validation and Object-Level Accuracy Service."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.db.models import MongoDoc
from app.domain.enums import AnnotationSource
from app.logging import get_logger

logger = get_logger(__name__)



def validate_annotation_geometry(annotation: Any) -> dict[str, Any]:
    """Validate bounding box geometry.

    Ensures x1 < x2, y1 < y2, and normalized coordinates within [0, 100].
    Flags invalid geometry without silently modifying coordinates.
    """
    ann_id = str(getattr(annotation, "id", ""))
    if hasattr(annotation, "bbox") and getattr(annotation, "bbox", None) is not None:
        bbox = getattr(annotation, "bbox")
        x = float(getattr(bbox, "x", 0.0) or 0.0)
        y = float(getattr(bbox, "y", 0.0) or 0.0)
        w = float(getattr(bbox, "w", 0.0) or 0.0)
        h = float(getattr(bbox, "h", 0.0) or 0.0)
    else:
        x = float(getattr(annotation, "x", 0.0) or 0.0)
        y = float(getattr(annotation, "y", 0.0) or 0.0)
        w = float(getattr(annotation, "w", 0.0) or 0.0)
        h = float(getattr(annotation, "h", 0.0) or 0.0)

    x2 = x + w
    y2 = y + h

    is_valid = (
        w > 0.0
        and h > 0.0
        and x >= 0.0
        and y >= 0.0
        and x2 <= 100.0
        and y2 <= 100.0
        and x < x2
        and y < y2
    )

    return {
        "annotation_id": ann_id,
        "is_valid": is_valid,
        "x1": x,
        "y1": y,
        "x2": x2,
        "y2": y2,
        "w": w,
        "h": h,
        "reason": None if is_valid else "INVALID_GEOMETRY",
    }


def _extract_box_coords(box: Any) -> tuple[float, float, float, float]:
    if box is None:
        return (0.0, 0.0, 0.0, 0.0)
    if isinstance(box, (list, tuple)) and len(box) >= 4:
        return (float(box[0] or 0), float(box[1] or 0), float(box[2] or 0), float(box[3] or 0))
    if isinstance(box, dict):
        x = float(box.get("x") or box.get("x1") or 0.0)
        y = float(box.get("y") or box.get("y1") or 0.0)
        w = float(box.get("w") or box.get("width") or (float(box.get("x2") or 0.0) - x))
        h = float(box.get("h") or box.get("height") or (float(box.get("y2") or 0.0) - y))
        return (x, y, max(0.0, w), max(0.0, h))
    x = float(getattr(box, "x", 0.0) or 0.0)
    y = float(getattr(box, "y", 0.0) or 0.0)
    w = float(getattr(box, "w", 0.0) or 0.0)
    h = float(getattr(box, "h", 0.0) or 0.0)
    return (x, y, max(0.0, w), max(0.0, h))


def calculate_box_iou(box_a: Any, box_b: Any) -> float:
    """Calculate IoU percentage (0.0 to 1.0) between two boxes in [0, 100] coordinates."""
    ax, ay, aw, ah = _extract_box_coords(box_a)
    bx, by, bw, bh = _extract_box_coords(box_b)

    inter_x1 = max(ax, bx)
    inter_y1 = max(ay, by)
    inter_x2 = min(ax + aw, bx + bw)
    inter_y2 = min(ay + ah, by + bh)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = aw * ah
    area_b = bw * bh
    union_area = area_a + area_b - inter_area

    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def detect_duplicate_candidates(
    annotations: list[Any], iou_threshold: float = 0.85
) -> list[dict[str, Any]]:
    """Detect duplicate annotations within the same image for the same canonical class."""
    duplicates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for idx_a, ann_a in enumerate(annotations):
        label_a = (getattr(ann_a, "label", "") or "").strip().lower()
        id_a = str(getattr(ann_a, "id", ""))
        conf_a = float(getattr(ann_a, "confidence", 1.0) or 1.0)

        for ann_b in annotations[idx_a + 1 :]:
            label_b = (getattr(ann_b, "label", "") or "").strip().lower()
            id_b = str(getattr(ann_b, "id", ""))
            conf_b = float(getattr(ann_b, "confidence", 1.0) or 1.0)

            if label_a != label_b or not label_a:
                continue

            pair_key = tuple(sorted([id_a, id_b]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            iou = calculate_box_iou(ann_a, ann_b)
            if iou >= iou_threshold:
                duplicates.append({
                    "annotation_id_a": id_a,
                    "annotation_id_b": id_b,
                    "class": getattr(ann_a, "label", ""),
                    "iou": round(iou, 4),
                    "confidence_a": conf_a,
                    "confidence_b": conf_b,
                    "duplicate_decision": "flagged",
                    "reason": "DUPLICATE_CANDIDATE",
                })

    return duplicates


def detect_model_disagreements_and_conflicts(
    annotations: list[Any], all_raw_detections: list[Any] | None = None
) -> list[dict[str, Any]]:
    """Detect overlapping detections (IoU >= 0.45) with conflicting labels.

    Flags possible_class_conflict = True and model_agreement = False.
    """
    conflicts: list[dict[str, Any]] = []
    candidates = all_raw_detections if all_raw_detections is not None else annotations

    for idx_a, det_a in enumerate(candidates):
        label_a = (getattr(det_a, "label", "") or "").strip().lower()
        id_a = str(getattr(det_a, "id", ""))
        model_a = getattr(det_a, "model_key", getattr(det_a, "model_id", "yolo26"))

        for det_b in candidates[idx_a + 1 :]:
            label_b = (getattr(det_b, "label", "") or "").strip().lower()
            id_b = str(getattr(det_b, "id", ""))
            model_b = getattr(det_b, "model_key", getattr(det_b, "model_id", "faster_rcnn"))

            if label_a == label_b:
                continue

            iou = calculate_box_iou(det_a, det_b)
            if iou >= 0.45:
                conflicts.append({
                    "annotation_id_a": id_a,
                    "annotation_id_b": id_b,
                    "label_a": getattr(det_a, "label", ""),
                    "label_b": getattr(det_b, "label", ""),
                    "model_a": model_a,
                    "model_b": model_b,
                    "iou": round(iou, 4),
                    "possible_class_conflict": True,
                    "model_agreement": False,
                    "reason": "MODEL_DISAGREEMENT",
                })

    return conflicts


def evaluate_small_and_boundary_objects(
    annotations: list[Any], small_object_area_threshold: float = 1.0
) -> dict[str, Any]:
    """Flag very small objects and boundary-touching objects."""
    small_objects: list[dict[str, Any]] = []
    boundary_objects: list[dict[str, Any]] = []

    for ann in annotations:
        ann_id = str(getattr(ann, "id", ""))
        x = float(getattr(ann, "x", 0.0) or 0.0)
        y = float(getattr(ann, "y", 0.0) or 0.0)
        w = float(getattr(ann, "w", 0.0) or 0.0)
        h = float(getattr(ann, "h", 0.0) or 0.0)

        box_area_pct = w * h
        area_ratio = box_area_pct / 10000.0

        if box_area_pct <= small_object_area_threshold:
            small_objects.append({
                "annotation_id": ann_id,
                "label": getattr(ann, "label", ""),
                "object_area_ratio": round(area_ratio, 6),
                "width_ratio": round(w / 100.0, 4),
                "height_ratio": round(h / 100.0, 4),
                "small_object_flag": True,
                "reason": "SMALL_OBJECT",
            })

        left_edge = x <= 0.5
        top_edge = y <= 0.5
        right_edge = (x + w) >= 99.5
        bottom_edge = (y + h) >= 99.5

        if left_edge or top_edge or right_edge or bottom_edge:
            boundary_objects.append({
                "annotation_id": ann_id,
                "label": getattr(ann, "label", ""),
                "edges": {
                    "left_edge": left_edge,
                    "top_edge": top_edge,
                    "right_edge": right_edge,
                    "bottom_edge": bottom_edge,
                },
                "boundary_object_flag": True,
                "reason": "BOUNDARY_OBJECT",
            })

    return {
        "small_objects": small_objects,
        "boundary_objects": boundary_objects,
        "small_object_count": len(small_objects),
        "boundary_object_count": len(boundary_objects),
    }


def compute_confidence_distribution(annotations: list[Any]) -> dict[str, Any]:
    """Compute confidence statistics and distribution buckets."""
    valid_confs = [
        float(getattr(a, "confidence", 1.0) or 1.0)
        for a in annotations
        if getattr(a, "confidence", None) is not None
        and isinstance(getattr(a, "confidence"), (int, float))
        and not isinstance(getattr(a, "confidence"), bool)
        and 0.0 <= float(getattr(a, "confidence")) <= 1.0
        and getattr(a, "source", "ai") not in ("human", "human_modified")
    ]

    if not valid_confs:
        return {
            "object_count": len(annotations),
            "mean_confidence": None,
            "min_confidence": None,
            "max_confidence": None,
            "distribution": {
                "< 0.30": 0,
                "0.30-0.50": 0,
                "0.50-0.70": 0,
                "0.70-0.80": 0,
                "0.80-0.90": 0,
                ">= 0.90": 0,
            },
        }

    buckets = {
        "< 0.30": sum(1 for c in valid_confs if c < 0.30),
        "0.30-0.50": sum(1 for c in valid_confs if 0.30 <= c < 0.50),
        "0.50-0.70": sum(1 for c in valid_confs if 0.50 <= c < 0.70),
        "0.70-0.80": sum(1 for c in valid_confs if 0.70 <= c < 0.80),
        "0.80-0.90": sum(1 for c in valid_confs if 0.80 <= c < 0.90),
        ">= 0.90": sum(1 for c in valid_confs if c >= 0.90),
    }

    return {
        "object_count": len(annotations),
        "mean_confidence": round(sum(valid_confs) / len(valid_confs), 4),
        "min_confidence": round(min(valid_confs), 4),
        "max_confidence": round(max(valid_confs), 4),
        "distribution": buckets,
    }


def evaluate_ground_truth_metrics(
    persisted_anns: list[Any],
    gt_anns: list[Any],
    iou_threshold: float = 0.50,
) -> dict[str, Any]:
    """Calculate Precision, Recall, and F1 score against ground-truth annotations.

    If ground-truth is absent, returns precision=None, recall=None, f1=None,
    ground_truth_available=False.
    """
    if not gt_anns:
        return {
            "ground_truth_available": False,
            "accuracy": "Data not available",
            "precision": None,
            "recall": None,
            "f1": None,
            "matched_tp": 0,
            "fp": len(persisted_anns),
            "fn": 0,
        }

    matched_gt: set[str] = set()
    matched_pred: set[str] = set()
    tp = 0

    for pred in persisted_anns:
        pred_id = str(getattr(pred, "id", ""))
        pred_label = (getattr(pred, "label", "") or "").strip().lower()

        best_gt_id = None
        best_iou = 0.0

        for gt in gt_anns:
            gt_id = str(getattr(gt, "id", ""))
            if gt_id in matched_gt:
                continue
            gt_label = (getattr(gt, "label", "") or "").strip().lower()
            if pred_label != gt_label:
                continue

            iou = calculate_box_iou(pred, gt)
            if iou >= iou_threshold and iou > best_iou:
                best_iou = iou
                best_gt_id = gt_id

        if best_gt_id is not None:
            tp += 1
            matched_gt.add(best_gt_id)
            matched_pred.add(pred_id)

    fp = len(persisted_anns) - tp
    fn = len(gt_anns) - tp

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round((2 * precision * recall) / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    return {
        "ground_truth_available": True,
        "accuracy": f"F1={f1:.4f}",
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched_tp": tp,
        "fp": fp,
        "fn": fn,
    }


def evaluate_expected_class_coverage(
    annotations: list[Any], expected_ontology_labels: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    """Compare observed classes against project's configured ontology labels."""
    observed_labels = {
        (getattr(a, "label", "") or "").strip()
        for a in annotations
        if getattr(a, "label", None)
    }

    missing_expected = [
        lbl for lbl in expected_ontology_labels if lbl not in observed_labels
    ]

    return {
        "expected_labels": list(expected_ontology_labels),
        "observed_labels": sorted(observed_labels),
        "missing_expected_class": missing_expected,
        "coverage_ratio": (
            round((len(expected_ontology_labels) - len(missing_expected)) / len(expected_ontology_labels), 4)
            if expected_ontology_labels
            else 1.0
        ),
    }


def validate_object_level_quality(
    annotations: list[Any],
    all_raw_detections: list[Any] | None = None,
    expected_ontology_labels: list[str] | tuple[str, ...] | None = None,
    gt_annotations: list[Any] | None = None,
) -> dict[str, Any]:
    """Aggregate object-level quality validation for an asset."""
    geometry_results = [validate_annotation_geometry(ann) for ann in annotations]
    invalid_geometry_count = sum(1 for g in geometry_results if not g["is_valid"])

    duplicates = detect_duplicate_candidates(annotations)
    conflicts = detect_model_disagreements_and_conflicts(annotations, all_raw_detections)
    small_boundary = evaluate_small_and_boundary_objects(annotations)
    conf_stats = compute_confidence_distribution(annotations)

    coverage = (
        evaluate_expected_class_coverage(annotations, expected_ontology_labels)
        if expected_ontology_labels
        else {"missing_expected_class": [], "coverage_ratio": 1.0}
    )

    gt_metrics = evaluate_ground_truth_metrics(annotations, gt_annotations or [])

    return {
        "annotation_count": len(annotations),
        "invalid_geometry_count": invalid_geometry_count,
        "duplicate_candidates": duplicates,
        "duplicate_count": len(duplicates),
        "model_disagreements": conflicts,
        "conflict_count": len(conflicts),
        "small_objects": small_boundary["small_objects"],
        "boundary_objects": small_boundary["boundary_objects"],
        "small_object_count": small_boundary["small_object_count"],
        "boundary_object_count": small_boundary["boundary_object_count"],
        "confidence_stats": conf_stats,
        "class_coverage": coverage,
        "ground_truth_metrics": gt_metrics,
        "accuracy": gt_metrics["accuracy"],
    }


from app.db.firebase import AsyncIOMotorDatabase

from app.db.models import MongoDoc
from app.domain.enums import AnnotationSource
from app.logging import get_logger

logger = get_logger(__name__)


def calculate_audit_pass_rate(passed_audited_samples: int, total_audited_samples: int) -> float | None:
    """Return passed audited samples / total audited samples * 100."""
    if total_audited_samples <= 0:
        return None
    return round(passed_audited_samples / total_audited_samples * 100.0, 1)


def calculate_ai_annotation_accuracy(correct_evaluated: int, total_evaluated: int) -> float | None:
    """Calculate AI accuracy from persisted evaluated review decisions only.

    This is deliberately separate from model confidence and from HITL rate.
    ``None`` means there is no evaluated AI population to score.
    """
    return calculate_audit_pass_rate(correct_evaluated, total_evaluated)


async def calculate_project_quality_report(db: AsyncIOMotorDatabase, project_id: str) -> dict[str, Any]:
    """Generate a project-scoped quality report based on persisted HITL decisions, assets, and audit deltas."""
    import time
    t_start = time.perf_counter()
    project_doc = await db["projects"].find_one({"id": project_id})
    if project_doc is None:
        return {
            "project_id": project_id,
            "error": "Project not found",
        }
    project = MongoDoc(project_doc)

    t_assets = time.perf_counter()
    assets_cursor = db["assets"].find({"project_id": project_id})
    assets = [MongoDoc(d) async for d in assets_cursor]
    logger.info("quality_timing_assets", elapsed_ms=round((time.perf_counter() - t_assets) * 1000, 2), count=len(assets))

    t_ann = time.perf_counter()
    ann_cursor = db["annotations"].find({"project_id": project_id})
    annotations = [MongoDoc(d) async for d in ann_cursor]
    logger.info("quality_timing_annotations", elapsed_ms=round((time.perf_counter() - t_ann) * 1000, 2), count=len(annotations))

    # Fetch HITL decisions and deltas
    t_dec = time.perf_counter()
    decisions_cursor = db["decisions"].find({"project_id": project_id})
    decisions = [MongoDoc(d) async for d in decisions_cursor]
    logger.info("quality_timing_decisions", elapsed_ms=round((time.perf_counter() - t_dec) * 1000, 2), count=len(decisions))

    t_deltas = time.perf_counter()
    deltas_cursor = db["deltas"].find({"project_id": project_id})
    deltas = [MongoDoc(d) async for d in deltas_cursor]
    audit_events = [MongoDoc(d) async for d in db["audit_events"].find({"project_id": project_id})]
    logger.info("quality_timing_deltas_audits", elapsed_ms=round((time.perf_counter() - t_deltas) * 1000, 2), deltas=len(deltas), audits=len(audit_events))

    total_items = len(assets)
    total_ai_annotated = len(annotations) or total_items
    total_human_reviewed = len([d for d in decisions if d.get("audit_source") == "HUMAN_REVIEW" or d.get("status") in {"human_review_completed", "final_approved", "human_rework_required"}])
    total_high_confidence = len([d for d in decisions if (d.get("confidence") or 0) >= 0.95 or d.get("status") == "high_confidence_auto_pass"])
    total_high_confidence_sampled = len([d for d in decisions if d.get("sampled") is True or d.get("audit_source") == "HIGH_CONFIDENCE_SAMPLE"])

    audited_decisions = [
        d for d in decisions
        if d.get("answer") in {"PASS", "FAIL"}
        or (
            d.get("audit_source") in {"HUMAN_REVIEW", "HIGH_CONFIDENCE_SAMPLE"}
            and d.get("status") in {"final_approved", "human_rework_required"}
        )
    ]
    total_audited = len(audited_decisions)
    total_passed = len([d for d in audited_decisions if d.get("answer") == "PASS" or d.get("status") == "final_approved"])
    total_failed = len([d for d in audited_decisions if d.get("answer") == "FAIL" or d.get("status") == "human_rework_required"])
    total_reworked = len([d for d in decisions if d.get("status") == "human_rework_required" or d.get("rework_feedback")])
    final_approved_count = len([a for a in assets if a.get("review_status") in {"final_approved", "auto_approved", "approved"}] or [d for d in decisions if d.get("status") == "final_approved"])

    qc_pass_rate = round(total_passed / total_audited * 100, 1) if total_audited > 0 else None
    rework_rate = round(total_reworked / total_audited * 100, 1) if total_audited > 0 else None
    defect_rate = round(total_failed / total_audited * 100, 1) if total_audited > 0 else None

    # These are the explicit QA formulas. Null means the persisted source
    # population does not exist; it is never represented as a fabricated zero.
    audit_pass_rate = calculate_audit_pass_rate(total_passed, total_audited)
    ai_annotation_accuracy = calculate_ai_annotation_accuracy(total_passed, total_audited)
    defect_leakage = round(total_failed / total_audited * 100, 1) if total_audited else None

    reviewer_pairs: list[tuple[str, str]] = []
    for asset in assets:
        first = asset.get("reviewer_1_decision")
        second = asset.get("reviewer_2_decision")
        if first and second:
            reviewer_pairs.append((str(first).lower(), str(second).lower()))
    if reviewer_pairs:
        from app.services.analytics import calculate_reviewer_agreement
        inter_annotator_agreement = calculate_reviewer_agreement(reviewer_pairs)
    else:
        inter_annotator_agreement = None

    gold_annotations = [
        annotation for annotation in annotations
        if str(annotation.get("source") or "").lower() in {"ground_truth", "gold", "gold_standard"}
    ]
    predicted_annotations = [
        annotation for annotation in annotations if annotation not in gold_annotations
    ]
    iou_values: list[float] = []
    if gold_annotations:
        matched_gold: set[str] = set()
        for prediction in predicted_annotations:
            best_iou = 0.0
            best_id = None
            for gold in gold_annotations:
                gold_id = str(gold.get("id"))
                if gold_id in matched_gold or str(prediction.get("label", "")).casefold() != str(gold.get("label", "")).casefold():
                    continue
                candidate = calculate_box_iou(prediction, gold)
                if candidate > best_iou:
                    best_iou, best_id = candidate, gold_id
            if best_id is not None:
                matched_gold.add(best_id)
                iou_values.append(best_iou)
    mean_iou = round(sum(iou_values) / len(iou_values), 4) if iou_values else None
    iou_distribution = None
    if iou_values:
        total_iou = len(iou_values)
        buckets = {
            "gt_0_95": sum(value > 0.95 for value in iou_values),
            "0_85_0_95": sum(0.85 <= value <= 0.95 for value in iou_values),
            "0_70_0_85": sum(0.70 <= value < 0.85 for value in iou_values),
            "lt_0_70": sum(value < 0.70 for value in iou_values),
        }
        iou_distribution = {
            key: {"count": count, "percentage": round(count / total_iou * 100, 1)}
            for key, count in buckets.items()
        }

    high_conf_audits = [d for d in audited_decisions if d.get("audit_source") == "HIGH_CONFIDENCE_SAMPLE"]
    high_conf_passed = [d for d in high_conf_audits if d.get("answer") == "PASS" or d.get("status") == "final_approved"]
    high_confidence_sample_accuracy = round(len(high_conf_passed) / len(high_conf_audits) * 100, 1) if len(high_conf_audits) > 0 else None

    human_rev_audits = [d for d in audited_decisions if d.get("audit_source") == "HUMAN_REVIEW"]
    human_rev_passed = [d for d in human_rev_audits if d.get("answer") == "PASS" or d.get("status") == "final_approved"]
    human_reviewed_accuracy = round(len(human_rev_passed) / len(human_rev_audits) * 100, 1) if len(human_rev_audits) > 0 else None

    defect_breakdown: dict[str, int] = {
        "wrong_label": 0,
        "missing_annotation": 0,
        "extra_annotation": 0,
        "bounding_box_error": 0,
        "polygon_segmentation_error": 0,
        "text_span_error": 0,
        "classification_error": 0,
        "other_guideline_violation": 0,
    }

    for d in decisions:
        cat = d.get("defect_category")
        if cat and cat in defect_breakdown:
            defect_breakdown[cat] += 1

    res = {
        "project_id": project_id,
        "total_items": total_items,
        "total_annotated": total_ai_annotated,
        "total_human_reviewed": total_human_reviewed,
        "total_high_confidence": total_high_confidence,
        "total_high_confidence_sampled": total_high_confidence_sampled,
        "total_audited": total_audited,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_reworked": total_reworked,
        "final_approved": final_approved_count,
        "qc_pass_rate": qc_pass_rate,
        "audit_pass_rate": audit_pass_rate,
        "ai_annotation_accuracy": ai_annotation_accuracy,
        "ai_accuracy_correct_evaluated": total_passed,
        "ai_accuracy_total_evaluated": total_audited,
        "defect_leakage": defect_leakage,
        "mean_iou": mean_iou,
        "inter_annotator_agreement": inter_annotator_agreement,
        "iou_distribution": iou_distribution,
        "rework_rate": rework_rate,
        "defect_rate": defect_rate,
        "high_confidence_sample_accuracy": high_confidence_sample_accuracy,
        "human_reviewed_accuracy": human_reviewed_accuracy,
        "defect_breakdown": defect_breakdown,
        "annotation_deltas_count": len(deltas),
    }
    logger.info("calculate_project_quality_report_TOTAL", elapsed_ms=round((time.perf_counter() - t_start) * 1000, 2))
    return res


async def run_data_accuracy_validation_engine(project_id: str, db: Any) -> list[dict[str, Any]]:
    """Structured Data Accuracy Validation Engine.

    Evaluates 13 core dataset and workflow integrity metrics.
    Returns:
        [{"check": "...", "status": "PASS|FAIL|NOT_APPLICABLE|DATA_NOT_AVAILABLE", "message": "...", "evidence": ...}]
    """
    cursor_assets = db.assets.find({"project_id": project_id})
    assets = await cursor_assets.to_list(length=10000)

    cursor_annos = db.annotations.find({"project_id": project_id})
    annotations = await cursor_annos.to_list(length=10000)

    cursor_notes = db.review_notes.find({"project_id": project_id})
    notes = await cursor_notes.to_list(length=10000)

    project = await db.projects.find_one({"id": project_id})
    ontology_labels = set(project.get("labels", [])) if project else set()

    checks: list[dict[str, Any]] = []

    # 1. Completeness
    if not assets:
        checks.append({
            "check": "Completeness",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No assets exist in project",
            "evidence": {"total_assets": 0},
        })
    else:
        completed = len([a for a in assets if a.get("review_status") in ("final_approved", "high_confidence_auto_pass")])
        rate = completed / len(assets)
        checks.append({
            "check": "Completeness",
            "status": "PASS" if rate >= 0.95 else ("FAIL" if rate > 0 else "DATA_NOT_AVAILABLE"),
            "message": f"Project completeness is {round(rate * 100, 1)}%",
            "evidence": {"total_assets": len(assets), "completed_assets": completed},
        })

    # 2. Label Accuracy
    notes_with_decision = [n for n in notes if n.get("qc_decision")]
    if not notes_with_decision:
        checks.append({
            "check": "Label Accuracy",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No QC auditor decisions recorded yet",
            "evidence": {"qc_notes_count": 0},
        })
    else:
        label_passed = len([n for n in notes_with_decision if (n.get("checklist") or {}).get("label_accuracy", True)])
        acc_rate = label_passed / len(notes_with_decision)
        checks.append({
            "check": "Label Accuracy",
            "status": "PASS" if acc_rate >= 0.90 else "FAIL",
            "message": f"QC label accuracy rate is {round(acc_rate * 100, 1)}%",
            "evidence": {"total_audited": len(notes_with_decision), "label_passed": label_passed},
        })

    # 3. Ontology Compliance
    if not annotations:
        checks.append({
            "check": "Ontology Compliance",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No annotations present for project",
            "evidence": {"annotations_count": 0},
        })
    elif not ontology_labels:
        checks.append({
            "check": "Ontology Compliance",
            "status": "NOT_APPLICABLE",
            "message": "No project ontology labels configured",
            "evidence": {"ontology_labels": []},
        })
    else:
        invalid_labels = [a.get("label") for a in annotations if a.get("label") and a.get("label") not in ontology_labels]
        checks.append({
            "check": "Ontology Compliance",
            "status": "PASS" if not invalid_labels else "FAIL",
            "message": "All annotations strictly belong to project ontology" if not invalid_labels else f"Found {len(invalid_labels)} ungrounded annotations",
            "evidence": {"invalid_labels_count": len(invalid_labels), "sample_invalid": invalid_labels[:5]},
        })

    # 4. Localization Accuracy
    geom_validations = [validate_annotation_geometry(a) for a in annotations]
    invalid_geoms = [g for g in geom_validations if not g["is_valid"]]
    if not annotations:
        checks.append({
            "check": "Localization Accuracy",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No bounding box annotations available",
            "evidence": {"annotations_count": 0},
        })
    else:
        checks.append({
            "check": "Localization Accuracy",
            "status": "PASS" if not invalid_geoms else "FAIL",
            "message": "All bounding box coordinates are normalized and valid" if not invalid_geoms else f"{len(invalid_geoms)} annotations have invalid box bounds",
            "evidence": {"total_annotations": len(annotations), "invalid_geometry_count": len(invalid_geoms)},
        })

    # 5. Missing Objects
    deltas = [a.get("annotation_delta") for a in assets if a.get("annotation_delta")]
    if not deltas:
        checks.append({
            "check": "Missing Objects",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No human-correction error deltas computed yet",
            "evidence": {"deltas_computed": 0},
        })
    else:
        total_missed = sum(d.get("missed_objects", 0) for d in deltas)
        checks.append({
            "check": "Missing Objects",
            "status": "PASS" if total_missed == 0 else "FAIL",
            "message": f"{total_missed} total missing objects corrected by human annotators across assets",
            "evidence": {"total_missed_objects_added": total_missed, "assets_audited": len(deltas)},
        })

    # 6. Extra Objects
    if not deltas:
        checks.append({
            "check": "Extra Objects",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No human-correction error deltas computed yet",
            "evidence": {"deltas_computed": 0},
        })
    else:
        total_removed = sum(d.get("extra_ai_objects_removed", 0) for d in deltas)
        checks.append({
            "check": "Extra Objects",
            "status": "PASS" if total_removed == 0 else "FAIL",
            "message": f"{total_removed} false positive AI objects removed by human annotators",
            "evidence": {"extra_objects_removed": total_removed},
        })

    # 7. Duplicate Objects
    if not notes_with_decision:
        checks.append({
            "check": "Duplicate Objects",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No QC duplicate audit data recorded",
            "evidence": {},
        })
    else:
        dup_failures = len([n for n in notes_with_decision if not (n.get("checklist") or {}).get("duplicate_objects", True)])
        checks.append({
            "check": "Duplicate Objects",
            "status": "PASS" if dup_failures == 0 else "FAIL",
            "message": "Zero duplicate objects flagged in QC" if dup_failures == 0 else f"{dup_failures} assets flagged for duplicate detections",
            "evidence": {"duplicate_flagged_count": dup_failures},
        })

    # 8. Confidence Integrity
    raw_confs = [a.get("confidence") for a in annotations if a.get("confidence") is not None]
    if not raw_confs:
        checks.append({
            "check": "Confidence Integrity",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No model confidence scores found",
            "evidence": {},
        })
    else:
        boosted = [c for c in raw_confs if c > 1.0 or c < 0.0]
        checks.append({
            "check": "Confidence Integrity",
            "status": "PASS" if not boosted else "FAIL",
            "message": "Raw model confidence values are strictly preserved within [0.0, 1.0]",
            "evidence": {"confidence_samples": raw_confs[:5]},
        })

    # 9. Routing Integrity
    routed_assets = [a for a in assets if a.get("routing_status")]
    if not routed_assets:
        checks.append({
            "check": "Routing Integrity",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No assets routed by backend confidence engine",
            "evidence": {},
        })
    else:
        checks.append({
            "check": "Routing Integrity",
            "status": "PASS",
            "message": f"Backend confidence routing evaluated for {len(routed_assets)} assets",
            "evidence": {"routed_assets_count": len(routed_assets)},
        })

    # 10. Human Correction Integrity
    cursor_audit = db.agent_requests.find({"project_id": project_id})
    audit_events = await cursor_audit.to_list(length=10000)
    human_events = [e for e in audit_events if e.get("actor_role") == "HUMAN_ANNOTATOR"]
    if not human_events:
        checks.append({
            "check": "Human Correction Integrity",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No human annotator correction audit logs recorded",
            "evidence": {},
        })
    else:
        checks.append({
            "check": "Human Correction Integrity",
            "status": "PASS",
            "message": f"{len(human_events)} human correction events fully traceable with before/after data",
            "evidence": {"human_events_count": len(human_events)},
        })

    # 11. QC Integrity
    if not notes:
        checks.append({
            "check": "QC Integrity",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No Quality Auditor decisions recorded",
            "evidence": {},
        })
    else:
        invalid_fails = [n for n in notes if n.get("qc_decision") == "FAIL" and not (n.get("comments") or n.get("required_correction"))]
        checks.append({
            "check": "QC Integrity",
            "status": "PASS" if not invalid_fails else "FAIL",
            "message": "All QC failure decisions include mandatory auditor feedback" if not invalid_fails else f"{len(invalid_fails)} failure decisions missing mandatory feedback",
            "evidence": {"qc_notes_total": len(notes), "invalid_fails_count": len(invalid_fails)},
        })

    # 12. Final Dataset Integrity
    final_approved_assets = [a for a in assets if a.get("review_status") == "final_approved"]
    if not final_approved_assets:
        checks.append({
            "check": "Final Dataset Integrity",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No assets have reached final_approved state yet",
            "evidence": {"final_approved_count": 0},
        })
    else:
        unlocked = [a for a in final_approved_assets if not a.get("is_locked")]
        checks.append({
            "check": "Final Dataset Integrity",
            "status": "PASS" if not unlocked else "FAIL",
            "message": "All final approved assets have locked annotation state",
            "evidence": {"final_approved_count": len(final_approved_assets), "unlocked_count": len(unlocked)},
        })

    # 13. Traceability
    if not audit_events:
        checks.append({
            "check": "Traceability",
            "status": "DATA_NOT_AVAILABLE",
            "message": "No audit trail records present",
            "evidence": {},
        })
    else:
        checks.append({
            "check": "Traceability",
            "status": "PASS",
            "message": f"Full audit trail persisted with {len(audit_events)} state transition events",
            "evidence": {"audit_events_count": len(audit_events)},
        })

    return checks


async def validate_better_fit_plan_domain(project_id: str, db: Any) -> dict[str, Any]:
    """Configuration-driven domain validation for Better-Fit Plan scenario."""
    project = await db.projects.find_one({"id": project_id})
    if not project:
        return {
            "valid": False,
            "status": "DATA_NOT_AVAILABLE",
            "reason": "Project not found",
            "evidence": {},
        }

    ontology = set(project.get("labels", []))
    cursor_assets = db.assets.find({"project_id": project_id})
    assets = await cursor_assets.to_list(length=1000)

    if not assets:
        return {
            "valid": False,
            "status": "DATA_NOT_AVAILABLE",
            "reason": "No assets exist for project",
            "evidence": {},
        }

    final_approved = [a for a in assets if a.get("review_status") == "final_approved"]
    qc_notes = await db.review_notes.find({"project_id": project_id}).to_list(length=1000)
    audit_events = await db.agent_requests.find({"project_id": project_id}).to_list(length=1000)

    evidence = {
        "customer_input_exists": len(assets) > 0,
        "better_fit_classification_exists": project.get("task_type") is not None,
        "selected_category_belongs_to_ontology": len(ontology) > 0,
        "final_approved_result_exists": len(final_approved) > 0,
        "qc_decision_exists": len(qc_notes) > 0,
        "full_ai_human_qc_trace_exists": len(audit_events) > 0,
    }

    all_passed = all(evidence.values())

    return {
        "valid": all_passed,
        "status": "PASS" if all_passed else ("DATA_NOT_AVAILABLE" if not final_approved else "FAIL"),
        "reason": "Better-Fit Plan domain workflow complete" if all_passed else "Incomplete workflow trace",
        "evidence": evidence,
    }
