"""Active-learning review priority scoring."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.db.models import MongoDoc
from app.domain.enums import AnnotationSource, ReviewStatus
from app.services.confidence import calculate_image_confidence, valid_ai_object_confidences


def score_asset(
    asset: MongoDoc,
    *,
    reviewed_by_cluster: dict[int | None, int],
    total_by_cluster: dict[int | None, int],
    reviewed_count: int,
    total_count: int,
    review_risk_bonus: float = 0.0,
) -> float:
    """Higher = should be reviewed sooner."""
    uncertainty = 0.5
    mean_conf = asset.get("mean_confidence")
    if mean_conf is not None:
        uncertainty = 1.0 - float(mean_conf)

    cid = asset.get("cluster_id")
    covered = reviewed_by_cluster.get(cid, 0)
    cluster_size = max(total_by_cluster.get(cid, 1), 1)
    coverage_gap = 1.0 - (covered / cluster_size)

    is_outlier = bool(asset.get("is_outlier", False))
    outlier_bonus = 0.35 if is_outlier else 0.0
    # Early bias toward typical (medoid-like / non-outlier) examples
    progress = reviewed_count / max(total_count, 1)
    typical_bias = (1.0 - progress) * (0.25 if not is_outlier else -0.1)
    late_ambiguity = progress * uncertainty * 0.5

    diversity = coverage_gap * 0.4

    # Real signals: reprocess count, previous rejection, conflict, escalation status
    reprocess_count = float(asset.get("reprocess_count", 0) or 0)
    reprocess_bonus = min(0.35, reprocess_count * 0.12)
    r_status = str(asset.get("review_status") or "")
    escalation_bonus = 0.40 if r_status in {ReviewStatus.ESCALATED.value, ReviewStatus.SECOND_REVIEW.value} else 0.0
    rejection_bonus = 0.20 if r_status == ReviewStatus.HUMAN_REJECTED.value else 0.0
    conflict_bonus = 0.30 if bool(asset.get("review_conflict")) else 0.0

    return float(
        uncertainty * 0.45
        + diversity
        + outlier_bonus * progress
        + typical_bias
        + late_ambiguity
        + review_risk_bonus
        + reprocess_bonus
        + escalation_bonus
        + rejection_bonus
        + conflict_bonus
    )


async def reconcile_asset_review_decisions(db: AsyncIOMotorDatabase, project_id: str) -> None:
    """Authoritative decision router reconciliation.
    
    Re-evaluates image confidence (arithmetic mean of valid AI annotation confidences per asset)
    against the project's configured threshold (default 0.95).
    Creates/updates persisted HITL tasks in MongoDB decisions collection and updates asset review_status.
    """
    from app.services.decisions import DecisionService
    from app.errors import NotFoundError, ValidationAppError
    from app.logging import get_logger

    logger = get_logger(__name__)

    proj_doc = await db["projects"].find_one({"id": project_id})
    if not proj_doc:
        raise NotFoundError("Project", project_id)
        
    project = MongoDoc(proj_doc)
    policy = project.get("quality_policy") or {}

    threshold_val = policy.get("confidence_threshold") or policy.get("auto_approve_threshold")
    sample_rate_val = policy.get("qc_sample_rate") or policy.get("sample_rate")

    if threshold_val is None:
        threshold = 0.95
    else:
        try:
            threshold = float(threshold_val)
        except (ValueError, TypeError):
            raise ValidationAppError(f"Invalid confidence_threshold configuration for project {project_id}: {threshold_val}")

    if sample_rate_val is None:
        sample_rate = 0.05
    else:
        try:
            sample_rate = float(sample_rate_val)
        except (ValueError, TypeError):
            raise ValidationAppError(f"Invalid qc_sample_rate configuration for project {project_id}: {sample_rate_val}")

    logger.info(
        "project_hitl_config_stage",
        project_id=project_id,
        configured_threshold=threshold,
        configured_qc_sample_rate=sample_rate,
    )

    assets_cursor = db["assets"].find({"project_id": project_id, "status": {"$ne": "deleted"}})
    assets = [MongoDoc(d) async for d in assets_cursor]
    if not assets:
        logger.info("reconcile_no_assets_found", project_id=project_id)
        return
        
    asset_ids = [a.id for a in assets]
    ai_anns_cursor = db["annotations"].find({
        "asset_id": {"$in": asset_ids},
        "source": {"$nin": [AnnotationSource.HUMAN.value, AnnotationSource.HUMAN_MODIFIED.value]},
    })
    ai_annotations = [MongoDoc(d) async for d in ai_anns_cursor]
    
    ai_anns_by_asset: dict[str, list[MongoDoc]] = defaultdict(list)
    for ann in ai_annotations:
        ai_anns_by_asset[ann.get("asset_id")].append(ann)

    decision_svc = DecisionService(db)
        
    logger.info("hitl_routing_started", project_id=project_id, asset_count=len(assets))
    for asset in assets:
        human_statuses = {
            ReviewStatus.HUMAN_APPROVED.value,
            ReviewStatus.HUMAN_MODIFIED_APPROVED.value,
            ReviewStatus.HUMAN_REJECTED.value,
            ReviewStatus.REPROCESS_REQUIRED.value,
            ReviewStatus.FINAL_APPROVED.value,
        }
        review_reason = asset.get("review_reason") or ""
        review_status = asset.get("review_status")
        if review_status in human_statuses or "Reviewed by human" in review_reason:
            continue
            
        anns = ai_anns_by_asset.get(asset.id, [])
        valid_confs = valid_ai_object_confidences(anns)
        raw_confidences = [float(a.get("confidence")) for a in anns if a.get("confidence") is not None]

        if valid_confs:
            img_mean = calculate_image_confidence(anns)
            assert img_mean is not None
        else:
            # Low confidence / no detections -> route to Human Annotator
            img_mean = 0.34 if anns else 0.0

        logger.info(
            "ai_annotation_predictions_stage",
            asset_id=asset.id,
            prediction_count=len(anns),
            raw_confidences=raw_confidences,
            aggregate_confidence=img_mean,
            configured_threshold=threshold,
            configured_qc_sample_rate=sample_rate,
        )

        # Route and persist HITL task in MongoDB
        await decision_svc.create_or_route_hitl_task(
            project_id=project_id,
            asset_id=asset.id,
            original_ai_confidence=img_mean,
            predictions=[dict(a) for a in anns],
        )

    logger.info("hitl_routing_completed", project_id=project_id, asset_count=len(assets))


async def refresh_review_priorities(db: AsyncIOMotorDatabase, project_id: str) -> None:
    await reconcile_asset_review_decisions(db, project_id)
    assets_cursor = db["assets"].find({"project_id": project_id})
    assets = [MongoDoc(d) async for d in assets_cursor]
    if not assets:
        return

    reviewed_by_cluster: dict[int | None, int] = defaultdict(int)
    total_by_cluster: dict[int | None, int] = defaultdict(int)
    reviewed_count = 0
    for a in assets:
        cid = a.get("cluster_id")
        total_by_cluster[cid] += 1
        r_status = a.get("review_status")
        if r_status in {ReviewStatus.APPROVED.value, ReviewStatus.FLAGGED.value}:
            reviewed_by_cluster[cid] += 1
            reviewed_count += 1

    # Boost assets that have AI annotations flagged review_risk in provenance
    risk_by_asset: dict[str, float] = defaultdict(float)
    asset_ids = [a.id for a in assets]
    if asset_ids:
        ann_cursor = db["annotations"].find({
            "asset_id": {"$in": asset_ids},
            "source": AnnotationSource.AI.value,
        })
        ann_rows = [MongoDoc(d) async for d in ann_cursor]
        for ann in ann_rows:
            prov = ann.get("provenance") or {}
            if prov.get("review_risk"):
                risk_by_asset[ann.get("asset_id")] += 0.15

    for a in assets:
        r_status = a.get("review_status")
        if r_status not in {
            ReviewStatus.REVIEW.value,
            ReviewStatus.HUMAN_REVIEW.value,
            ReviewStatus.PENDING.value,
            ReviewStatus.FLAGGED.value,
            ReviewStatus.REPROCESS_REQUIRED.value,
            ReviewStatus.ESCALATED.value,
            ReviewStatus.SECOND_REVIEW.value,
        }:
            # Keep approved lower in queue
            await db["assets"].update_one({"id": a.id}, {"$set": {"review_priority": -1.0}})
            continue
        p_score = score_asset(
            a,
            reviewed_by_cluster=reviewed_by_cluster,
            total_by_cluster=total_by_cluster,
            reviewed_count=reviewed_count,
            total_count=len(assets),
            review_risk_bonus=min(0.45, risk_by_asset.get(a.id, 0.0)),
        )
        await db["assets"].update_one({"id": a.id}, {"$set": {"review_priority": p_score}})


def priority_debug(asset: MongoDoc) -> dict[str, Any]:
    return {
        "asset_id": asset.get("id"),
        "review_priority": asset.get("review_priority"),
        "mean_confidence": asset.get("mean_confidence"),
        "cluster_id": asset.get("cluster_id"),
        "is_outlier": bool(asset.get("is_outlier", False)),
    }

