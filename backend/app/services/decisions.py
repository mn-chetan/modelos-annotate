"""Aggregated Decision and Human-in-the-Loop (HITL) Workflow Service backed by MongoDB."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.db.models import MongoDoc, to_mongo_doc
from app.domain.enums import AnnotationSource, DefectCategory, HumanRole, ReviewStatus
from app.errors import NotFoundError, ValidationAppError
from app.logging import get_logger
from app.services.quality_validation import calculate_box_iou
from app.services.review_priority import refresh_review_priorities

logger = get_logger(__name__)


def compute_annotation_deltas(
    original_ai_outputs: list[dict[str, Any]],
    final_approved_outputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute actual annotation deltas between original AI predictions and final approved output."""
    deltas: list[dict[str, Any]] = []

    ai_matched = set()
    approved_matched = set()

    for i, ai_ann in enumerate(original_ai_outputs):
        ai_label = str(ai_ann.get("label") or "").strip().lower()
        ai_bbox = ai_ann.get("bbox") or {}

        best_match_idx = None
        best_iou = 0.0

        for j, app_ann in enumerate(final_approved_outputs):
            if j in approved_matched:
                continue
            app_bbox = app_ann.get("bbox") or {}
            iou = calculate_box_iou(ai_bbox, app_bbox)
            if iou > best_iou:
                best_iou = iou
                best_match_idx = j

        if best_match_idx is not None and best_iou >= 0.3:
            ai_matched.add(i)
            approved_matched.add(best_match_idx)
            app_ann = final_approved_outputs[best_match_idx]
            app_label = str(app_ann.get("label") or "").strip().lower()

            if ai_label != app_label:
                deltas.append({
                    "id": str(uuid.uuid4()),
                    "delta_type": "label_correction",
                    "original_value": ai_ann.get("label"),
                    "corrected_value": app_ann.get("label"),
                    "ai_annotation": ai_ann,
                    "final_annotation": app_ann,
                })

            if best_iou < 0.95:
                deltas.append({
                    "id": str(uuid.uuid4()),
                    "delta_type": "bbox_correction",
                    "original_value": ai_bbox,
                    "corrected_value": app_ann.get("bbox"),
                    "iou": best_iou,
                    "ai_annotation": ai_ann,
                    "final_annotation": app_ann,
                })
        else:
            deltas.append({
                "id": str(uuid.uuid4()),
                "delta_type": "removed_annotation",
                "original_value": ai_ann,
                "corrected_value": None,
                "ai_annotation": ai_ann,
            })

    for j, app_ann in enumerate(final_approved_outputs):
        if j not in approved_matched:
            deltas.append({
                "id": str(uuid.uuid4()),
                "delta_type": "added_annotation",
                "original_value": None,
                "corrected_value": app_ann,
                "final_annotation": app_ann,
            })

    return deltas


class DecisionService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def get_project_hitl_config(self, project_id: str) -> dict[str, Any]:
        """Fetch project HITL settings (confidence threshold = 0.95 default, qc_sample_rate = 0.05 default)."""
        proj = await self.db["projects"].find_one({"id": project_id})
        if not proj:
            return {"confidence_threshold": 0.95, "qc_sample_rate": 0.05, "annotation_guidelines": "", "labels": []}
        policy = proj.get("quality_policy") or {}
        thresh = float(policy.get("confidence_threshold") or proj.get("confidence_threshold") or 0.95)
        sample_rate = float(policy.get("qc_sample_rate") or proj.get("high_confidence_qc_sample_rate") or 0.02)
        sample_rate = max(0.02, min(0.05, sample_rate))
        return {
            "project_id": project_id,
            "confidence_threshold": thresh,
            "qc_sample_rate": sample_rate,
            "annotation_guidelines": proj.get("annotation_guidelines", ""),
            "labels": proj.get("labels", []),
            "ontology": proj.get("labels", []),
        }

    async def update_project_hitl_config(
        self,
        project_id: str,
        confidence_threshold: float | None = None,
        qc_sample_rate: float | None = None,
        annotation_guidelines: str | None = None,
        ontology: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update project HITL configuration with validation on bounds."""
        updates: dict[str, Any] = {}
        policy_updates: dict[str, Any] = {}

        if confidence_threshold is not None:
            thresh = float(confidence_threshold)
            thresh = max(0.0, min(1.0, thresh))
            updates["confidence_threshold"] = thresh
            policy_updates["confidence_threshold"] = thresh

        if qc_sample_rate is not None:
            sr = float(qc_sample_rate)
            sr = max(0.02, min(0.05, sr))
            updates["high_confidence_qc_sample_rate"] = sr
            policy_updates["qc_sample_rate"] = sr

        if annotation_guidelines is not None:
            updates["annotation_guidelines"] = annotation_guidelines

        if ontology is not None:
            updates["labels"] = ontology

        if policy_updates:
            for k, v in policy_updates.items():
                updates[f"quality_policy.{k}"] = v

        if updates:
            from datetime import UTC, datetime
            updates["updated_at"] = datetime.now(UTC)
            await self.db["projects"].update_one({"id": project_id}, {"$set": updates})

        return await self.get_project_hitl_config(project_id)

    async def list_open(self, project_id: str) -> list[dict[str, Any]]:
        cursor = self.db["decisions"].find({"project_id": project_id}).sort("created_at", -1)
        docs = [MongoDoc(d) async for d in cursor]
        return [self._out(r) for r in docs]

    async def list_by_role(self, project_id: str, role: str) -> list[dict[str, Any]]:
        """List queue items filtered strictly by human role."""
        if role == HumanRole.HUMAN_ANNOTATOR.value or role == "HUMAN_ANNOTATOR":
            statuses = [
                ReviewStatus.HUMAN_REVIEW_REQUIRED.value,
                ReviewStatus.IN_HUMAN_REVIEW.value,
                ReviewStatus.HUMAN_REWORK_REQUIRED.value,
                "human_review",
                "pending",
                "rework",
            ]
            # Include persisted human-review history. Once submitted, a task
            # moves to QC/final states and must remain visible to the existing
            # endpoint used by the Human Reviewed counter.
            cursor = self.db["decisions"].find({"project_id": project_id}).sort("created_at", -1)
            all_docs = [MongoDoc(d) async for d in cursor]
            docs = [
                doc for doc in all_docs
                if doc.get("status") in statuses
                or str(doc.get("audit_source") or "").upper() == "HUMAN_REVIEW"
                or any(
                    str(revision.get("source") or "").upper() in {"HUMAN", "HUMAN_MODIFIED"}
                    for revision in (doc.get("revisions") or [])
                    if isinstance(revision, dict)
                )
            ]

            # Text analysis persists the routing state on the asset. Older
            # text runs may not have a matching decision document, so hydrate
            # those review-only assets into the HITL queue. Auto-approved
            # assets are deliberately excluded by the status filter.
            queued_asset_ids = {str(doc.get("asset_id")) for doc in docs if doc.get("asset_id")}
            asset_cursor = self.db["assets"].find({
                "project_id": project_id,
                "review_status": {"$in": statuses},
            })
            async for asset in asset_cursor:
                asset_id = str(asset.get("id") or "")
                if not asset_id or asset_id in queued_asset_ids:
                    continue
                annotation_cursor = self.db["annotations"].find({"asset_id": asset_id}).sort("created_at", 1)
                predictions = [to_mongo_doc(annotation) for annotation in await annotation_cursor.to_list(length=500)]
                now = datetime.now(UTC)
                task_doc = {
                    "id": f"hitl_{asset_id}",
                    "project_id": project_id,
                    "asset_id": asset_id,
                    "status": asset.get("review_status"),
                    "workflow_state": asset.get("review_status"),
                    "role": HumanRole.HUMAN_ANNOTATOR.value,
                    "assigned_role": HumanRole.HUMAN_ANNOTATOR.value,
                    "decision_type": "low_confidence",
                    "confidence": asset.get("mean_confidence"),
                    "original_ai_confidence": asset.get("mean_confidence"),
                    "sample_rate": 0.0,
                    "sampled": False,
                    "audit_source": "HUMAN_REVIEW",
                    "question": "Low confidence - Human Review Required",
                    "original_ai_output": predictions,
                    "current_annotations": predictions,
                    "created_at": asset.get("created_at") or now,
                    "updated_at": now,
                    "revisions": [],
                }
                await self.db["decisions"].update_one(
                    {"asset_id": asset_id},
                    {"$set": task_doc},
                    upsert=True,
                )
                docs.append(MongoDoc(task_doc))
                queued_asset_ids.add(asset_id)
        elif role == HumanRole.QUALITY_AUDITOR.value or role == "QUALITY_AUDITOR":
            statuses = [
                ReviewStatus.QUALITY_AUDIT_REQUIRED.value,
                ReviewStatus.HUMAN_REVIEW_COMPLETED.value,
                ReviewStatus.HIGH_CONFIDENCE_QC_SAMPLE.value,
                "audit",
                "qc_sample",
            ]
            cursor = self.db["decisions"].find({
                "project_id": project_id,
                "status": {"$in": statuses},
            }).sort("created_at", -1)
            docs = [MongoDoc(d) async for d in cursor]
        else:
            # PROJECT_MANAGER or ALL
            cursor = self.db["decisions"].find({"project_id": project_id}).sort("created_at", -1)
            docs = [MongoDoc(d) async for d in cursor]
            return [self._out(r) for r in docs]
        return [self._out(r) for r in docs]

    async def create_or_route_hitl_task(
        self,
        project_id: str,
        asset_id: str,
        original_ai_confidence: float,
        predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Perform backend confidence routing and random sampling according to project config."""
        config = await self.get_project_hitl_config(project_id)
        threshold = config["confidence_threshold"]  # 0.95
        sample_rate = config["qc_sample_rate"]      # 0.02 - 0.05

        existing = await self.db["decisions"].find_one({"asset_id": asset_id})
        if existing and existing.get("status") in {
            ReviewStatus.HUMAN_APPROVED.value,
            ReviewStatus.HUMAN_MODIFIED_APPROVED.value,
            ReviewStatus.HUMAN_REJECTED.value,
            ReviewStatus.REPROCESS_REQUIRED.value,
            ReviewStatus.FINAL_APPROVED.value,
            ReviewStatus.QUALITY_AUDIT_REQUIRED.value,
            ReviewStatus.HUMAN_REVIEW_COMPLETED.value,
        }:
            logger.info("hitl_routing_skipped_existing_active", asset_id=asset_id, status=existing.get("status"))
            return self._out(MongoDoc(existing))

        now = datetime.now(UTC)
        task_id = existing.get("id") if (existing and existing.get("id")) else f"hitl_{str(uuid.uuid4())[:8]}"

        raw_confidences = [float(p.get("confidence")) for p in predictions if p.get("confidence") is not None]

        if original_ai_confidence < threshold:
            status = ReviewStatus.HUMAN_REVIEW_REQUIRED.value
            role = HumanRole.HUMAN_ANNOTATOR.value
            audit_source = "HUMAN_REVIEW"
            sampled = False
            question = f"Low confidence ({round(original_ai_confidence, 2)}) - Human Review Required"
            decision_type = "low_confidence"
        else:
            # Perform random sampling in backend (2%-5%)
            sampled = random.random() < sample_rate
            if sampled:
                status = ReviewStatus.QUALITY_AUDIT_REQUIRED.value
                role = HumanRole.QUALITY_AUDITOR.value
                audit_source = "HIGH_CONFIDENCE_SAMPLE"
                question = f"High confidence ({round(original_ai_confidence, 2)}) - Random Sampled for Audit ({round(sample_rate * 100, 1)}%)"
                decision_type = "qc_sample"
            else:
                status = ReviewStatus.HIGH_CONFIDENCE_AUTO_PASS.value
                role = "SYSTEM"
                audit_source = None
                question = f"High confidence ({round(original_ai_confidence, 2)}) - Auto Pass Approved"
                decision_type = "auto_pass"

        logger.info(
            "hitl_confidence_routing_stage",
            asset_id=asset_id,
            prediction_count=len(predictions),
            raw_confidences=raw_confidences,
            aggregate_confidence=original_ai_confidence,
            configured_threshold=threshold,
            configured_qc_sample_rate=sample_rate,
            routing_decision=status,
            assigned_role=role,
            workflow_state=status,
            hitl_task_id=task_id,
        )

        doc = {
            "id": task_id,
            "project_id": project_id,
            "asset_id": asset_id,
            "status": status,
            "workflow_state": status,
            "role": role,
            "assigned_role": role,
            "decision_type": decision_type,
            "confidence": original_ai_confidence,
            "original_ai_confidence": original_ai_confidence,
            "sample_rate": sample_rate,
            "sampled": sampled,
            "audit_source": audit_source,
            "question": question,
            "original_ai_output": predictions,
            "current_annotations": predictions,
            "rework_feedback": None,
            "defect_category": None,
            "auditor_id": None,
            "created_at": now,
            "updated_at": now,
            "revisions": [
                {
                    "revision": 1,
                    "status": status,
                    "source": "AI",
                    "timestamp": now.isoformat(),
                    "annotations": predictions,
                }
            ],
        }

        await self.db["decisions"].update_one(
            {"asset_id": asset_id},
            {"$set": doc},
            upsert=True,
        )

        # Update asset review status to match HITL task status
        await self.db["assets"].update_one(
            {"id": asset_id},
            {"$set": {
                "review_status": status,
                "mean_confidence": original_ai_confidence,
                "updated_at": now,
            }}
        )

        return self._out(MongoDoc(doc))

    async def submit_human_annotation(
        self,
        decision_id_or_asset_id: str,
        annotations: list[dict[str, Any]],
        annotator_id: str = "HUMAN_ANNOTATOR",
    ) -> dict[str, Any]:
        """Submit Human Annotator work. Moves task to QUALITY_AUDIT_REQUIRED."""
        now = datetime.now(UTC)
        doc = await self.db["decisions"].find_one({
            "$or": [{"id": decision_id_or_asset_id}, {"asset_id": decision_id_or_asset_id}]
        })
        if not doc:
            raise NotFoundError("HITL Task", decision_id_or_asset_id)

        task = MongoDoc(doc)
        revisions = list(task.get("revisions") or [])
        rev_num = len(revisions) + 1

        # Tag annotations with source = HUMAN or HUMAN_MODIFIED
        human_anns = []
        for ann in annotations:
            ann_copy = dict(ann)
            ann_copy["source"] = AnnotationSource.HUMAN_MODIFIED.value if ann_copy.get("source") == "ai" else AnnotationSource.HUMAN.value
            human_anns.append(ann_copy)

        revisions.append({
            "revision": rev_num,
            "status": ReviewStatus.HUMAN_REVIEW_COMPLETED.value,
            "source": "HUMAN",
            "annotator_id": annotator_id,
            "timestamp": now.isoformat(),
            "annotations": human_anns,
        })

        new_status = ReviewStatus.QUALITY_AUDIT_REQUIRED.value

        update_payload = {
            "status": new_status,
            "role": HumanRole.QUALITY_AUDITOR.value,
            "audit_source": "HUMAN_REVIEW",
            "current_annotations": human_anns,
            "revisions": revisions,
            "updated_at": now,
        }

        await self.db["decisions"].update_one({"id": task.id}, {"$set": update_payload})
        # Keep the text-analysis readback in sync with the canonical HITL
        # revision.  The review UI reads this payload, while the annotations
        # collection remains the durable annotation store.
        asset_row = await self.db["assets"].find_one({"id": task.asset_id})
        text_analysis = dict((asset_row or {}).get("text_analysis") or {})
        text_analysis["annotations"] = human_anns
        text_analysis["review_status"] = "PENDING"
        text_analysis["agent_status"] = new_status
        await self.db["assets"].update_one(
            {"id": task.asset_id},
            {"$set": {"review_status": new_status, "text_analysis": text_analysis, "updated_at": now}},
        )

        # Persist updated annotations to MongoDB annotations collection
        if task.asset_id:
            await self.db["annotations"].delete_many({"asset_id": task.asset_id})
            for ann in human_anns:
                ann_doc = dict(ann)
                ann_doc["id"] = str(uuid.uuid4())
                ann_doc["asset_id"] = task.asset_id
                await self.db["annotations"].insert_one(ann_doc)

        refreshed = await self.db["decisions"].find_one({"id": task.id})
        return self._out(MongoDoc(refreshed))

    async def resolve(self, decision_id: str, payload: dict[str, Any] | str) -> dict[str, Any]:
        """Resolve a Quality Auditor check with PASS or FAIL."""
        now = datetime.now(UTC)
        if isinstance(payload, str):
            res_str = payload.lower()
            defect_cat = None
            feedback = None
            auditor_id = "QUALITY_AUDITOR"
        else:
            res_str = (payload.get("resolution") or payload.get("answer") or "pass").lower()
            defect_cat = payload.get("defect_category")
            feedback = payload.get("feedback")
            auditor_id = payload.get("auditor_id") or "QUALITY_AUDITOR"

        row_doc = await self.db["decisions"].find_one({
            "$or": [{"id": decision_id}, {"asset_id": decision_id}]
        })
        if row_doc is None:
            raise NotFoundError("Decision", decision_id)

        row = MongoDoc(row_doc)
        revisions = list(row.get("revisions") or [])

        if res_str in {"pass", "approved", "final_approved"}:
            final_status = ReviewStatus.FINAL_APPROVED.value
            role = "SYSTEM"

            # Compute actual deltas between original AI predictions and final approved annotations
            orig_ai = list(row.get("original_ai_output") or [])
            final_approved = list(row.get("current_annotations") or [])
            deltas = compute_annotation_deltas(orig_ai, final_approved)

            # Save deltas in MongoDB
            for d in deltas:
                d["project_id"] = row.project_id
                d["asset_id"] = row.asset_id
                d["decision_id"] = row.id
                d["created_at"] = now
                await self.db["deltas"].insert_one(d)

            update_data = {
                "status": final_status,
                "role": role,
                "answer": "PASS",
                "resolved_at": now,
                "updated_at": now,
                "deltas_count": len(deltas),
            }

            await self.db["decisions"].update_one({"id": row.id}, {"$set": update_data})
            await self.db["assets"].update_one({"id": row.asset_id}, {"$set": {"review_status": final_status}})

        elif res_str in {"fail", "rework", "human_rework_required"}:
            if not defect_cat or not feedback:
                raise ValidationAppError("Defect Category and Auditor Feedback are required for FAIL decisions.")

            final_status = ReviewStatus.HUMAN_REWORK_REQUIRED.value
            role = HumanRole.HUMAN_ANNOTATOR.value

            revisions.append({
                "revision": len(revisions) + 1,
                "status": final_status,
                "source": "QUALITY_AUDITOR",
                "auditor_id": auditor_id,
                "defect_category": defect_cat,
                "feedback": feedback,
                "timestamp": now.isoformat(),
            })

            update_data = {
                "status": final_status,
                "role": role,
                "answer": "FAIL",
                "defect_category": defect_cat,
                "rework_feedback": feedback,
                "auditor_id": auditor_id,
                "audited_at": now,
                "revisions": revisions,
                "updated_at": now,
            }

            await self.db["decisions"].update_one({"id": row.id}, {"$set": update_data})
            await self.db["assets"].update_one({"id": row.asset_id}, {"$set": {"review_status": final_status}})

        else:
            raise ValidationAppError(f"Unsupported resolution action: {res_str}")

        refreshed = await self.db["decisions"].find_one({"id": row.id})
        return self._out(MongoDoc(refreshed))

    def _out(self, row: MongoDoc) -> dict[str, Any]:
        def _iso(val: Any) -> Any:
            if isinstance(val, datetime):
                return val.isoformat()
            if type(val).__name__ == "ObjectId":
                return str(val)
            if isinstance(val, dict):
                return {k: _iso(v) for k, v in val.items() if k != "_id"}
            if isinstance(val, list):
                return [_iso(v) for v in val]
            return val

        return {
            "id": row.get("id"),
            "project_id": row.get("project_id"),
            "asset_id": row.get("asset_id"),
            "status": row.get("status"),
            "role": row.get("role"),
            "decision_type": row.get("decision_type"),
            "confidence": row.get("confidence"),
            "sample_rate": row.get("sample_rate"),
            "sampled": row.get("sampled", False),
            "audit_source": row.get("audit_source"),
            "question": row.get("question"),
            "original_ai_output": _iso(row.get("original_ai_output") or []),
            "current_annotations": _iso(row.get("current_annotations") or []),
            "rework_feedback": row.get("rework_feedback"),
            "defect_category": row.get("defect_category"),
            "auditor_id": row.get("auditor_id"),
            "revisions": _iso(row.get("revisions") or []),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "resolved_at": _iso(row.get("resolved_at")),
        }
