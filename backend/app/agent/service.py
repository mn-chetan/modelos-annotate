"""Agent orchestration service with budgets and persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.agent.client import AgentBudgetExceeded, AgentUsage, VertexAgentClient
from app.agent.fake import FakeAgentClient
from app.agent.normalize import normalize_project_plan_response
from app.agent.pricing import PRICING_VERSION, estimate_cost_usd
from app.config import Settings
from app.db.models import MongoDoc
from app.domain.enums import AgentRequestKind, PlanStatus, ProjectStatus
from app.errors import ModelUnavailableError, NotFoundError, ValidationAppError
from app.logging import get_logger

logger = get_logger(__name__)


def create_agent_client(settings: Settings, *, force_fake: bool = False) -> Any:
    if force_fake or not settings.agent_enabled:
        return FakeAgentClient()
    if getattr(settings, "is_azure_agent", False):
        from app.agent.client import AzureOpenAIAgentClient
        return AzureOpenAIAgentClient(settings)
    return VertexAgentClient(settings)


class AgentService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        client: Any,
    ) -> None:
        self.db = db
        self.settings = settings
        self.client = client

    async def _budget_guard(self, project_id: str) -> None:
        req_count = await self.db["agent_requests"].count_documents({"project_id": project_id})
        if self.settings.agent_request_cap and req_count >= self.settings.agent_request_cap:
            raise AgentBudgetExceeded(
                "Agent request cap reached for this project",
                details={
                    "project_id": project_id,
                    "request_cap": self.settings.agent_request_cap,
                    "requests_used": req_count,
                    "next_step": "Increase AGENT_REQUEST_CAP or start a new project",
                },
            )

        agg = self.db["usage_events"].aggregate([
            {"$match": {"project_id": project_id, "kind": "llm"}},
            {"$group": {"_id": None, "total": {"$sum": "$cost_usd"}}},
        ])
        spent_total = 0.0
        async for item in agg:
            spent_total = float(item.get("total", 0.0))

        if self.settings.agent_budget_usd and spent_total >= self.settings.agent_budget_usd:
            raise AgentBudgetExceeded(
                "Agent budget reached for this project",
                details={
                    "project_id": project_id,
                    "budget_usd": self.settings.agent_budget_usd,
                    "spent_usd_estimate": spent_total,
                    "next_step": "Increase AGENT_BUDGET_USD or continue without further agent calls",
                },
            )

    async def _persist_usage(
        self,
        *,
        project_id: str,
        kind: str,
        usage: AgentUsage,
        context: dict[str, Any],
        response: dict[str, Any],
        clarifying: list[Any] | None = None,
    ) -> MongoDoc:
        cost = estimate_cost_usd(tokens_in=usage.tokens_in, tokens_out=usage.tokens_out)
        now = datetime.now(UTC)
        row = MongoDoc({
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "kind": kind,
            "model_id": usage.model_id,
            "request_context": context,
            "response_payload": response,
            "clarifying_questions": clarifying or [],
            "tokens_in": usage.tokens_in,
            "tokens_out": usage.tokens_out,
            "cost_usd_estimate": cost,
            "pricing_version": PRICING_VERSION,
            "created_at": now,
        })
        await self.db["agent_requests"].insert_one(dict(row))
        await self.db["usage_events"].insert_one({
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "kind": "llm",
            "model_id": usage.model_id,
            "tokens_in": usage.tokens_in,
            "tokens_out": usage.tokens_out,
            "cost_usd": cost,
            "detection_count": 0,
            "duration_ms": 0,
            "created_at": now,
        })
        return row

    async def run_intake(self, project_id: str) -> dict[str, Any]:
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        project = MongoDoc(project_doc)
        await self._budget_guard(project_id)

        context = {
            "name": project.get("name"),
            "goal": project.get("goal"),
            "task_type": project.get("task_type"),
            "label_strategy": project.get("label_strategy"),
            "labels": project.get("labels"),
            "images_sent": False,
        }
        if not getattr(self.client, "available", True):
            reason = getattr(self.client, "reason", "unknown")
            logger.error("vertex_agent_unavailable_in_intake", project_id=project_id, reason=reason)
            raise ModelUnavailableError(
                f"Vertex AI agent is unavailable: {reason}",
                details={
                    "project_id": project_id,
                    "reason": reason,
                    "model": getattr(self.client, "model_id", "gemini-3.6-flash"),
                    "auth": "ADC",
                },
            )

        result, usage = self.client.intake(
            name=project.get("name"),
            goal=project.get("goal"),
            task_type=project.get("task_type"),
            strategy=project.get("label_strategy"),
            labels=list(project.get("labels") or []),
            modality=project.get("modality") or "image",
        )

        proj_updates: dict[str, Any] = {"status": ProjectStatus.DRAFT.value, "updated_at": datetime.now(UTC)}
        if result.proposed_labels:
            proj_updates["labels"] = result.proposed_labels
        if result.label_strategy:
            proj_updates["label_strategy"] = result.label_strategy
        await self.db["projects"].update_one({"id": project_id}, {"$set": proj_updates})

        plan = await self._get_or_create_plan(project_id)
        p_status = PlanStatus.AWAITING_CLARIFICATION.value if result.needs_clarification else PlanStatus.PENDING_APPROVAL.value
        plan_updates = {
            "summary": result.summary,
            "taxonomy": result.proposed_labels,
            "label_strategy": result.label_strategy,
            "workflow": [m.model_dump() for m in result.recommended_models],
            "risks": result.risks,
            "rationale": result.review_policy_notes,
            "ambiguities": [],
            "review_policy": {},
            "clarifications": {},
            "agent_model_id": usage.model_id,
            "confidence": result.confidence,
            "status": p_status,
            "updated_at": datetime.now(UTC),
        }
        await self.db["project_plans"].update_one({"id": plan.id}, {"$set": plan_updates})

        req = await self._persist_usage(
            project_id=project_id,
            kind=AgentRequestKind.INTAKE.value,
            usage=usage,
            context=context,
            response=result.model_dump(),
            clarifying=[q.model_dump() for q in result.clarifying_questions],
        )
        logger.info(
            "agent_intake_complete",
            project_id=project_id,
            agent_request_id=req.id,
            needs_clarification=result.needs_clarification,
            model=usage.model_id,
        )
        return await self.get_plan(project_id)

    async def apply_clarifications(
        self, project_id: str, answers: dict[str, str]
    ) -> dict[str, Any]:
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        project = MongoDoc(project_doc)
        if not answers:
            raise ValidationAppError("Clarification answers are required")
        await self._budget_guard(project_id)

        plan = await self._get_or_create_plan(project_id)
        merged = dict(plan.get("clarifications") or {})
        merged.update(answers)

        if not getattr(self.client, "available", True):
            reason = getattr(self.client, "reason", "unknown")
            logger.error("vertex_agent_unavailable_in_clarify", project_id=project_id, reason=reason)
            raise ModelUnavailableError(
                f"Vertex AI agent is unavailable: {reason}",
                details={
                    "project_id": project_id,
                    "reason": reason,
                    "model": getattr(self.client, "model_id", "gemini-3.6-flash"),
                    "auth": "ADC",
                },
            )

        payload, usage = self.client.plan(
            name=project.get("name"),
            goal=project.get("goal"),
            task_type=project.get("task_type"),
            strategy=project.get("label_strategy"),
            labels=list(project.get("labels") or []),
            clarifications=merged,
            intake_summary=plan.get("summary"),
            modality=project.get("modality") or "image",
        )
        plan_updates = self._apply_plan_payload(payload, usage.model_id)
        plan_updates["clarifications"] = merged
        plan_updates["status"] = PlanStatus.PENDING_APPROVAL.value
        plan_updates["updated_at"] = datetime.now(UTC)

        await self.db["project_plans"].update_one({"id": plan.id}, {"$set": plan_updates})
        if payload.taxonomy:
            await self.db["projects"].update_one(
                {"id": project_id},
                {"$set": {"labels": payload.taxonomy, "updated_at": datetime.now(UTC)}}
            )

        await self._persist_usage(
            project_id=project_id,
            kind=AgentRequestKind.CLARIFY.value,
            usage=usage,
            context={"clarifications": answers, "images_sent": False},
            response=payload.model_dump(),
        )
        return await self.get_plan(project_id)

    async def generate_plan(self, project_id: str) -> dict[str, Any]:
        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        project = MongoDoc(project_doc)
        await self._budget_guard(project_id)
        plan = await self._get_or_create_plan(project_id)
        if not getattr(self.client, "available", True):
            reason = getattr(self.client, "reason", "unknown")
            logger.error("vertex_agent_unavailable_in_plan", project_id=project_id, reason=reason)
            raise ModelUnavailableError(
                f"Vertex AI agent is unavailable: {reason}",
                details={
                    "project_id": project_id,
                    "reason": reason,
                    "model": getattr(self.client, "model_id", "gemini-3.6-flash"),
                    "auth": "ADC",
                },
            )

        payload, usage = self.client.plan(
            name=project.get("name"),
            goal=project.get("goal"),
            task_type=project.get("task_type"),
            strategy=project.get("label_strategy"),
            labels=list(project.get("labels") or []),
            clarifications=dict(plan.get("clarifications") or {}),
            intake_summary=plan.get("summary"),
        )
        plan_updates = self._apply_plan_payload(payload, usage.model_id)
        plan_updates["status"] = PlanStatus.PENDING_APPROVAL.value
        plan_updates["updated_at"] = datetime.now(UTC)
        await self.db["project_plans"].update_one({"id": plan.id}, {"$set": plan_updates})

        if payload.taxonomy:
            await self.db["projects"].update_one(
                {"id": project_id},
                {"$set": {"labels": payload.taxonomy, "updated_at": datetime.now(UTC)}}
            )

        await self._persist_usage(
            project_id=project_id,
            kind=AgentRequestKind.PLAN.value,
            usage=usage,
            context={"images_sent": False},
            response=payload.model_dump(),
        )
        return await self.get_plan(project_id)

    async def approve_plan(self, project_id: str) -> dict[str, Any]:
        logger.info("ontology_approval_started", project_id=project_id)

        project_doc = await self.db["projects"].find_one({"id": project_id})
        if project_doc is None:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        project = MongoDoc(project_doc)

        plan_doc = await self.db["project_plans"].find_one({"project_id": project_id})
        now = datetime.now(UTC)
        if plan_doc is None:
            plan_id = str(uuid.uuid4())
            plan = MongoDoc({
                "id": plan_id,
                "project_id": project_id,
                "workflow": [{"step": "default"}],
                "status": PlanStatus.APPROVED.value,
                "approved_at": now,
                "created_at": now,
                "updated_at": now,
            })
            await self.db["project_plans"].insert_one(dict(plan))
        else:
            plan = MongoDoc(plan_doc)
            await self.db["project_plans"].update_one(
                {"id": plan.id},
                {"$set": {
                    "status": PlanStatus.APPROVED.value,
                    "approved_at": now,
                    "updated_at": now,
                }}
            )

        proj_updates: dict[str, Any] = {
            "status": ProjectStatus.READY.value,
            "ontology_status": "approved",
            "updated_at": now,
        }
        labels = plan.get("taxonomy") or project.get("labels")
        if plan.get("taxonomy"):
            proj_updates["labels"] = plan.get("taxonomy")

        ontology = [
            {**entry, "approved": True, "status": "approved"}
            if isinstance(entry, dict)
            else {"name": str(entry), "approved": True, "status": "approved"}
            for entry in (project.get("label_ontology") or [])
        ]
        if not ontology and labels:
            import re
            from app.domain.color import color_for_class
            ontology = [
                {
                    "id": f"cpt_{re.sub(r'[^a-z0-9_]', '_', str(l).strip().lower())}",
                    "name": str(l).strip(),
                    "approved": True,
                    "status": "approved",
                    "color": color_for_class(str(l).strip()),
                }
                for l in labels
                if str(l).strip()
            ]

        proj_updates["label_ontology"] = ontology
        if plan.get("review_policy"):
            proj_updates["quality_policy"] = plan.get("review_policy")

        await self.db["projects"].update_one({"id": project_id}, {"$set": proj_updates})
        logger.info("ontology_approval_complete", project_id=project_id, ontology_status="approved")
        logger.info("ontology_approved", project_id=project_id, plan_id=plan.id)
        logger.info("agent_plan_approved", project_id=project_id, plan_id=plan.id)
        return await self.get_plan(project_id)

    async def get_plan(self, project_id: str) -> dict[str, Any]:
        plan_doc = await self.db["project_plans"].find_one({"project_id": project_id})
        if plan_doc is None:
            raise NotFoundError("Plan not found", details={"project_id": project_id})
        normalized_plan = normalize_project_plan_response(dict(plan_doc))
        plan = MongoDoc(normalized_plan)

        requests = [
            MongoDoc(d)
            for d in await self.db["agent_requests"]
            .find({"project_id": project_id})
            .sort("created_at", -1)
            .to_list(length=1)
        ]
        latest_qs = requests[0] if requests else None

        response = {
            "id": plan.get("id"),
            "project_id": plan.get("project_id"),
            "status": plan.get("status"),
            "summary": plan.get("summary"),
            "taxonomy": plan.get("taxonomy"),
            "label_strategy": plan.get("label_strategy"),
            "workflow": plan.get("workflow"),
            "ambiguities": plan.get("ambiguities"),
            "risks": plan.get("risks"),
            "review_policy": plan.get("review_policy"),
            "rationale": plan.get("rationale"),
            "clarifications": plan.get("clarifications"),
            "clarifying_questions": (latest_qs.get("clarifying_questions") if latest_qs else []),
            "agent_model_id": plan.get("agent_model_id"),
            "confidence": plan.get("confidence"),
            "approved_at": plan.get("approved_at"),
            "created_at": plan.get("created_at"),
            "updated_at": plan.get("updated_at"),
            "pricing_version": PRICING_VERSION,
        }
        normalized_response = normalize_project_plan_response(response)
        logger.info("agent_plan_validation_success", project_id=project_id, source="firebase")
        return normalized_response

    def _apply_plan_payload(self, payload: Any, model_id: str) -> dict[str, Any]:
        return {
            "summary": payload.summary,
            "taxonomy": payload.taxonomy,
            "label_strategy": payload.label_strategy,
            "workflow": [m.model_dump() for m in payload.workflow],
            "ambiguities": payload.ambiguities,
            "risks": payload.risks,
            "review_policy": payload.review_policy,
            "clarifications": payload.clarifications,
            "rationale": payload.rationale,
            "agent_model_id": model_id,
        }

    async def _get_or_create_plan(self, project_id: str) -> MongoDoc:
        plan_doc = await self.db["project_plans"].find_one({"project_id": project_id})
        if plan_doc is None:
            now = datetime.now(UTC)
            plan = MongoDoc({
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "created_at": now,
                "updated_at": now,
            })
            await self.db["project_plans"].insert_one(dict(plan))
            return plan
        return MongoDoc(plan_doc)

