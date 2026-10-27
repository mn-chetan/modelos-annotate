"""Quality Check (QC) Auditor Service.

Handles:
1. QC Streams: 100% human-submitted tasks + 2%-5% sampled high-confidence AI tasks.
2. 12-Point QC Audit Checklist validation and persistence.
3. QC PASS -> FINAL_APPROVED (state locking).
4. QC FAIL -> REWORK_REQUIRED (mandatory auditor feedback & failed checklist items).
5. AI vs Final Approved Annotation Error Delta calculation (missed, added, label corrections, geometry corrections).
6. Ready for Model Improvement status transition.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.models import MongoSession, get_database
from app.domain.enums import HumanRole, ReviewAction, ReviewStatus
from app.errors import ValidationAppError
from app.logging import get_logger
from app.services.audit_trail import record_audit_event

logger = get_logger(__name__)

QC_CHECKLIST_ITEMS = [
    "completeness",
    "label_accuracy",
    "ontology_compliance",
    "localization_accuracy",
    "missing_objects",
    "extra_objects",
    "duplicate_objects",
    "confidence_routing_correctness",
    "human_correction_correctness",
    "required_fields",
    "guideline_compliance",
    "domain_specific_validation",
]


def calculate_annotation_delta(
    ai_annotations: list[dict[str, Any]],
    final_annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate reward / error delta between original AI predictions and final approved annotations."""
    from app.services.quality_validation import calculate_box_iou

    ai_matched = set()
    final_matched = set()
    label_corrections = 0
    geometry_corrections = 0
    attribute_corrections = 0

    for i, ai_ann in enumerate(ai_annotations):
        ai_box = ai_ann.get("bbox") or [
            ai_ann.get("x", 0),
            ai_ann.get("y", 0),
            ai_ann.get("w", 0),
            ai_ann.get("h", 0),
        ]
        ai_lbl = str(ai_ann.get("label", "")).strip().casefold()

        best_j = None
        best_iou = 0.0

        for j, fin_ann in enumerate(final_annotations):
            if j in final_matched:
                continue
            fin_box = fin_ann.get("bbox") or [
                fin_ann.get("x", 0),
                fin_ann.get("y", 0),
                fin_ann.get("w", 0),
                fin_ann.get("h", 0),
            ]
            iou = calculate_box_iou(ai_box, fin_box)
            if iou > best_iou:
                best_iou = iou
                best_j = j

        if best_j is not None and best_iou >= 0.45:
            ai_matched.add(i)
            final_matched.add(best_j)
            fin_ann = final_annotations[best_j]
            fin_lbl = str(fin_ann.get("label", "")).strip().casefold()

            if ai_lbl != fin_lbl:
                label_corrections += 1
            if best_iou < 0.85:
                geometry_corrections += 1
            if ai_ann.get("attributes") != fin_ann.get("attributes"):
                attribute_corrections += 1

    missed_objects = len(final_annotations) - len(final_matched)  # Added by human
    added_objects = len(ai_annotations) - len(ai_matched)  # AI false positives removed

    return {
        "original_ai_count": len(ai_annotations),
        "final_approved_count": len(final_annotations),
        "missed_objects": max(0, missed_objects),
        "extra_ai_objects_removed": max(0, added_objects),
        "label_corrections": label_corrections,
        "geometry_corrections": geometry_corrections,
        "attribute_corrections": attribute_corrections,
        "total_corrections": (
            max(0, missed_objects)
            + max(0, added_objects)
            + label_corrections
            + geometry_corrections
            + attribute_corrections
        ),
    }


async def submit_for_qc(
    *,
    db: Any,
    asset_id: str,
    project_id: str,
    annotator_id: str,
    annotations: list[dict[str, Any]],
    change_reason: str = "Human annotation completed",
) -> dict[str, Any]:
    """Human Annotator submits work for QC."""
    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        raise ValidationAppError(f"Asset {asset_id} not found", details={"asset_id": asset_id})

    # STEP 3: Do not allow submissions on already FINAL_APPROVED / locked tasks
    if asset.get("is_locked") or asset.get("review_status") == ReviewStatus.FINAL_APPROVED.value or asset.get("workflow_status") == "FINAL_APPROVED":
        raise ValidationAppError(
            f"Asset {asset_id} is locked and final approved; cannot submit for QC.",
            details={"asset_id": asset_id, "current_status": "FINAL_APPROVED"},
        )

    # Record before state
    cursor = db.annotations.find({"asset_id": asset_id})
    before_state = await cursor.to_list(length=1000)

    # Replace with updated human annotations
    await db.annotations.delete_many({"asset_id": asset_id})

    now = datetime.now(UTC)
    new_rows = []
    preserved_ai_confidences: list[float] = []
    for ann in annotations:
        ann_id = ann.get("id") or str(uuid4())
        bbox = ann.get("bbox") or [ann.get("x", 0), ann.get("y", 0), ann.get("w", 0), ann.get("h", 0)]
        x = float(ann.get("x") if ann.get("x") is not None else (bbox[0] if bbox and len(bbox) > 0 else 0.0))
        y = float(ann.get("y") if ann.get("y") is not None else (bbox[1] if bbox and len(bbox) > 1 else 0.0))
        w = float(ann.get("w") if ann.get("w") is not None else (bbox[2] if bbox and len(bbox) > 2 else 0.0))
        h = float(ann.get("h") if ann.get("h") is not None else (bbox[3] if bbox and len(bbox) > 3 else 0.0))

        src = str(ann.get("source") or "human").lower()
        conf = ann.get("confidence")
        if conf is None:
            conf = ann.get("raw_confidence")
        if src in ("human", "human_added", "human_created") and not ann.get("model_id"):
            conf = None

        # QC submission must keep the original model score for reporting. The
        # final human annotation remains confidence=None; the AI score is
        # provenance, not a fabricated confidence for the human edit.
        provenance = dict(ann.get("provenance") or {})
        original_ai_confidence = (
            provenance.get("original_ai_confidence")
            or ann.get("original_ai_confidence")
            or ann.get("raw_model_confidence")
            or (ann.get("confidence") if ann.get("source") == "ai" else None)
        )
        if original_ai_confidence is not None:
            try:
                original_ai_confidence = float(original_ai_confidence)
                preserved_ai_confidences.append(original_ai_confidence)
                provenance.setdefault("original_ai_confidence", original_ai_confidence)
            except (TypeError, ValueError):
                original_ai_confidence = None

        new_row = {
            "id": ann_id,
            "asset_id": asset_id,
            "project_id": project_id,
            "label": ann.get("label", ""),
            "confidence": conf,
            "source": ann.get("source") or "human",
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "bbox": [x, y, w, h],
            "polygon": ann.get("polygon"),
            "geometry_type": ann.get("geometry_type", "box"),
            "attributes": ann.get("attributes", {}),
            "provenance": provenance,
            "original_ai_confidence": original_ai_confidence,
            "created_at": now,
            "updated_at": now,
        }
        new_rows.append(new_row)

    if new_rows:
        await db.annotations.insert_many(new_rows)

    # State Transition: SUBMITTED_FOR_QC / QUALITY_AUDIT_REQUIRED
    new_status = ReviewStatus.SUBMITTED_FOR_QC.value
    await db.assets.update_one(
        {"id": asset_id},
        {
            "$set": {
                "review_status": new_status,
                "workflow_status": "QC_PENDING",
                "qc_status": "QC_PENDING",
                "current_real_status": "QC_PENDING",
                "submitted_by": annotator_id,
                "is_locked": False,
                "updated_at": now,
                "mean_confidence": (
                    sum(preserved_ai_confidences) / len(preserved_ai_confidences)
                    if preserved_ai_confidences else asset.get("mean_confidence")
                ),
            }
        },
    )

    # STEP 1: Ensure QC task is created/available for Quality Auditor without duplicates in decisions collection
    existing_decision = await db.decisions.find_one({"asset_id": asset_id})
    decision_id = existing_decision.get("id") if (existing_decision and existing_decision.get("id")) else f"hitl_{str(uuid4())[:8]}"

    # Delete any duplicate decision records for this asset
    await db.decisions.delete_many({"asset_id": asset_id})

    # Insert authoritative single decision doc for Quality Auditor
    await db.decisions.insert_one({
        "id": decision_id,
        "project_id": project_id,
        "asset_id": asset_id,
        "status": ReviewStatus.QUALITY_AUDIT_REQUIRED.value,
        "workflow_state": "QC_PENDING",
        "role": HumanRole.QUALITY_AUDITOR.value,
        "assigned_role": HumanRole.QUALITY_AUDITOR.value,
        "decision_type": "human_submitted_qc",
        "confidence": asset.get("mean_confidence") or 0.5,
        "original_ai_confidence": asset.get("mean_confidence") or 0.5,
        "audit_source": "HUMAN_REVIEW",
        "question": "Human annotation completed - Quality Audit Required",
        "current_annotations": new_rows,
        "rework_feedback": None,
        "defect_category": None,
        "auditor_id": None,
        "created_at": existing_decision.get("created_at") if existing_decision else now,
        "updated_at": now,
    })

    # Persist audit trail
    await record_audit_event(
        db=db,
        project_id=project_id,
        asset_id=asset_id,
        request_id=f"{asset_id}:hitl",
        annotation_id=None,
        actor_id=annotator_id,
        actor_role="HUMAN_ANNOTATOR",
        before_state={"annotations": before_state},
        after_state={"annotations": new_rows},
        action=ReviewAction.SUBMIT.value,
        reason=change_reason,
    )

    return {
        "asset_id": asset_id,
        "status": new_status,
        "workflow_status": "QC_PENDING",
        "qc_status": "QC_PENDING",
        "current_real_status": "QC_PENDING",
        "is_locked": False,
        "annotations_count": len(new_rows),
        "submitted_at": now.isoformat(),
    }


async def process_qc_decision(
    *,
    db: Any,
    asset_id: str,
    project_id: str,
    auditor_id: str,
    decision: str,  # "PASS" or "FAIL"
    checklist: dict[str, bool],
    comments: str = "",
    required_correction: str = "",
) -> dict[str, Any]:
    """QC Auditor evaluates task with 12-point checklist."""
    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        raise ValidationAppError(f"Asset {asset_id} not found", details={"asset_id": asset_id})

    norm_decision = str(decision).strip().upper()
    if norm_decision not in ("PASS", "FAIL"):
        raise ValidationAppError(
            f"QC Decision must be 'PASS' or 'FAIL', got '{decision}'",
            details={"decision": decision},
        )

    # STEP 3: Validate current task state before transition
    curr_wf = str(asset.get("workflow_status") or "").strip().upper()
    curr_rev = str(asset.get("review_status") or "").strip().lower()
    curr_qc = str(asset.get("qc_status") or "").strip().upper()

    is_qc_pending = (
        curr_wf in ("QC_PENDING", "SUBMITTED_FOR_QC")
        or curr_rev in ("submitted_for_qc", "quality_audit_required", "high_confidence_qc_sample", "qc_pending")
        or curr_qc == "QC_PENDING"
    )

    # Reject if asset is already FINAL_APPROVED and locked
    if asset.get("is_locked") or curr_rev == "final_approved" or curr_wf == "FINAL_APPROVED":
        raise ValidationAppError(
            "Invalid state transition: Asset is already FINAL_APPROVED and locked.",
            details={"asset_id": asset_id, "current_status": "FINAL_APPROVED"},
        )

    # Reject if not in QC_PENDING state (e.g. HUMAN_REVIEW -> FINAL_APPROVED or REWORK_REQUIRED -> FINAL_APPROVED)
    if not is_qc_pending:
        current_display = curr_wf or (
            "HUMAN_REVIEW" if curr_rev in ("human_review_required", "in_human_review", "pending", "human_review")
            else "REWORK_REQUIRED" if curr_rev == "human_rework_required"
            else curr_rev
        )
        raise ValidationAppError(
            f"Invalid state transition: Cannot perform QC evaluation on asset in '{current_display}' state. Task must be in QC_PENDING state (submitted for QC by Human Annotator).",
            details={
                "asset_id": asset_id,
                "current_status": current_display,
                "required_status": "QC_PENDING",
            },
        )

    # Requirement 7: FAIL requires failure_reason & required_correction
    if norm_decision == "FAIL" and not (comments.strip() or required_correction.strip()):
        raise ValidationAppError(
            "QC Failure requires mandatory auditor comments or required_correction feedback.",
            details={"asset_id": asset_id, "decision": "FAIL"},
        )

    now = datetime.now(UTC)
    previous_status = asset.get("review_status", ReviewStatus.SUBMITTED_FOR_QC.value)

    if norm_decision == "PASS":
        new_status = ReviewStatus.FINAL_APPROVED.value
        qc_status = ReviewStatus.QC_PASSED.value

        # Fetch original AI predictions vs final approved annotations for error delta
        cursor_model = db.model_runs.find({"asset_id": asset_id})
        ai_runs = await cursor_model.to_list(length=1000)
        ai_annos = [r.get("detection") for r in ai_runs if r.get("detection")]

        cursor_final = db.annotations.find({"asset_id": asset_id})
        final_annos = await cursor_final.to_list(length=1000)

        delta = calculate_annotation_delta(ai_annos, final_annos)

        # Transition: QC_PENDING -> FINAL_APPROVED (Lock task)
        await db.assets.update_one(
            {"id": asset_id},
            {
                "$set": {
                    "review_status": new_status,
                    "workflow_status": "FINAL_APPROVED",
                    "qc_status": qc_status,
                    "current_real_status": "FINAL_APPROVED",
                    "is_locked": True,
                    "auditor_id": auditor_id,
                    "qc_timestamp": now,
                    "checklist_results": checklist,
                    "auditor_comments": comments,
                    "annotation_delta": delta,
                    "model_improvement_status": ReviewStatus.READY_FOR_MODEL_IMPROVEMENT.value,
                    "updated_at": now,
                }
            },
        )

        # Update decision state
        await db.decisions.update_many(
            {"asset_id": asset_id},
            {
                "$set": {
                    "status": ReviewStatus.FINAL_APPROVED.value,
                    "workflow_state": "FINAL_APPROVED",
                    "role": "SYSTEM",
                    "answer": "PASS",
                    "auditor_id": auditor_id,
                    "resolved_at": now,
                    "updated_at": now,
                }
            },
        )
    else:
        new_status = ReviewStatus.HUMAN_REWORK_REQUIRED.value
        qc_status = ReviewStatus.QC_FAILED.value

        # Transition: QC_PENDING -> REWORK_REQUIRED (Route back to Human Annotator)
        await db.assets.update_one(
            {"id": asset_id},
            {
                "$set": {
                    "review_status": new_status,
                    "workflow_status": "REWORK_REQUIRED",
                    "qc_status": qc_status,
                    "current_real_status": "REWORK_REQUIRED",
                    "is_locked": False,
                    "auditor_id": auditor_id,
                    "qc_timestamp": now,
                    "checklist_results": checklist,
                    "auditor_comments": comments,
                    "required_correction": required_correction or comments,
                    "qc_auditor_feedback": comments,
                    "qc_rework_instruction": required_correction or comments,
                    "updated_at": now,
                }
            },
        )

        # Route decision back to Human Annotator
        await db.decisions.update_many(
            {"asset_id": asset_id},
            {
                "$set": {
                    "status": ReviewStatus.HUMAN_REWORK_REQUIRED.value,
                    "workflow_state": "REWORK_REQUIRED",
                    "role": HumanRole.HUMAN_ANNOTATOR.value,
                    "assigned_role": HumanRole.HUMAN_ANNOTATOR.value,
                    "answer": "FAIL",
                    "rework_feedback": comments or required_correction,
                    "auditor_id": auditor_id,
                    "audited_at": now,
                    "updated_at": now,
                }
            },
        )

    # Persist review note document
    note_id = str(uuid4())
    await db.review_notes.insert_one({
        "id": note_id,
        "asset_id": asset_id,
        "project_id": project_id,
        "auditor_id": auditor_id,
        "qc_decision": norm_decision,
        "checklist": checklist,
        "comments": comments,
        "required_correction": required_correction,
        "created_at": now,
    })

    # Audit trail
    await record_audit_event(
        db=db,
        project_id=project_id,
        asset_id=asset_id,
        request_id=f"{asset_id}:qc",
        annotation_id=None,
        actor_id=auditor_id,
        actor_role="QUALITY_AUDITOR",
        action=ReviewAction.PASS.value if norm_decision == "PASS" else ReviewAction.FAIL.value,
        reason=comments or required_correction or f"QC {norm_decision}",
        before_state={"status": previous_status},
        after_state={"status": new_status, "checklist": checklist, "comments": comments},
    )

    return {
        "asset_id": asset_id,
        "decision": norm_decision,
        "status": new_status,
        "workflow_status": "FINAL_APPROVED" if norm_decision == "PASS" else "REWORK_REQUIRED",
        "current_real_status": "FINAL_APPROVED" if norm_decision == "PASS" else "REWORK_REQUIRED",
        "qc_status": qc_status,
        "is_locked": True if norm_decision == "PASS" else False,
        "timestamp": now.isoformat(),
    }


async def _fetch_cursor(cursor: Any) -> list[dict[str, Any]]:
    if isinstance(cursor, list):
        return cursor
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(length=1000)
    if hasattr(cursor, "__aiter__"):
        return [r async for r in cursor]
    return []


async def calculate_hitl_execution_metrics(db: Any, project_id: str, decisions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Calculate the 5 authoritative HITL Execution Report metrics from persisted database data."""
    import time
    t0 = time.perf_counter()
    from app.services.quality_validation import calculate_box_iou

    # ---------------------------------------------------------------------------
    # 1. Audit Pass Rate & 3. Defect Leakage
    # ---------------------------------------------------------------------------
    t_start = time.perf_counter()
    review_notes = await _fetch_cursor(db.review_notes.find({"project_id": project_id}))
    assets = await _fetch_cursor(db.assets.find({"project_id": project_id}))
    logger.info("hitl_timing_assets_review_notes", elapsed_ms=round((time.perf_counter() - t_start) * 1000, 2), assets_count=len(assets), review_notes_count=len(review_notes))

    audited_assets: dict[str, dict[str, Any]] = {}
    for rn in review_notes:
        aid = rn.get("asset_id")
        dec = str(rn.get("qc_decision", "")).strip().upper()
        checklist = rn.get("checklist") or {}
        has_defect = (dec == "FAIL") or any(v is False for v in checklist.values())
        if aid not in audited_assets:
            audited_assets[aid] = {"decision": dec, "has_defect": has_defect}
        else:
            if dec in ("PASS", "FAIL"):
                audited_assets[aid]["decision"] = dec
            if has_defect:
                audited_assets[aid]["has_defect"] = True

    for a in assets:
        aid = a.get("id") or a.get("_id")
        qc_stat = str(a.get("qc_status", "")).upper()
        rev_stat = str(a.get("review_status", "")).lower()
        auditor_id = a.get("auditor_id")
        if auditor_id:
            if qc_stat == "QC_PASSED" or rev_stat == "final_approved":
                if aid not in audited_assets:
                    audited_assets[aid] = {"decision": "PASS", "has_defect": False}
            elif qc_stat == "QC_FAILED" or rev_stat == "human_rework_required":
                if aid not in audited_assets:
                    audited_assets[aid] = {"decision": "FAIL", "has_defect": True}

    passed_count = sum(1 for v in audited_assets.values() if v["decision"] == "PASS")
    failed_count = sum(1 for v in audited_assets.values() if v["decision"] == "FAIL")
    total_audited = passed_count + failed_count
    defective_count = sum(1 for v in audited_assets.values() if v.get("has_defect"))

    if total_audited > 0:
        audit_pass_rate = {
            "value": round((passed_count / total_audited) * 100.0, 1),
            "passed_audited_samples": passed_count,
            "total_audited_samples": total_audited,
            "passed": passed_count,
            "audited": total_audited,
            "status": "AVAILABLE",
        }
        defect_leakage = {
            "value": round((defective_count / total_audited) * 100.0, 1),
            "defective_audited_samples": defective_count,
            "total_audited_samples": total_audited,
            "defective": defective_count,
            "audited": total_audited,
            "status": "AVAILABLE",
        }
    else:
        audit_pass_rate = {
            "value": None,
            "passed_audited_samples": 0,
            "total_audited_samples": 0,
            "passed": 0,
            "audited": 0,
            "status": "DATA_NOT_AVAILABLE",
            "reason": "No completed QA audits available",
        }
        defect_leakage = {
            "value": None,
            "defective_audited_samples": 0,
            "total_audited_samples": 0,
            "defective": 0,
            "audited": 0,
            "status": "DATA_NOT_AVAILABLE",
            "reason": "No authoritative defect leakage evidence available",
        }

    # ---------------------------------------------------------------------------
    # 2. Mean IoU (Ground Truth) & 5. Model IoU Threshold Acceptance Distribution
    # ---------------------------------------------------------------------------
    if decisions is None:
        t_dec = time.perf_counter()
        decisions = await _fetch_cursor(db.decisions.find({"project_id": project_id}))
        logger.info("hitl_timing_decisions_query", elapsed_ms=round((time.perf_counter() - t_dec) * 1000, 2), decisions_count=len(decisions))
    ai_outputs_by_asset: dict[str, list[dict[str, Any]]] = {}
    for d in decisions:
        aid = d.get("asset_id")
        orig = d.get("original_ai_output")
        if aid and orig:
            ai_outputs_by_asset[aid] = orig

    approved_asset_ids = {
        (a.get("id") or a.get("_id"))
        for a in assets
        if a.get("review_status") in ("final_approved", "human_approved", "human_modified_approved")
        or a.get("qc_status") == "QC_PASSED"
    }

    # Pre-fetch all annotations for this project in one bulk query and index by asset_id
    t_annos = time.perf_counter()
    all_annos = await _fetch_cursor(db.annotations.find({"project_id": project_id}))
    annos_by_asset: dict[str, list[dict[str, Any]]] = {}
    for a in all_annos:
        aid_key = a.get("asset_id")
        if aid_key:
            annos_by_asset.setdefault(aid_key, []).append(a)
    logger.info("hitl_timing_bulk_annotations_fetch", elapsed_ms=round((time.perf_counter() - t_annos) * 1000, 2), count=len(all_annos))

    t_ious = time.perf_counter()
    valid_ious: list[float] = []
    logger.info("hitl_timing_start_approved_asset_loop", approved_asset_count=len(approved_asset_ids))
    for aid in approved_asset_ids:
        ai_annos = ai_outputs_by_asset.get(aid, [])
        if not ai_annos:
            continue
        final_annos = annos_by_asset.get(aid, [])

        for ai_a in ai_annos:
            ai_box = ai_a.get("bbox") or [ai_a.get("x", 0), ai_a.get("y", 0), ai_a.get("w", 0), ai_a.get("h", 0)]
            ai_lbl = str(ai_a.get("label", "")).strip().casefold()
            best_iou = 0.0
            for fin_a in final_annos:
                fin_box = fin_a.get("bbox") or [fin_a.get("x", 0), fin_a.get("y", 0), fin_a.get("w", 0), fin_a.get("h", 0)]
                fin_lbl = str(fin_a.get("label", "")).strip().casefold()
                if ai_lbl == fin_lbl:
                    iou = calculate_box_iou(ai_box, fin_box)
                    if iou > best_iou:
                        best_iou = iou
            if best_iou > 0.0:
                valid_ious.append(best_iou)
    logger.info("hitl_timing_approved_asset_loop_total", elapsed_ms=round((time.perf_counter() - t_ious) * 1000, 2))

    if valid_ious:
        mean_iou_val = round(sum(valid_ious) / len(valid_ious), 2)
        n = len(valid_ious)
        mean_iou = {
            "value": mean_iou_val,
            "evaluated_annotations": n,
            "matched_annotations": n,
            "status": "AVAILABLE",
        }
        c1 = sum(1 for x in valid_ious if x > 0.95)
        c2 = sum(1 for x in valid_ious if 0.85 <= x <= 0.95)
        c3 = sum(1 for x in valid_ious if 0.70 <= x < 0.85)
        c4 = sum(1 for x in valid_ious if x < 0.70)
        iou_distribution = {
            "total_annotations_evaluated": n,
            "total_evaluated": n,
            "buckets": [
                {"range": ">0.95", "label": "Pristine Pixel Boundary Match", "count": c1, "percentage": round((c1 / n) * 100.0, 1)},
                {"range": "0.85-0.95", "label": "Certified Production Grade", "count": c2, "percentage": round((c2 / n) * 100.0, 1)},
                {"range": "0.70-0.85", "label": "Human Adjusted in HITL", "count": c3, "percentage": round((c3 / n) * 100.0, 1)},
                {"range": "<0.70", "label": "Flagged & Discarded", "count": c4, "percentage": round((c4 / n) * 100.0, 1)},
            ],
            "status": "AVAILABLE",
        }
    else:
        mean_iou = {
            "value": None,
            "evaluated_annotations": 0,
            "matched_annotations": 0,
            "status": "DATA_NOT_AVAILABLE",
            "reason": "No verified ground-truth geometry available",
        }
        iou_distribution = {
            "total_annotations_evaluated": 0,
            "total_evaluated": 0,
            "buckets": [],
            "status": "DATA_NOT_AVAILABLE",
            "reason": "No verified IoU evaluations available",
        }

    # ---------------------------------------------------------------------------
    # 4. Inter-Annotator Agreement
    # ---------------------------------------------------------------------------
    t_audit = time.perf_counter()
    audit_events = await _fetch_cursor(db.audit_events.find({"project_id": project_id}))
    logger.info("hitl_timing_audit_events_query", elapsed_ms=round((time.perf_counter() - t_audit) * 1000, 2), count=len(audit_events))
    human_actors_by_asset: dict[str, set[str]] = {}
    for ev in audit_events:
        aid = ev.get("asset_id")
        actor_role = ev.get("actor_role")
        actor_id = ev.get("actor_id")
        if aid and actor_role == "HUMAN_ANNOTATOR" and actor_id:
            human_actors_by_asset.setdefault(aid, set()).add(actor_id)

    double_annotated_assets = [aid for aid, actors in human_actors_by_asset.items() if len(actors) >= 2]
    matching_annos = 0
    total_double_annos = 0

    if double_annotated_assets:
        t_double = time.perf_counter()
        logger.info("hitl_timing_start_double_annotated_loop", count=len(double_annotated_assets))
        for aid in double_annotated_assets:
            annos = annos_by_asset.get(aid, [])

            by_user: dict[str, list[dict[str, Any]]] = {}
            for a in annos:
                uid = a.get("created_by") or a.get("user_id") or "user1"
                by_user.setdefault(uid, []).append(a)
            user_keys = list(by_user.keys())
            if len(user_keys) >= 2:
                u1_annos = by_user[user_keys[0]]
                u2_annos = by_user[user_keys[1]]
                for a1 in u1_annos:
                    box1 = a1.get("bbox") or [a1.get("x", 0), a1.get("y", 0), a1.get("w", 0), a1.get("h", 0)]
                    lbl1 = str(a1.get("label", "")).strip().casefold()
                    total_double_annos += 1
                    matched = False
                    for a2 in u2_annos:
                        box2 = a2.get("bbox") or [a2.get("x", 0), a2.get("y", 0), a2.get("w", 0), a2.get("h", 0)]
                        lbl2 = str(a2.get("label", "")).strip().casefold()
                        if lbl1 == lbl2 and calculate_box_iou(box1, box2) >= 0.7:
                            matched = True
                            break
                    if matched:
                        matching_annos += 1
        logger.info("hitl_timing_double_annotated_loop_total", elapsed_ms=round((time.perf_counter() - t_double) * 1000, 2))

    if total_double_annos > 0:
        val = round((matching_annos / total_double_annos) * 100.0, 1)
        inter_annotator_agreement = {
            "value": val,
            "matching_annotations": matching_annos,
            "total_double_annotations": total_double_annos,
            "matching": matching_annos,
            "double_annotations": total_double_annos,
            "kappa": None,
            "status": "AVAILABLE",
        }
    else:
        inter_annotator_agreement = {
            "value": None,
            "matching_annotations": 0,
            "total_double_annotations": 0,
            "matching": 0,
            "double_annotations": 0,
            "kappa": None,
            "status": "DATA_NOT_AVAILABLE",
            "reason": "No independent double-annotation samples available",
        }

    logger.info("calculate_hitl_execution_metrics_TOTAL", elapsed_ms=round((time.perf_counter() - t0) * 1000, 2))
    return {
        "audit_pass_rate": audit_pass_rate,
        "mean_iou": mean_iou,
        "defect_leakage": defect_leakage,
        "inter_annotator_agreement": inter_annotator_agreement,
        "iou_acceptance_distribution": iou_distribution,
    }
