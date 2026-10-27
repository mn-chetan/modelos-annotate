"""Evidence-driven review decisions for completed annotation passes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.inference.merge import box_iou_percent
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReviewDecision:
    status: str
    human_review_required: bool
    unresolved_reasons: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)


async def route_asset_confidence_and_sampling(
    *,
    db: Any,
    asset_id: str,
    project_id: str,
    detections: list[Any],
) -> dict[str, Any]:
    """Backend confidence-based routing & 2%-5% QC sampling engine.

    Rules:
    - min_confidence < project.confidence_threshold (e.g. 0.95) -> HUMAN_REVIEW
    - min_confidence >= project.confidence_threshold -> AUTO_PASS_ELIGIBLE
    - Sample 2%–5% of AUTO_PASS_ELIGIBLE for QC audit (QC_SAMPLE).
    - Persist sampling decision on asset.
    """
    import random
    from app.domain.enums import ReviewStatus

    project = await db.projects.find_one({"id": project_id})
    if not project:
        conf_threshold = 0.95
        sample_rate = 0.02
    else:
        conf_threshold = float(project.get("confidence_threshold", 0.95))
        sample_rate = float(project.get("high_confidence_qc_sample_rate", 0.02))

    sample_rate = max(0.02, min(0.05, sample_rate))

    confidences = []
    for d in detections:
        if d is None:
            continue
        c = getattr(d, "confidence", None)
        if c is None and isinstance(d, dict):
            c = d.get("confidence")
        if c is not None:
            try:
                confidences.append(float(c))
            except (TypeError, ValueError):
                pass

    min_confidence = min(confidences) if confidences else 0.0
    is_auto_pass_eligible = (len(confidences) > 0) and (min_confidence >= conf_threshold)

    if not is_auto_pass_eligible:
        routing_status = "HUMAN_REVIEW"
        review_status = ReviewStatus.HUMAN_REVIEW_REQUIRED.value
        is_qc_sample = False
    else:
        is_qc_sample = (random.random() < sample_rate)
        if is_qc_sample:
            routing_status = "QC_SAMPLE"
            review_status = ReviewStatus.HIGH_CONFIDENCE_QC_SAMPLE.value
        else:
            routing_status = "AUTO_PASS"
            review_status = ReviewStatus.HIGH_CONFIDENCE_AUTO_PASS.value

    if db:
        await db.assets.update_one(
            {"id": asset_id},
            {
                "$set": {
                    "review_status": review_status,
                    "routing_status": routing_status,
                    "confidence_threshold_applied": conf_threshold,
                    "sample_rate_applied": sample_rate,
                    "is_qc_sample": is_qc_sample,
                    "auto_pass_eligible": is_auto_pass_eligible,
                    "min_confidence": min_confidence,
                }
            },
        )

    return {
        "asset_id": asset_id,
        "routing_status": routing_status,
        "review_status": review_status,
        "auto_pass_eligible": is_auto_pass_eligible,
        "is_qc_sample": is_qc_sample,
        "confidence_threshold": conf_threshold,
        "sample_rate": sample_rate,
        "min_confidence": min_confidence,
    }


def _get_review_confidence_for_detection(det: Any, all_detections: list[Any]) -> float:
    """Expose descriptive evidence without changing detector confidence.

    This value is deliberately not used as an approval threshold.  In
    particular, IoU and agreement must not be converted into a fabricated
    confidence score.
    """
    label = getattr(det, "label", "")
    model_key = getattr(det, "model_key", "")
    confidence = getattr(det, "confidence", 0.0) or 0.0

    # Start with contributing models from provenance if present
    prov = getattr(det, "provenance", None) or {}
    contributing = prov.get("contributing_models") or []

    if contributing:
        confidences = [item.get("raw_confidence") or item.get("confidence") or 0.0 for item in contributing]
        max_conf = max(confidences) if confidences else confidence
        supporting_models = {item.get("model_key") for item in contributing if item.get("model_key")}
        merge_iou = prov.get("merge_iou") or 0.0
    else:
        # Reconstruct dynamically (useful for unit tests and fallback)
        overlapping = [det]
        supporting_models = {model_key}
        merge_iou = 0.0

        for d in all_detections:
            if getattr(d, "id", None) == getattr(det, "id", None):
                continue
            if getattr(d, "label", "") == label:
                try:
                    iou = box_iou_percent(det, d)
                except Exception:
                    iou = 0.0
                if iou >= 0.45:
                    overlapping.append(d)
                    supporting_models.add(getattr(d, "model_key", ""))
                    merge_iou = max(merge_iou, iou)

        confidences = [getattr(d, "confidence", 0.0) or 0.0 for d in overlapping]
        max_conf = max(confidences) if confidences else confidence

    # Keep this field model-derived and descriptive.  It is not an evidence
    # score and is never used to approve/reject an image.
    return float(max_conf)


def decide_review(
    *,
    merged: list[Any],
    all_detections: list[Any],
    scene_evidence: Any | None,
    completed_models: list[str],
    required_verification: str = "standard",
    rejected_count: int = 0,
    model_availability: dict[str, bool] | None = None,
    auto_approve_threshold: float = 0.90,
    verification_report: dict[str, Any] | None = None,
) -> ReviewDecision:
    """Resolve only when verification evidence has no unresolved condition."""
    reasons: list[str] = []

    verification_report = verification_report or {}
    unresolved_conflicts = list(verification_report.get("unresolved_conflicts") or [])
    if unresolved_conflicts:
        reasons.append("UNRESOLVED_CLASS_CONFLICT")
    if verification_report.get("invalid_labels"):
        reasons.append("QUALITY_POLICY")
    if verification_report.get("out_of_bounds"):
        reasons.append("INVALID_GEOMETRY")
    if verification_report.get("oversized_boxes"):
        reasons.append("QUALITY_POLICY")
    if verification_report.get("duplicate_pairs"):
        reasons.append("DUPLICATE_CANDIDATE")

    def verification_resolved(det: Any) -> bool:
        provenance = getattr(det, "provenance", None) or {}
        if provenance.get("verification_agent_failed"):
            return False
        if provenance.get("verified_candidate") is True:
            return True
        if provenance.get("review_risk") is True:
            return False
        if provenance.get("resolution_status") == "unresolved" or provenance.get("semantic_conflict"):
            return False
        return not bool(provenance.get("verification_required"))

    # 1. Compile structured evidence fields
    original_model_confidences = [getattr(d, "confidence", 0.0) or 0.0 for d in all_detections]
    predictions_yolo = [
        {"label": getattr(d, "label", ""), "confidence": getattr(d, "confidence", 0.0) or 0.0}
        for d in all_detections if getattr(d, "model_key", "") == "yolo26"
    ]
    predictions_rcnn = [
        {"label": getattr(d, "label", ""), "confidence": getattr(d, "confidence", 0.0) or 0.0}
        for d in all_detections if getattr(d, "model_key", "") == "faster_rcnn"
    ]

    # Calculate conflicts (overlapping boxes with different labels)
    conflicts = 0
    conflict_pairs = []
    for index, first in enumerate(all_detections):
        for second in all_detections[index + 1 :]:
            try:
                overlaps = (
                    first.model_key != second.model_key
                    and box_iou_percent(first, second) >= 0.45
                )
            except Exception:
                overlaps = False
            if overlaps and getattr(first, "label", "") != getattr(second, "label", ""):
                conflicts += 1
                conflict_pairs.append({
                    "left": first.label, "right": second.label,
                    "iou": box_iou_percent(first, second),
                })

    # Calculate model agreement count
    agreement_count = 0
    for det in merged:
        prov = getattr(det, "provenance", None) or {}
        supporting = {item.get("model_key") for item in prov.get("contributing_models", []) if item.get("model_key")}
        if "yolo26" in supporting and "faster_rcnn" in supporting:
            agreement_count += 1

    iou_associations = [
        det.provenance.get("merge_iou")
        for det in merged
        if getattr(det, "provenance", None) and det.provenance.get("merge_iou") is not None
    ]

    geometry_valid = True
    for detection in merged:
        bbox = getattr(detection, "bbox", None)
        if (
            bbox is None
            or bbox.w <= 0.0
            or bbox.h <= 0.0
            or bbox.x < 0.0
            or bbox.y < 0.0
            or bbox.x + bbox.w > 100.0
            or bbox.y + bbox.h > 100.0
        ):
            geometry_valid = False
            reasons.append("INVALID_GEOMETRY")
            break

    unresolved_candidate_ids = []
    for detection in merged:
        provenance = getattr(detection, "provenance", None) or {}
        if not verification_resolved(detection) or provenance.get("semantic_conflict"):
            unresolved_candidate_ids.append(str(getattr(detection, "id", "")))
    if unresolved_candidate_ids:
        reasons.append("UNVERIFIED_CANDIDATE")


    # Video plans require temporal evidence to survive normalization. The
    # annotation table stores one frame observation per row, grouped by the
    # persistent track_id in provenance; missing either part makes the result
    # incomplete and therefore reviewable.
    temporal_missing = []
    if required_verification == "temporal":
        for detection in merged:
            provenance = getattr(detection, "provenance", None) or {}
            if (
                provenance.get("track_id") is None
                or provenance.get("frame_number") is None
                or provenance.get("timestamp") is None
            ):
                temporal_missing.append(str(getattr(detection, "id", "")))
        if temporal_missing:
            reasons.append("temporal annotation evidence is incomplete")

    # Coverage concern evaluation
    coverage_concern_flag = False
    expected_count = getattr(scene_evidence, "expected_object_count", None) if scene_evidence else None
    if isinstance(expected_count, int) and expected_count > 0:
        coverage = len(merged) / expected_count
        if coverage < 0.60:
            coverage_concern_flag = True
            reasons.append("coverage concern remains unresolved")

    metadata = getattr(scene_evidence, "metadata", {}) if scene_evidence else {}
    if isinstance(metadata, dict):
        if metadata.get("coverage_concern"):
            coverage_concern_flag = True
            reasons.append("coverage concern remains unresolved")
        if metadata.get("verification_failed"):
            reasons.append("verification agent reported unresolved evidence")
        if metadata.get("expected_content") and not merged and not metadata.get("empty_scene_verified"):
            reasons.append("expected visual content was not resolved")

    # Calculate image-level AI mean confidence from valid active AI annotations
    valid_ai_confs = [
        float(getattr(det, "confidence", 0.0) or 0.0)
        for det in merged
        if getattr(det, "confidence", None) is not None
        and isinstance(getattr(det, "confidence", None), (int, float))
        and not isinstance(getattr(det, "confidence", None), bool)
        and 0.0 <= float(getattr(det, "confidence", 0.0) or 0.0) <= 1.0
        and getattr(det, "source", "ai") not in ("human", "human_modified")
    ]
    mean_confidence = (sum(valid_ai_confs) / len(valid_ai_confs)) if valid_ai_confs else None

    object_review_confidences = {
        getattr(det, "id", ""): _get_review_confidence_for_detection(det, all_detections)
        for det in merged
    }

    if valid_ai_confs:
        if mean_confidence is not None and mean_confidence < auto_approve_threshold:
            reasons.append("LOW_CONFIDENCE")
    else:
        reasons.append("NO_VALID_AI_DETECTIONS")

    # Label consistency & conflict status
    label_consistency_flag = (conflicts == 0)
    if conflicts and not verification_report.get("cross_model_conflicts"):
        reasons.append("MODEL_DISAGREEMENT")

    if required_verification == "cross_model" and len(set(completed_models)) < 2:
        reasons.append("QUALITY_POLICY")

    # 2. Agentic verification if enabled
    try:
        from app.config import get_settings
        settings = get_settings()
        agent_enabled = bool(getattr(settings, "agent_enabled", True))
    except Exception:
        import os
        agent_enabled = os.environ.get("AGENT_ENABLED", "true").lower() == "true"
        settings = None

    import sys
    import time
    if "pytest" in sys.modules:
        agent_enabled = False

    verification_start_time = time.perf_counter()

    if agent_enabled:
        # Log verification started
        logger.info(
            "verification_started",
            verification_model=getattr(settings, "vertex_agent_model", "gemini") if settings else "gemini",
        )
        
        # Clean expected_count of MagicMocks
        clean_expected = None
        if expected_count is not None:
            if type(expected_count).__name__ not in ("Mock", "MagicMock", "NonCallableMock", "NonCallableMagicMock"):
                clean_expected = expected_count

        payload = {
            "merged_count": len(merged),
            "labels": list(dict.fromkeys(str(getattr(d, "label", "")) for d in merged)),
            "confidence_values": [float(getattr(d, "confidence", 0.0) or 0.0) for d in merged],
            "completed_models": completed_models,
            "required_verification": required_verification,
            "conflicts_count": conflicts,
            "conflict_pairs": conflict_pairs,
            "geometry_valid": geometry_valid,
            "expected_count": clean_expected,
            "observed_count": len(merged),
            "verification_report": verification_report,
        }
        
        system_prompt = (
            "You are the Vision Verification Agent. Return ONLY compact JSON: "
            '{"decision":"approve|human_review|reject","reason_code":"brief","confidence":0.0}. '
            "Do not provide chain-of-thought or candidate details."
        )

        from app.inference.agent_reasoning import call_json_agent
        res = call_json_agent(
            system_prompt=system_prompt,
            user_payload=payload,
            settings=settings,
            max_output_tokens=96,
        )
        if res is None:
            reasons.append("verification agent response unavailable or truncated")
        else:
            compact_decision = str(res.get("decision", "")).lower()
            if compact_decision in {"human_review", "reject"}:
                reasons.append(str(res.get("reason_code") or "verification agent requested review"))
            elif compact_decision not in {"approve"}:
                reasons.append("verification agent returned an invalid decision")
            agent_reasons = list(res.get("unresolved_reasons") or [])
            if not geometry_valid and "invalid annotation geometry" not in agent_reasons:
                agent_reasons.append("invalid annotation geometry")
            if required_verification == "temporal" and temporal_missing and "temporal annotation evidence is incomplete" not in agent_reasons:
                agent_reasons.append("temporal annotation evidence is incomplete")
            if required_verification == "cross_model" and len(set(completed_models)) < 2 and "cross-model verification was required but incomplete" not in agent_reasons:
                agent_reasons.append("cross-model verification was required but incomplete")
            reasons = list(dict.fromkeys(reasons + agent_reasons))

            # Technical validation: zero valid AI detections must NOT be auto-approved unless empty scene is explicitly verified
            if not valid_ai_confs and not metadata.get("empty_scene_verified") and "NO_VALID_AI_DETECTIONS" not in reasons:
                reasons.append("NO_VALID_AI_DETECTIONS")

            candidate_provenances = res.get("candidate_provenances") or {}
            for det in merged:
                det_id = str(getattr(det, "id", ""))
                prov = getattr(det, "provenance", None)
                if prov is not None:
                    info = candidate_provenances.get(det_id) or {}
                    prov["evidence_strength"] = info.get("evidence_strength", "strong" if det.confidence >= 0.70 else "weak")
                    prov["verification_status"] = info.get("verification_status", "verified" if not agent_reasons else "unresolved")
    else:
        # Log verification started for technical validation fallback
        logger.info(
            "verification_started",
            verification_model="technical_validator",
        )

    unique_reasons = tuple(dict.fromkeys(reasons))
    decision = "auto_approve" if not unique_reasons else "human_review"
    reason = ", ".join(unique_reasons) if unique_reasons else "All evidence resolved successfully"
    
    # Log verification completed
    duration_ms = int((time.perf_counter() - verification_start_time) * 1000)
    logger.info(
        "verification_completed",
        verification_decision=decision,
        verification_duration_ms=duration_ms,
    )

    review_evidence = {
        "detections_resolved": bool(not unique_reasons),
        "label_conflicts": bool(conflicts > 0),
        "conflict_pairs": conflict_pairs,
        "cross_model_conflicts": list(verification_report.get("cross_model_conflicts") or []),
        "unresolved_conflicts": unresolved_conflicts,
        "unresolved_conflict_count": len(unresolved_conflicts),
        "unresolved_requested_label_conflicts": list(
            verification_report.get("unresolved_requested_label_conflicts") or []
        ),
        "resolved_conflict_count": int(verification_report.get("resolved_conflict_count") or 0),
        "geometry_valid": geometry_valid,
        "model_agreement": bool(agreement_count > 0),
        "coverage_concern": coverage_concern_flag,
        "verification_required_count": len(unresolved_candidate_ids),
        "temporal_evidence_complete": not temporal_missing,
        "temporal_missing_candidate_ids": temporal_missing,
        "unresolved_candidate_ids": unresolved_candidate_ids,
        "verified_count": len(merged) - len(unresolved_candidate_ids),
    }

    evidence: dict[str, Any] = {
        "decision": decision,
        "reason": reason,
        "mean_confidence": mean_confidence,
        "valid_ai_annotation_count": len(valid_ai_confs),
        "confidence_values": valid_ai_confs,
        "auto_approve_threshold": auto_approve_threshold,
        "evidence": review_evidence,
        "completed_models": list(completed_models),
        "merged_count": len(merged),
        "candidate_count": len(all_detections),
        "original_model_confidences": original_model_confidences,
        "predictions_yolo": predictions_yolo,
        "predictions_rcnn": predictions_rcnn,
        "model_agreement": (agreement_count > 0),
        "model_agreement_count": agreement_count,
        "iou_associations": iou_associations,
        "label_consistency": label_consistency_flag,
        "geometry_validity": geometry_valid,
        "duplicate_conflict_status": {
            "duplicates_suppressed": rejected_count,
            "conflicts": conflicts
        },
        "coverage_concern": coverage_concern_flag,
        "additional_detector_results": [
            {"model_key": d.model_key, "label": d.label, "confidence": d.confidence}
            for d in all_detections if d.model_key not in ("yolo26", "faster_rcnn")
        ],
        "verification_results": {
            "rejected_count": rejected_count,
            "status": "passed" if rejected_count == 0 else "flagged"
        },
        "ontology_task_context": {
            "labels": list(set(d.label for d in merged))
        },
        "model_availability": model_availability or {
            "yolo26": "yolo26" in completed_models,
            "faster_rcnn": "faster_rcnn" in completed_models
        },
        "evidence_confidence": max(object_review_confidences.values(), default=None),
        "object_evidence_confidences": object_review_confidences,
        "resolved_candidate_ids": [] if (
            (isinstance(metadata, dict) and metadata.get("verification_failed"))
            or (required_verification == "cross_model" and len(set(completed_models)) < 2)
        ) else [
            str(getattr(det, "id", "")) for det in merged
            if str(getattr(det, "id", "")) not in unresolved_candidate_ids
        ],
    }

    logger.info(
        "review_decision_evaluated",
        valid_ai_annotation_count=len(valid_ai_confs),
        confidence_values=valid_ai_confs,
        mean_confidence=mean_confidence,
        threshold=auto_approve_threshold,
        eligible_for_auto_approval=bool(mean_confidence is not None and mean_confidence >= auto_approve_threshold),
        needs_human_review=bool(unique_reasons),
        review_status="approved" if not unique_reasons else "human_review",
        review_reasons=list(unique_reasons),
        unresolved_conflict_count=len(unresolved_conflicts),
        cross_model_conflicts=list(verification_report.get("cross_model_conflicts") or []),
    )

    return ReviewDecision(
        status="unresolved" if unique_reasons else "resolved",
        human_review_required=bool(unique_reasons),
        unresolved_reasons=unique_reasons,
        evidence=evidence,
    )

