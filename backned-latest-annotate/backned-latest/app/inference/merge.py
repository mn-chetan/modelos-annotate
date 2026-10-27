"""Cross-model detection merge.

Responsibilities:
    1. Normalize detections through the project ontology.
    2. Preserve original model confidence and provenance.
    3. Suppress invalid/unmapped detections deterministically.
    4. Merge duplicate detections from different models using IoU.
    5. Never invent a fine-grained label.
    6. Never convert model confidence into quality/confidence scores.
    7. Keep enough routing statistics to diagnose where detections disappear.

Important semantic separation:

    model confidence != IoU != verification confidence != quality

IoU in this module is used only for geometric duplicate merging.
Ground-truth IoU for TP/FP/FN evaluation belongs to the quality service.
"""

from __future__ import annotations

from typing import Any

from app.inference.contracts import NormalizedDetection
from app.inference.ontology_map import OntologyIndex, apply_mapping_to_detection
from app.inference.routing import (
    LabelSourcePlan,
    RoutingStats,
    build_capability_snapshot as build_label_source_plan,
)


# Percent boxes: full-image area is 100 * 100 = 10_000.
DEFAULT_MAX_BOX_AREA = 8500.0

# Preferred model is allowed to win a close tie.
PREFERRED_MODEL_MARGIN = 0.03
# A semantic class conflict is only auto-resolved when the model scores are
# meaningfully separated.  This is conflict policy, not an inference threshold.
CONFLICT_CONFIDENCE_MARGIN = 0.15

# Generic labels are NOT safe fine-grained ontology labels.
#
# IMPORTANT:
# We intentionally do NOT convert:
#
#     vehicle -> car
#     vehicle -> truck
#     vehicle -> bus
#
# because geometry overlap alone is not evidence for semantic identity.
GENERIC_LABELS = {
    "vehicle",
    "object",
    "item",
}


def box_iou_percent(
    a: NormalizedDetection,
    b: NormalizedDetection,
) -> float:
    """Calculate geometric IoU for percent-based bounding boxes.

    This IoU is ONLY used for detection deduplication/merging.

    It must NOT be interpreted as:
        - annotation quality
        - model confidence
        - TP/FP/FN
        - precision
        - recall
        - F1

    Ground-truth evaluation belongs to the quality evaluation service.
    """

    ax1 = a.bbox.x
    ay1 = a.bbox.y
    ax2 = a.bbox.x + a.bbox.w
    ay2 = a.bbox.y + a.bbox.h

    bx1 = b.bbox.x
    by1 = b.bbox.y
    bx2 = b.bbox.x + b.bbox.w
    by2 = b.bbox.y + b.bbox.h

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)

    intersection = iw * ih

    if intersection <= 0.0:
        return 0.0

    area_a = max(0.0, a.bbox.w) * max(0.0, a.bbox.h)
    area_b = max(0.0, b.bbox.w) * max(0.0, b.bbox.h)

    union = area_a + area_b - intersection

    if union <= 0.0:
        return 0.0

    return intersection / union


def _raw_model_label(det: NormalizedDetection) -> str:
    """Return the original model label without modifying it."""

    provenance = det.provenance or {}

    return (
        provenance.get("raw_model_label")
        or provenance.get("raw_label")
        or det.label
    )


def _preferred_model_for_label(
    label: str,
    source_plan: LabelSourcePlan | None,
) -> str | None:
    if source_plan is None:
        return None

    return source_plan.preferred_model_for(label)


def _model_preference_rank(
    det: NormalizedDetection,
    source_plan: LabelSourcePlan | None,
) -> int:
    preferred = _preferred_model_for_label(det.label, source_plan)

    if preferred is None:
        return 0

    return 0 if det.model_key == preferred else 1


def _classify_object_size(w: float, h: float) -> str:
    """Classify detection box size in percent area coordinates (0-100 x 0-100)."""
    area_percent = max(0.0, w) * max(0.0, h)
    if area_percent <= 100.0:  # <= 1% of total image area
        return "small"
    elif area_percent <= 1600.0:  # <= 16% of total image area
        return "medium"
    return "large"


def _preserve_provenance(
    winner: NormalizedDetection,
    loser: NormalizedDetection,
    *,
    merge_iou: float | None = None,
) -> dict[str, Any]:
    """Merge evidence without changing winner confidence.

    The winner's original model confidence remains untouched.

    Every contributing model keeps its own:
        model_key
        raw label
        raw confidence
        model id
    """

    winner_provenance = dict(winner.provenance or {})
    loser_provenance = dict(loser.provenance or {})

    contributing_models = list(
        winner_provenance.get("contributing_models") or []
    )

    def add_model_evidence(
        detection: NormalizedDetection,
    ) -> None:
        provenance = detection.provenance or {}

        entry = {
            "model_key": detection.model_key,
            "model_id": detection.model_id,
            "raw_model_label": _raw_model_label(detection),

            # CRITICAL:
            # This is the original model score.
            "raw_confidence": detection.confidence,
        }

        # Keep legacy "confidence" field only for compatibility.
        # It is explicitly the same original model confidence.
        entry["confidence"] = detection.confidence

        if entry not in contributing_models:
            contributing_models.append(entry)

    add_model_evidence(winner)
    add_model_evidence(loser)

    # Preserve any evidence already carried by either detection.
    for source in (winner_provenance, loser_provenance):
        for entry in source.get("contributing_models") or []:
            if entry not in contributing_models:
                contributing_models.append(entry)

    extra_confs = {}
    for entry in contributing_models:
        key = entry.get("model_key")
        if key:
            extra_confs[f"{key}_confidence"] = entry.get("raw_confidence") or entry.get("confidence") or 0.0

    model_keys = {m.get("model_key") for m in contributing_models if m.get("model_key")}
    # Any two independent detectors are agreement evidence, including the
    # previously omitted DINO + Faster R-CNN pair.
    model_agreement = len(model_keys) > 1

    # Preserve raw detector confidence for audit, and expose a separate
    # evidence score for UI ranking when independent models agree.
    raw_scores = []
    for entry in contributing_models:
        try:
            raw_scores.append(max(0.0, min(1.0, float(entry.get("raw_confidence") or entry.get("confidence") or 0.0))))
        except (TypeError, ValueError):
            continue
    evidence_confidence = max(raw_scores, default=0.0)
    if len(model_keys) > 1:
        independent_union = 1.0
        for score in raw_scores:
            independent_union *= 1.0 - score
        evidence_confidence = min(0.99, max(evidence_confidence, 1.0 - independent_union))

    w_size = _classify_object_size(winner.bbox.w, winner.bbox.h)

    return {
        **winner_provenance,
        **extra_confs,
        "contributing_models": contributing_models,

        # Explicit candidate normalization fields
        "source_model": winner.model_key,
        "source_detection_id": winner.id,
        "label": winner.label,
        "canonical_label": winner.label,
        "disposition": "merged",
        "size_category": w_size,

        # Explicit merge metadata.
        "merged_from_iou": True,

        # IMPORTANT:
        # Merge IoU is geometric deduplication evidence.
        # It is NOT ground-truth IoU.
        "merge_iou_only": True,

        # Preserve the original confidence of the selected winner.
        "selected_model_confidence": winner.confidence,
        # IoU is association evidence only; it never changes confidence.
        "merge_iou": merge_iou,
        "association_iou": merge_iou,
        "model_agreement": model_agreement,
        "matched_same_object": model_agreement,
        "evidence_confidence": round(evidence_confidence, 4),
        "confidence_semantics": "raw_model_confidence_preserved; evidence_confidence_is_fused_ui_signal",
        "candidate_state": "duplicate_suppressed",
    }


def _prefer(
    a: NormalizedDetection,
    b: NormalizedDetection,
    source_plan: LabelSourcePlan | None = None,
) -> NormalizedDetection:
    """Choose one duplicate detection without altering confidence.

    The selected detection keeps:
        - its own label
        - its own geometry
        - its own model
        - its own model confidence

    Evidence from the other model is preserved in provenance.

    When two boxes represent the same object (high containment of the smaller
    box inside the larger), the tighter box is kept. Confidence is never
    averaged or boosted.
    """
    from app.inference.detection_quality import box_area_percent, containment_of_inner

    area_a = box_area_percent(a)
    area_b = box_area_percent(b)
    smaller, larger = (a, b) if area_a <= area_b else (b, a)
    smaller_area = min(area_a, area_b)
    larger_area = max(area_a, area_b)
    if smaller_area > 0.0 and larger_area >= smaller_area * 1.35:
        if containment_of_inner(smaller, larger) >= 0.85:
            winner, loser = smaller, larger
            association_iou = box_iou_percent(winner, loser)
            provenance = _preserve_provenance(
                winner,
                loser,
                merge_iou=association_iou,
            )
            provenance["winner_reason"] = "tighter_contained_box"
            return NormalizedDetection(
                id=winner.id,
                asset_id=winner.asset_id,
                label=winner.label,
                class_id=winner.class_id,
                bbox=winner.bbox,
                confidence=winner.confidence,
                model_id=winner.model_id,
                model_key=winner.model_key,
                inferred_at=winner.inferred_at,
                provenance=provenance,
            )

    loc_a = (a.provenance or {}).get("localization_score") or (a.provenance or {}).get("localization_confidence")
    loc_b = (b.provenance or {}).get("localization_score") or (b.provenance or {}).get("localization_confidence")

    if loc_a is not None or loc_b is not None:
        val_a = float(loc_a) if loc_a is not None else -1.0
        val_b = float(loc_b) if loc_b is not None else -1.0
        if val_a != val_b:
            winner, loser = (a, b) if val_a > val_b else (b, a)
        else:
            winner, loser = (
                (a, b)
                if a.confidence >= b.confidence
                else (b, a)
            )
    else:
        preferred = _preferred_model_for_label(a.label, source_plan)

        if preferred is not None:
            if a.model_key == preferred and b.model_key != preferred:
                if a.confidence + PREFERRED_MODEL_MARGIN >= b.confidence:
                    winner, loser = a, b
                else:
                    winner, loser = b, a

            elif b.model_key == preferred and a.model_key != preferred:
                if b.confidence + PREFERRED_MODEL_MARGIN >= a.confidence:
                    winner, loser = b, a
                else:
                    winner, loser = a, b

            else:
                winner, loser = (
                    (a, b)
                    if a.confidence >= b.confidence
                    else (b, a)
                )
        else:
            winner, loser = (
                (a, b)
                if a.confidence >= b.confidence
                else (b, a)
            )

    association_iou = box_iou_percent(winner, loser)
    provenance = _preserve_provenance(
        winner,
        loser,
        merge_iou=association_iou,
    )

    # DO NOT calculate:
    #
    # confidence = average(...)
    # confidence = max(...) + agreement_bonus
    # confidence = WBF_score
    #
    # The confidence must remain the original winner's model confidence.
    return NormalizedDetection(
        id=winner.id,
        asset_id=winner.asset_id,
        label=winner.label,
        class_id=winner.class_id,
        bbox=winner.bbox,
        confidence=winner.confidence,
        model_id=winner.model_id,
        model_key=winner.model_key,
        inferred_at=winner.inferred_at,
        provenance=provenance,
    )


def _adaptive_iou_threshold(
    group: list[NormalizedDetection],
    base_threshold: float,
) -> float:
    """Adapt duplicate-merging IoU by object size.

    This affects ONLY duplicate suppression.

    It does not modify:
        - model confidence
        - quality
        - TP/FP/FN
        - precision
        - recall
        - F1
    """
    if len(group) < 2:
        return base_threshold

    average_area = sum(
        det.bbox.w * det.bbox.h
        for det in group
    ) / len(group)

    # Large objects:
    # require slightly stronger overlap before merging.
    if average_area >= 2500:
        return min(0.9, base_threshold + 0.05)

    # Small objects (area <= 100):
    # require higher IoU overlap to suppress to protect legitimate nearby small objects
    if average_area <= 100:
        return min(0.85, max(0.70, base_threshold + 0.20))

    if average_area <= 400:
        return min(0.80, max(0.60, base_threshold + 0.10))

    if average_area <= 1200:
        return min(0.75, max(0.55, base_threshold + 0.05))

    return base_threshold


def _mark_review_risk(
    det: NormalizedDetection,
    review_risk_threshold: float,
) -> NormalizedDetection:
    """Mark a weak prediction for later agent/human review.

    IMPORTANT:
    The detection is NOT removed and confidence is NOT changed.
    """

    provenance = {
        **(det.provenance or {}),
        "review_risk": True,
        "review_risk_threshold": review_risk_threshold,
        "review_risk_reason": "model_confidence_below_review_threshold",
    }

    return NormalizedDetection(
        id=det.id,
        asset_id=det.asset_id,
        label=det.label,
        class_id=det.class_id,
        bbox=det.bbox,

        # Original model confidence is preserved exactly.
        confidence=det.confidence,

        model_id=det.model_id,
        model_key=det.model_key,
        inferred_at=det.inferred_at,
        provenance=provenance,
    )


def _is_generic_label(label: str | None) -> bool:
    if not label:
        return False

    return label.strip().lower() in GENERIC_LABELS


def verify_merged_detections(
    detections: list[NormalizedDetection],
    index: OntologyIndex,
    *,
    expected_labels: list[str] | tuple[str, ...] = (),
    duplicate_iou: float = 0.85,
    oversized_area: float = 6500.0,
) -> dict[str, Any]:
    """Produce deterministic post-merge quality evidence without changing boxes.

    This is a verification report, not a second confidence score. It detects
    actionable gaps for the agent/review policy while preserving valid nearby
    same-class instances unless they are near-identical geometrically.
    """
    invalid_labels: list[str] = []
    out_of_bounds: list[str] = []
    oversized: list[str] = []
    low_confidence: list[str] = []
    duplicate_pairs: list[dict[str, Any]] = []
    detected_labels = {det.label for det in detections}
    small_objects = [
        detection.id
        for detection in detections
        if detection.bbox.w * detection.bbox.h <= 100.0
    ]
    spatial_regions = {
        min(3, int((detection.bbox.x + detection.bbox.w / 2.0) / 25.0))
        + min(3, int((detection.bbox.y + detection.bbox.h / 2.0) / 25.0)) * 4
        for detection in detections
    }

    for detection in detections:
        if index.resolve_canonical_name(detection.label) is None:
            invalid_labels.append(detection.label)
        box = detection.bbox
        if box.x < 0 or box.y < 0 or box.x + box.w > 100 or box.y + box.h > 100:
            out_of_bounds.append(detection.id)
        if box.w * box.h >= oversized_area:
            oversized.append(detection.id)
        if detection.confidence < 0.40:
            low_confidence.append(detection.id)

    for position, left in enumerate(detections):
        for right in detections[position + 1 :]:
            if left.label != right.label:
                continue
            iou = box_iou_percent(left, right)
            if iou < duplicate_iou:
                continue
            width_ratio = min(left.bbox.w, right.bbox.w) / max(left.bbox.w, right.bbox.w)
            height_ratio = min(left.bbox.h, right.bbox.h) / max(left.bbox.h, right.bbox.h)
            if width_ratio >= 0.70 and height_ratio >= 0.70:
                duplicate_pairs.append({"left": left.id, "right": right.id, "label": left.label, "iou": iou})

    expected = list(expected_labels)
    missing_labels = [label for label in expected if label not in detected_labels]
    report = {
        "invalid_labels": invalid_labels,
        "out_of_bounds": out_of_bounds,
        "oversized_boxes": oversized,
        "low_confidence": low_confidence,
        "small_object_ids": small_objects,
        "spatial_region_count": len(spatial_regions),
        "duplicate_pairs": duplicate_pairs,
        "missing_expected_labels": missing_labels,
        "detected_labels": sorted(detected_labels),
        "object_count": len(detections),
    }
    report["class_coverage"] = (
        len(expected_labels) - len(missing_labels)
    ) / len(expected_labels) if expected_labels else 1.0
    report["class_coverage"] = max(0.0, min(1.0, report["class_coverage"]))
    report["needs_review"] = bool(
        invalid_labels or out_of_bounds or oversized or duplicate_pairs or missing_labels
    )
    return report


def run_iou_threshold_diagnostic(
    detections: list[NormalizedDetection],
    index: OntologyIndex,
    *,
    source_plan: LabelSourcePlan | None = None,
    thresholds: tuple[float, ...] = (0.30, 0.40, 0.50, 0.60, 0.70, 0.80),
) -> dict[float, dict[str, int]]:
    """Run duplicate matching diagnostics across multiple IoU thresholds.

    Returns diagnostic metrics for each threshold:
        - fusion_input
        - duplicates_removed
        - conflicts
        - final_count
    """
    results = {}
    for th in thresholds:
        kept, stats = merge_detections(
            detections,
            index,
            iou_threshold=th,
            source_plan=source_plan,
        )
        results[th] = {
            "fusion_input": stats.fusion_input,
            "duplicates_removed": stats.duplicates_suppressed,
            "conflicts": stats.conflicts_detected,
            "final_count": len(kept),
        }
    return results


def _same_model_class_aware_nms(
    detections: list[NormalizedDetection],
    iou_threshold: float,
) -> tuple[list[NormalizedDetection], int]:
    """Perform class-aware NMS on same-model detections.

    Detections are grouped by label. Within each label group, candidates are
    sorted by confidence descending. Overlapping boxes above IoU threshold are
    suppressed unless their spatial centroids indicate distinct physical objects
    in a dense scene.
    """
    kept: list[NormalizedDetection] = []
    suppressed_count = 0
    by_label: dict[str, list[NormalizedDetection]] = {}

    for det in detections:
        by_label.setdefault(det.label, []).append(det)

    for label, group in by_label.items():
        sorted_group = sorted(group, key=lambda d: float(d.confidence), reverse=True)
        while sorted_group:
            best = sorted_group.pop(0)
            kept.append(best)
            remaining = []
            for candidate in sorted_group:
                iou = box_iou_percent(best, candidate)
                adaptive_th = _adaptive_iou_threshold([best, candidate], iou_threshold)

                # Check containment (Intersection over Smaller / IOS)
                inter_w = max(0.0, min(best.bbox.x + best.bbox.w, candidate.bbox.x + candidate.bbox.w) - max(best.bbox.x, candidate.bbox.x))
                inter_h = max(0.0, min(best.bbox.y + best.bbox.h, candidate.bbox.y + candidate.bbox.h) - max(best.bbox.y, candidate.bbox.y))
                inter_area = inter_w * inter_h
                min_area = min(best.bbox.w * best.bbox.h, candidate.bbox.w * candidate.bbox.h)
                containment = (inter_area / min_area) if min_area > 0 else 0.0

                is_duplicate = False
                if iou >= adaptive_th:
                    # Centroid offset check: distinguish true duplicate vs adjacent dense objects
                    cx_diff = abs((best.bbox.x + best.bbox.w / 2.0) - (candidate.bbox.x + candidate.bbox.w / 2.0))
                    cy_diff = abs((best.bbox.y + best.bbox.h / 2.0) - (candidate.bbox.y + candidate.bbox.h / 2.0))
                    min_w = min(best.bbox.w, candidate.bbox.w)
                    min_h = min(best.bbox.h, candidate.bbox.h)
                    # If centroids are offset by >= 35% of box dimensions, preserve as distinct nearby object
                    if not (min_w > 0 and min_h > 0 and (cx_diff / min_w >= 0.35 or cy_diff / min_h >= 0.35)):
                        is_duplicate = True
                elif containment >= 0.85 and iou >= 0.30:
                    # One candidate is heavily nested inside another for the same class (e.g. sign face vs sign face + post)
                    is_duplicate = True

                if is_duplicate:
                    suppressed_count += 1
                else:
                    remaining.append(candidate)
            sorted_group = remaining

    return kept, suppressed_count


def merge_detections(
    detections: list[NormalizedDetection],
    index: OntologyIndex,
    *,
    iou_threshold: float = 0.5,
    max_box_area: float = DEFAULT_MAX_BOX_AREA,
    giant_min_confidence: float = 0.85,
    review_risk_threshold: float = 0.8,
    source_plan: LabelSourcePlan | None = None,
) -> tuple[list[NormalizedDetection], RoutingStats]:
    """Normalize and deterministically merge model detections.

    Pipeline:

        raw detections
            ↓
        coordinate verification & ontology normalization
            ↓
        invalid/generic suppression
            ↓
        giant-box validation & review-risk marking
            ↓
        same-model class-aware NMS
            ↓
        cross-model matching & class conflict resolution
            ↓
        final canonical candidates
    """
    from app.logging import get_logger as _get_logger
    _logger_merge = _get_logger(__name__)

    stats = RoutingStats()
    mapped: list[NormalizedDetection] = []
    source_plan = source_plan or build_label_source_plan(index)

    # ---------------------------------------------------------------
    # Stage 1: Raw detector accounting & Ontology Normalization
    # ---------------------------------------------------------------
    for det in detections:
        model_key = getattr(det, "model_key", "") or ""

        if model_key == "yolo26":
            stats.yolo_raw += 1
        elif model_key == "faster_rcnn":
            stats.faster_rcnn_raw += 1
        elif model_key == "dino":
            stats.dino_raw += 1

        # Coordinate Verification Log
        bbox = getattr(det, "bbox", None)
        if bbox is not None:
            _logger_merge.debug(
                "coordinate_verification",
                coordinate_space="full_image_percent",
                model_key=model_key,
                box_x1=bbox.x,
                box_y1=bbox.y,
                box_x2=bbox.x + bbox.w,
                box_y2=bbox.y + bbox.h,
            )

        # Ontology normalization
        remapped, mapping_result = apply_mapping_to_detection(det, index)

        if remapped is None:
            stats.unmapped_suppressed += 1
            raw_label = (
                getattr(mapping_result, "raw_model_label", None)
                or _raw_model_label(det)
                or "?"
            )
            stats.by_raw_suppressed[raw_label] = (
                stats.by_raw_suppressed.get(raw_label, 0) + 1
            )
            _logger_merge.info(
                "candidate_unmapped_suppressed",
                candidate_id=det.id,
                raw_label=raw_label,
                normalized_raw_label=(getattr(mapping_result, "provenance", lambda: {})() or {}).get("normalized_raw_label"),
                requested_label=(det.provenance or {}).get("requested_label"),
                canonical_label=None,
                mapping_status="UNMAPPED_DETECTION",
                mapping_reason=getattr(mapping_result, "suppression_reason", None) or "label_not_in_project_ontology",
                model=model_key,
                confidence=det.confidence,
                bbox={"x": bbox.x, "y": bbox.y, "w": bbox.w, "h": bbox.h} if bbox else None,
                mapping_result="unmapped",
                suppression_reason=getattr(mapping_result, "suppression_reason", None) or "label_not_in_project_ontology",
            )
            continue

        # Bounding box geometry validation & clamping to image boundaries
        bbox = getattr(remapped, "bbox", None)
        if bbox is not None:
            import dataclasses
            x1 = max(0.0, min(100.0, bbox.x))
            y1 = max(0.0, min(100.0, bbox.y))
            x2 = max(0.0, min(100.0, bbox.x + bbox.w))
            y2 = max(0.0, min(100.0, bbox.y + bbox.h))
            
            new_bbox = dataclasses.replace(
                bbox,
                x=x1,
                y=y1,
                w=round(max(0.0, x2 - x1), 10),
                h=round(max(0.0, y2 - y1), 10),
            )
            remapped = dataclasses.replace(remapped, bbox=new_bbox)
            bbox = new_bbox

        if bbox is None or bbox.w <= 0.0 or bbox.h <= 0.0:
            stats.invalid_boxes_removed += 1
            continue

        # Reject generic labels
        if _is_generic_label(remapped.label):
            stats.unmapped_suppressed += 1
            raw_label = _raw_model_label(remapped)
            stats.by_raw_suppressed[raw_label] = (
                stats.by_raw_suppressed.get(raw_label, 0) + 1
            )
            _logger_merge.info(
                "candidate_generic_suppressed",
                candidate_id=remapped.id,
                raw_label=raw_label,
                model=remapped.model_key,
                confidence=remapped.confidence,
                bbox={"x": bbox.x, "y": bbox.y, "w": bbox.w, "h": bbox.h},
                suppression_reason="generic_ambiguous_label",
            )
            continue

        # A large box is evidence for QA, not a reason to discard a real
        # model candidate. The quality stage can route it to verification.
        area = remapped.bbox.w * remapped.bbox.h
        if area >= max_box_area:
            remapped = _mark_review_risk(remapped, review_risk_threshold)
            remapped = dataclasses.replace(
                remapped,
                provenance={
                    **(remapped.provenance or {}),
                    "suspicious_geometry": True,
                    "suspicious_geometry_reason": "large_image_area",
                },
            )

        # Review risk marking
        if remapped.confidence < review_risk_threshold:
            remapped = _mark_review_risk(remapped, review_risk_threshold)

        mapped.append(remapped)
        stats.mapped_accepted += 1
        stats.by_canonical[remapped.label] = (
            stats.by_canonical.get(remapped.label, 0) + 1
        )

    # ---------------------------------------------------------------
    # Stage 2: Same-Model Class-Aware NMS
    # ---------------------------------------------------------------
    yolo_mapped = [d for d in mapped if d.model_key == "yolo26"]
    dino_mapped = [d for d in mapped if d.model_key == "dino"]
    other_mapped = [d for d in mapped if d.model_key not in ("yolo26", "dino")]

    yolo_nms_list, yolo_suppressed = _same_model_class_aware_nms(yolo_mapped, iou_threshold)
    dino_nms_list, dino_suppressed = _same_model_class_aware_nms(dino_mapped, iou_threshold)
    other_nms_list, other_suppressed = _same_model_class_aware_nms(other_mapped, iou_threshold)

    stats.yolo_nms = len(yolo_nms_list)
    stats.dino_nms = len(dino_nms_list)
    stats.duplicates_suppressed += (yolo_suppressed + dino_suppressed + other_suppressed)

    fusion_input = yolo_nms_list + dino_nms_list + other_nms_list
    stats.fusion_input = len(fusion_input)

    # ---------------------------------------------------------------
    # Stage 3: Cross-Model Matching & Conflict Resolution
    # ---------------------------------------------------------------
    kept: list[NormalizedDetection] = []

    ordered = sorted(
        fusion_input,
        key=lambda d: (
            _model_preference_rank(d, source_plan),
            -float(d.confidence),
            d.model_key,
            d.id,
        ),
    )

    # Vehicle / confusable class pairs for same-object conflict checking
    confusable_vehicle_pairs = {
        ("car", "truck"), ("truck", "car"),
        ("cars", "trucks"), ("trucks", "cars"),
        ("car", "bus"), ("bus", "car"),
        ("cars", "buses"), ("buses", "cars"),
        ("car", "auto"), ("auto", "car"),
        ("cars", "autos"), ("autos", "cars"),
        ("truck", "bus"), ("bus", "truck"),
        ("trucks", "buses"), ("buses", "trucks"),
        ("auto", "motorcycle"), ("motorcycle", "auto"),
        ("autos", "motorcycles"), ("motorcycles", "autos"),
        ("auto", "truck"), ("truck", "auto"),
        ("autos", "trucks"), ("trucks", "autos"),
        ("auto", "bus"), ("bus", "auto"),
        ("autos", "buses"), ("buses", "autos"),
    }

    for candidate in ordered:
        matched_index: int | None = None
        matched_is_same_class = False
        matched_is_same_object_conflict = False
        best_iou = 0.0

        for i, existing in enumerate(kept):
            iou = box_iou_percent(candidate, existing)
            adaptive_threshold = _adaptive_iou_threshold([candidate, existing], iou_threshold)

            # Same-model NMS uses the size-aware threshold above to protect
            # nearby small objects.  Cross-model evidence has a different
            # failure mode: the same small object is often emitted with
            # slightly different boxes by each detector.  Use the configured
            # production IoU threshold for same-class cross-model matching so
            # those duplicates can be fused, while keeping the stricter
            # same-model policy unchanged.
            matching_threshold = (
                iou_threshold
                if candidate.model_key != existing.model_key
                else adaptive_threshold
            )

            if iou < matching_threshold:
                continue

            stats.fusion_matches += 1

            label_pair = (existing.label.lower(), candidate.label.lower())

            # Case A: Same Class -> Cross-Model Duplicate
            if existing.label == candidate.label:
                if iou > best_iou:
                    best_iou = iou
                    matched_index = i
                    matched_is_same_class = True
                    matched_is_same_object_conflict = False

            # Case B: Different Classes -> Evaluate physical object identity
            elif label_pair in confusable_vehicle_pairs:
                w_ratio = min(candidate.bbox.w, existing.bbox.w) / max(candidate.bbox.w, existing.bbox.w)
                h_ratio = min(candidate.bbox.h, existing.bbox.h) / max(candidate.bbox.h, existing.bbox.h)

                if iou >= max(0.65, adaptive_threshold) and w_ratio >= 0.50 and h_ratio >= 0.50:
                    # Same physical object with conflicting class labels!
                    if iou > best_iou:
                        best_iou = iou
                        matched_index = i
                        matched_is_same_class = False
                        matched_is_same_object_conflict = True
                else:
                    # Distinct physical objects (e.g. car behind truck or adjacent vehicle)
                    _logger_merge.info(
                        "cross_model_class_overlap_kept",
                        conflict_id=f"conflict_{existing.id}_{candidate.id}",
                        class_a=existing.label,
                        class_b=candidate.label,
                        confidence_a=existing.confidence,
                        confidence_b=candidate.confidence,
                        iou=iou,
                        same_object_decision=False,
                        winner="both",
                        reason="distinct_physical_objects_kept",
                    )

        if matched_index is not None:
            existing = kept[matched_index]

            if matched_is_same_class:
                # Deduplicate same class across models
                kept[matched_index] = _prefer(existing, candidate, source_plan)
                stats.duplicates_suppressed += 1
                continue

            elif matched_is_same_object_conflict:
                # Class conflict on same physical object
                stats.conflicts_detected += 1
                winner = _prefer(existing, candidate, source_plan)
                loser = candidate if winner.id == existing.id else existing
                conflict_id = f"conflict_{existing.id}_{candidate.id}"
                confidence_delta = abs(float(existing.confidence) - float(candidate.confidence))
                resolved = confidence_delta >= CONFLICT_CONFIDENCE_MARGIN
                resolution_status = "resolved" if resolved else "unresolved"
                resolution_reason = (
                    "meaningful_confidence_difference"
                    if resolved
                    else "ambiguous_semantic_class_conflict"
                )
                conflict_record = {
                    "conflict_id": conflict_id,
                    "asset_id": existing.asset_id,
                    "execution_ids": list(dict.fromkeys([
                        (existing.provenance or {}).get("execution_id"),
                        (candidate.provenance or {}).get("execution_id"),
                    ])) if (
                        (existing.provenance or {}).get("execution_id")
                        or (candidate.provenance or {}).get("execution_id")
                    ) else [],
                    "candidate_a": {"label": existing.label, "model": existing.model_key, "detection_id": existing.id},
                    "candidate_b": {"label": candidate.label, "model": candidate.model_key, "detection_id": candidate.id},
                    "confidence_a": existing.confidence,
                    "confidence_b": candidate.confidence,
                    "iou": best_iou,
                    "winner": winner.label,
                    "loser": loser.label,
                    "resolution_status": resolution_status,
                    "resolution_reason": resolution_reason,
                }
                stats.conflict_records.append(conflict_record)

                _logger_merge.info(
                    "cross_model_class_conflict",
                    conflict_id=conflict_id,
                    class_a=existing.label,
                    class_b=candidate.label,
                    confidence_a=existing.confidence,
                    confidence_b=candidate.confidence,
                    iou=best_iou,
                    same_object_decision=True,
                    winner=winner.model_key,
                    winner_label=winner.label,
                    resolution_status=resolution_status,
                    resolution_reason=resolution_reason,
                    reason=resolution_reason,
                )

                # Attach conflict resolution evidence to winner provenance
                updated_prov = {
                    **(winner.provenance or {}),
                    "cross_model_conflict": True,
                    "conflict_id": conflict_id,
                    "conflict_class_a": existing.label,
                    "conflict_class_b": candidate.label,
                    "conflict_confidence_a": existing.confidence,
                    "conflict_confidence_b": candidate.confidence,
                    "conflict_iou": best_iou,
                    "conflict_same_object_decision": True,
                    "conflict_winner": winner.model_key,
                    "conflict_reason": resolution_reason,
                    "resolution_status": resolution_status,
                    "resolution_reason": resolution_reason,
                    "semantic_conflict": not resolved,
                }

                winner_det = NormalizedDetection(
                    id=winner.id,
                    asset_id=winner.asset_id,
                    label=winner.label,
                    class_id=winner.class_id,
                    bbox=winner.bbox,
                    confidence=winner.confidence,
                    model_id=winner.model_id,
                    model_key=winner.model_key,
                    inferred_at=winner.inferred_at,
                    provenance=updated_prov,
                )

                kept[matched_index] = winner_det
                stats.duplicates_suppressed += 1
                continue

        # Unmatched candidate
        if candidate.model_key == "faster_rcnn":
            candidate = NormalizedDetection(
                id=candidate.id,
                asset_id=candidate.asset_id,
                label=candidate.label,
                class_id=candidate.class_id,
                bbox=candidate.bbox,
                confidence=candidate.confidence,
                model_id=candidate.model_id,
                model_key=candidate.model_key,
                inferred_at=candidate.inferred_at,
                provenance={
                    **(candidate.provenance or {}),
                    "new_object_candidate": True,
                    "verification_required": True,
                    "candidate_reason": "no_same_label_cross_model_association",
                },
            )

        kept.append(candidate)

    # ---------------------------------------------------------------
    # Stage 4: Candidate Normalization & Final Accounting
    # ---------------------------------------------------------------
    final_kept: list[NormalizedDetection] = []
    stats.by_canonical = {}
    for det in kept:
        prov = dict(det.provenance or {})
        size_cat = _classify_object_size(det.bbox.w, det.bbox.h)
        prov["source_model"] = prov.get("source_model", det.model_key)
        prov["source_detection_id"] = prov.get("source_detection_id", det.id)
        prov["label"] = det.label
        prov["canonical_label"] = det.label
        prov["disposition"] = prov.get("disposition", "accepted")
        prov["size_category"] = size_cat
        if "evidence_confidence" not in prov:
            try:
                prov["evidence_confidence"] = round(max(0.0, min(1.0, float(det.confidence))), 4)
            except (TypeError, ValueError):
                prov["evidence_confidence"] = None

        final_det = NormalizedDetection(
            id=det.id,
            asset_id=det.asset_id,
            label=det.label,
            class_id=det.class_id,
            bbox=det.bbox,
            confidence=det.confidence,
            model_id=det.model_id,
            model_key=det.model_key,
            inferred_at=det.inferred_at,
            provenance=prov,
        )
        final_kept.append(final_det)
        stats.by_canonical[det.label] = stats.by_canonical.get(det.label, 0) + 1

    from app.inference.detection_quality import finalize_detections

    kept, coverage = finalize_detections(final_kept)
    stats.mapped_accepted = len(kept)
    stats.final_candidates = len(kept)
    stats.record_stage("fusion_detections", len(kept))
    stats.record_stage("multi_object_parents_removed", int(coverage.get("multi_object_parents_removed") or 0))

    from app.inference.detection_quality import log_detection_score_trace
    log_detection_score_trace(
        "image_detection_score_trace",
        kept,
        stage="merged",
        asset_id=kept[0].asset_id if kept else (detections[0].asset_id if detections else None),
        raw_candidate_count=len(detections),
        fusion_input=stats.fusion_input,
        duplicates_removed=stats.duplicates_suppressed,
        conflicts_detected=stats.conflicts_detected,
        verification_score_semantics="not_generated_by_merge; verification is evidence/status only",
    )

    _logger_merge.info(
        "fusion_detection_result",
        count=len(kept),
        fusion_input=stats.fusion_input,
        duplicates_removed=stats.duplicates_suppressed,
        multi_object_parents_removed=coverage.get("multi_object_parents_removed"),
    )
    _logger_merge.info(
        "merge_detections_pipeline_complete",
        yolo_raw=stats.yolo_raw,
        yolo_nms=stats.yolo_nms,
        dino_raw=stats.dino_raw,
        dino_nms=stats.dino_nms,
        fusion_input=stats.fusion_input,
        fusion_matches=stats.fusion_matches,
        duplicates_removed=stats.duplicates_suppressed,
        conflicts_detected=stats.conflicts_detected,
        unmapped_removed=stats.unmapped_suppressed,
        final_candidates=stats.final_candidates,
    )

    return kept, stats


def stats_to_dict(stats: RoutingStats) -> dict[str, Any]:
    """Serialize merge/routing diagnostics.

    These are pipeline counts, NOT quality metrics.
    """

    return {
        "yolo_raw": stats.yolo_raw,
        "yolo_nms": stats.yolo_nms,
        "dino_raw": stats.dino_raw,
        "dino_nms": stats.dino_nms,
        "fusion_input": stats.fusion_input,
        "fusion_matches": stats.fusion_matches,
        "duplicates_removed": stats.duplicates_suppressed,
        "conflicts_detected": stats.conflicts_detected,
        "conflict_records": list(stats.conflict_records),
        "unmapped_removed": stats.unmapped_suppressed,
        "final_candidates": stats.final_candidates,

        "mapped_accepted": stats.mapped_accepted,
        "unmapped_suppressed": stats.unmapped_suppressed,
        "duplicates_suppressed": stats.duplicates_suppressed,
        "giant_suppressed": stats.giant_suppressed,
        "invalid_boxes_removed": stats.invalid_boxes_removed,

        "by_canonical": dict(stats.by_canonical),
        "by_raw_suppressed": dict(stats.by_raw_suppressed),

        "confidence_semantics": "original_model_confidence_only",
        "iou_semantics": "geometric_duplicate_merge_only",
        "quality_metrics_source": "ground_truth_quality_service",
    }
