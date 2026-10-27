from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorCollection

from app.schemas.analysis import AnalysisRecord, WorkflowAuditEvent, WorkflowStatus, WorkflowVersion


class AnalysisRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def create(self, analysis: AnalysisRecord) -> dict[str, Any]:
        document = analysis.model_dump(mode="json")
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def find_by_assessment_name(self, assessment_name: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"assessment_name": assessment_name})

    async def list_unapproved_qc_assessments(self) -> list[dict[str, Any]]:
        cursor = self.collection.find(
            {"status": {"$ne": "COMPLETED"}},
            {"_id": 0, "analysis_id": 1, "assessment_name": 1},
        )
        documents = await cursor.to_list(length=None)
        return [
            {
                "analysis_id": document["analysis_id"],
                "assessment_name": document["assessment_name"],
            }
            for document in documents
            if document.get("analysis_id") is not None and document.get("assessment_name")
        ]

    async def find_by_analysis_id(self, analysis_id: UUID) -> dict[str, Any] | None:
        return await self.collection.find_one({"analysis_id": str(analysis_id)})

    async def update_workflow(
        self,
        analysis_id: UUID,
        *,
        status: WorkflowStatus,
        updated_by: str,
        reviewer_role: str,
        result: dict[str, Any] | None = None,
        comments: str | None = None,
        approval_decision: str | None = None,
        rejection_reason: str | None = None,
        updated_fields: list[str] | None = None,
        assigned_reviewer_role: str | None = None,
        assigned_reviewer_name: str | None = None,
        preserve_human_review_result: bool = False,
    ) -> dict[str, Any] | None:
        document = await self.find_by_analysis_id(analysis_id)
        if document is None:
            return None

        audit_trail = list(document.get("audit_trail", []))
        versions = list(document.get("versions", []))
        now = datetime.utcnow()
        previous_status = document.get("status")

        if result is not None:
            if not preserve_human_review_result:
                document["human_review_result"] = result
            else:
                document["qc_result"] = result

        if comments:
            reviewer_comments = list(document.get("reviewer_comments", []))
            reviewer_comments.append(comments)
            document["reviewer_comments"] = reviewer_comments

        if assigned_reviewer_role is not None:
            document["assigned_reviewer_role"] = assigned_reviewer_role
        if assigned_reviewer_name is not None:
            document["assigned_reviewer_name"] = assigned_reviewer_name

        document["status"] = status
        document["updated_at"] = now

        audit_trail.append(
            WorkflowAuditEvent(
                action=(
                    "HUMAN_REVIEW_SUBMITTED"
                    if reviewer_role == "HUMAN_REVIEWER"
                    else "QC_APPROVED"
                    if status == "COMPLETED"
                    else "QC_REJECTED"
                    if status == "HUMAN_REVIEW"
                    else "ROUTED_TO_QC"
                ),
                reviewer_name=updated_by,
                reviewer_role=reviewer_role,
                status_before=previous_status,
                status_after=status,
                updated_fields=updated_fields or [],
                approval_decision=approval_decision,
                rejection_reason=rejection_reason,
                comments=comments,
            ).model_dump(mode="json")
        )

        versions.append(
            WorkflowVersion(
                version=len(versions) + 1,
                status=status,
                updated_by=updated_by,
                reviewer_role=reviewer_role,
                data=result or document.get("result", {}),
                comments=comments,
            ).model_dump(mode="json")
        )

        document["audit_trail"] = audit_trail
        document["versions"] = versions

        await self.collection.update_one(
            {"analysis_id": str(analysis_id)},
            {"$set": document},
        )
        return document
