"""Technical detection quality: geometry, coverage, QA flags, honest confidence.

This module never invents or boosts model confidence. It only:
    - validates box geometry
    - flags suspicious spatial evidence
    - suppresses a parent box when it already contains multiple child boxes
    - builds an image-level coverage summary for the quality agent
    - records pipeline counts at stage boundaries
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from app.inference.contracts import NormalizedDetection
from app.logging import get_logger

logger = get_logger(__name__)

ALLOWED_QUALITY_ACTIONS = {
    "APPROVE",
    "RETRY",
    "ALTERNATE_MODEL",
    "ADDITIONAL_TOOL",
    "DIFFERENT_STRATEGY",
    "VERIFY",
    "SEGMENT",
    "HUMAN_REVIEW",
    "FAIL",
    "NO_DETECTIONS_EXPECTED",
}


def box_area_percent(det: NormalizedDetection) -> float:
    return max(0.0, det.bbox.w) * max(0.0, det.bbox.h)


def box_intersection_area(a: NormalizedDetection, b: NormalizedDetection) -> float:
    ax1, ay1 = a.bbox.x, a.bbox.y
    ax2, ay2 = a.bbox.x + a.bbox.w, a.bbox.y + a.bbox.h
    bx1, by1 = b.bbox.x, b.bbox.y
    bx2, by2 = b.bbox.x + b.bbox.w, b.bbox.y + b.bbox.h
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    return iw * ih


def containment_of_inner(inner: NormalizedDetection, outer: NormalizedDetection) -> float:
    """Fraction of inner box area that lies inside outer. Technical geometry only."""
    area = box_area_percent(inner)
    if area <= 0.0:
        return 0.0
    return box_intersection_area(inner, outer) / area


def validate_box_geometry(det: NormalizedDetection) -> dict[str, Any]:
    x1, y1 = det.bbox.x, det.bbox.y
    x2, y2 = det.bbox.x + det.bbox.w, det.bbox.y + det.bbox.h
    width = det.bbox.w
    height = det.bbox.h
    area = width * height
    area_ratio = area / 10000.0
    aspect = (width / height) if height > 0 else 0.0
    valid = (
        x1 < x2
        and y1 < y2
        and 0.0 <= x1 <= 100.0
        and 0.0 <= x2 <= 100.0
        and 0.0 <= y1 <= 100.0
        and 0.0 <= y2 <= 100.0
        and width > 0.0
        and height > 0.0
    )
    return {
        "valid": valid,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "width": width,
        "height": height,
        "area": area,
        "area_ratio": area_ratio,
        "aspect_ratio": aspect,
    }


def attach_honest_confidence(det: NormalizedDetection) -> NormalizedDetection:
    """Copy the model's own score into provenance. Never modify confidence."""
    provenance = dict(det.provenance or {})
    raw = provenance.get("raw_model_confidence")
    if raw is None:
        raw = provenance.get("raw_confidence")
    if raw is None:
        raw = det.confidence
    provenance["raw_confidence"] = float(raw)
    provenance["confidence_source"] = det.model_key
    provenance["model_key"] = det.model_key
    provenance.setdefault("confidence_semantics", "original_model_confidence_only")
    if "calibrated_confidence" not in provenance:
        provenance["calibrated_confidence"] = None
    return replace(det, provenance=provenance)


def attach_qa_flags(
    detections: list[NormalizedDetection],
    *,
    review_confidence_observation: float = 0.40,
    oversized_area_ratio: float = 0.35,
    near_duplicate_iou: float = 0.85,
) -> list[NormalizedDetection]:
    """Attach evidence-based QA flags. Flags never reject a detection by themselves."""
    from app.inference.merge import box_iou_percent

    flagged: list[NormalizedDetection] = []
    for det in detections:
        geometry = validate_box_geometry(det)
        flags: list[str] = []
        if not geometry["valid"]:
            flags.append("invalid_geometry")
        if geometry["area_ratio"] >= oversized_area_ratio:
            flags.append("suspicious_geometry")
        if det.confidence < review_confidence_observation:
            flags.append("low_confidence")
        children = [
            other
            for other in detections
            if other.id != det.id and containment_of_inner(other, det) >= 0.70
        ]
        if len(children) >= 2:
            flags.append("possible_overlap")
            flags.append("possible_missed_region")
        provenance = dict(det.provenance or {})
        for other in detections:
            if other.id == det.id or other.label != det.label:
                continue
            if box_iou_percent(det, other) >= near_duplicate_iou:
                flags.append("possible_duplicate")
                break
        if provenance.get("review_risk"):
            flags.append("uncertain_label")
        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique_flags = []
        for item in flags:
            if item not in seen:
                seen.add(item)
                unique_flags.append(item)
        provenance["qa_flags"] = unique_flags
        provenance["geometry_metrics"] = geometry
        provenance["hitl_status"] = provenance.get("hitl_status") or "ai_proposed"
        if unique_flags:
            provenance["needs_review"] = True
        flagged.append(replace(det, provenance=provenance))
    return flagged


def suppress_multi_object_parents(
    detections: list[NormalizedDetection],
    *,
    child_containment: float = 0.70,
    min_children: int = 2,
) -> tuple[list[NormalizedDetection], int]:
    """Drop a box that already contains multiple other detections.

    The children are kept. A lone large box is NOT dropped; it is only flagged.
    """
    drop_ids: set[str] = set()
    for parent in detections:
        children = [
            child
            for child in detections
            if child.id != parent.id
            and child.label == parent.label
            and containment_of_inner(child, parent) >= child_containment
        ]
        if len(children) >= min_children:
            parent_area = box_area_percent(parent)
            child_area = sum(box_area_percent(child) for child in children)
            if parent_area >= child_area * 0.8:
                drop_ids.add(parent.id)
                logger.info(
                    "multi_object_parent_suppressed",
                    parent_id=parent.id,
                    parent_label=parent.label,
                    parent_area=parent_area,
                    child_count=len(children),
                    child_ids=[child.id for child in children],
                    reason="box_contains_multiple_distinct_detections_of_same_class",
                )
    kept = [det for det in detections if det.id not in drop_ids]
    return kept, len(drop_ids)


def spatial_regions_with_detections(detections: list[NormalizedDetection]) -> list[int]:
    regions: set[int] = set()
    for det in detections:
        cx = det.bbox.x + det.bbox.w / 2.0
        cy = det.bbox.y + det.bbox.h / 2.0
        col = min(3, max(0, int(cx / 25.0)))
        row = min(3, max(0, int(cy / 25.0)))
        regions.add(row * 4 + col)
    return sorted(regions)


def build_image_coverage_summary(
    detections: list[NormalizedDetection],
    *,
    image_width: int | None = None,
    image_height: int | None = None,
) -> dict[str, Any]:
    classes = sorted({det.label for det in detections})
    small = [
        det.id
        for det in detections
        if box_area_percent(det) <= 100.0
    ]
    suspicious = [
        det.id
        for det in detections
        if (det.provenance or {}).get("qa_flags")
        and (
            "suspicious_geometry" in (det.provenance or {}).get("qa_flags", [])
            or "possible_overlap" in (det.provenance or {}).get("qa_flags", [])
        )
    ]
    duplicates = [
        det.id
        for det in detections
        if "possible_duplicate" in ((det.provenance or {}).get("qa_flags") or [])
    ]
    empty_regions = [idx for idx in range(16) if idx not in set(spatial_regions_with_detections(detections))]
    return {
        "image_width": image_width,
        "image_height": image_height,
        "detection_count": len(detections),
        "classes_detected": classes,
        "spatial_regions_with_detections": spatial_regions_with_detections(detections),
        "empty_spatial_regions": empty_regions,
        "small_object_candidates": len(small),
        "duplicate_candidates": len(duplicates),
        "suspicious_boxes": len(suspicious),
        "confidence_by_source": _confidence_by_source(detections),
    }


def _confidence_by_source(detections: list[NormalizedDetection]) -> dict[str, dict[str, float | int | None]]:
    grouped: dict[str, list[float]] = {}
    for det in detections:
        source = str((det.provenance or {}).get("confidence_source") or det.model_key)
        grouped.setdefault(source, []).append(float(det.confidence))
    summary: dict[str, dict[str, float | int | None]] = {}
    for source, scores in grouped.items():
        summary[source] = {
            "count": len(scores),
            "min": min(scores) if scores else None,
            "mean": (sum(scores) / len(scores)) if scores else None,
            "max": max(scores) if scores else None,
            "semantics": f"{source}_native_score",
        }
    return summary


@dataclass
class PipelineCounts:
    agent_requested_detections: int | None = None
    model_raw_detections: int = 0
    postprocess_detections: int = 0
    fusion_detections: int = 0
    persisted_detections: int = 0
    ui_detections: int | None = None
    extra: dict[str, int] = field(default_factory=dict)


def log_pipeline_event(
    event: str,
    *,
    project_id: str | None = None,
    asset_id: str | None = None,
    job_id: str | None = None,
    job_item_id: str | None = None,
    agent_run_id: str | None = None,
    execution_id: str | None = None,
    **fields: Any,
) -> None:
    data = dict(fields)
    if project_id is not None:
        data["project_id"] = project_id
    if asset_id is not None:
        data["asset_id"] = asset_id
    if job_id is not None:
        data["job_id"] = job_id
    if job_item_id is not None:
        data["job_item_id"] = job_item_id
    if agent_run_id is not None:
        data["agent_run_id"] = agent_run_id
    if execution_id is not None:
        data["execution_id"] = execution_id
    logger.info(event, **data)


def log_detection_score_trace(
    event: str,
    detections: list[NormalizedDetection],
    *,
    stage: str,
    asset_id: str | None = None,
    execution_id: str | None = None,
    **fields: Any,
) -> None:
    """Log image detector scores without conflating score semantics."""
    rows = []
    for det in detections:
        provenance = det.provenance or {}
        rows.append({
            "detection_id": det.id,
            "model_key": det.model_key,
            "label": det.label,
            "raw_model_score": float(det.confidence),
            "merged_score": float(det.confidence) if stage == "merged" else None,
            "evidence_score": provenance.get("evidence_confidence"),
            "verification_score": provenance.get("verification_score"),
            "verification_status": provenance.get("verification_status"),
        })
    scores_by_model: dict[str, list[float]] = {}
    for row in rows:
        scores_by_model.setdefault(row["model_key"], []).append(row["raw_model_score"])
    log_pipeline_event(
        event,
        asset_id=asset_id,
        execution_id=execution_id,
        score_stage=stage,
        score_count=len(rows),
        scores=rows,
        scores_by_model=scores_by_model,
        **fields,
    )


def finalize_detections(
    detections: list[NormalizedDetection],
    *,
    image_width: int | None = None,
    image_height: int | None = None,
) -> tuple[list[NormalizedDetection], dict[str, Any]]:
    """Post-fusion technical cleanup used by worker and agent graph."""
    honest = [attach_honest_confidence(det) for det in detections]
    without_parents, dropped = suppress_multi_object_parents(honest)
    flagged = attach_qa_flags(without_parents)
    coverage = build_image_coverage_summary(
        flagged,
        image_width=image_width,
        image_height=image_height,
    )
    coverage["multi_object_parents_removed"] = dropped
    log_pipeline_event(
        "postprocess_detection_result",
        count=len(flagged),
        multi_object_parents_removed=dropped,
        suspicious_boxes=coverage["suspicious_boxes"],
        duplicate_candidates=coverage["duplicate_candidates"],
    )
    return flagged, coverage
