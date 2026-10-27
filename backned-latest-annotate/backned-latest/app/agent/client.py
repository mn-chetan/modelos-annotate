"""Vertex AI Gemini client (ADC, global, configurable model id)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from pydantic import ValidationError

from app.agent.multimodal import AgentImagePart
from app.agent.normalize import normalize_ontology_payload, normalize_project_plan_response
from app.agent.schemas import IntakeAgentResult, OntologyAgentResult, ProjectPlanPayload
from app.config import Settings
from app.errors import AppError, ModelUnavailableError
from app.logging import get_logger
from app.recon.ontology import OntologyProposal, ProposedLabel

logger = get_logger(__name__)


class AgentBudgetExceeded(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="agent_budget_exceeded",
            status_code=402,
            details=details,
        )


@dataclass
class AgentUsage:
    tokens_in: int
    tokens_out: int
    model_id: str
    raw: dict[str, Any]
    images_sent: int = 0


def build_ontology_user_contents(
    recon_context: dict[str, Any],
    images: list[AgentImagePart] | None = None,
) -> Any:
    """Build Vertex `contents` for ontology proposal (string or multimodal parts).

    Pure helper so tests can assert request construction without calling Vertex.
    """
    from google.genai import types

    # Strip bulky quality maps from the text context; keep structure + sample meta.
    context = dict(recon_context)
    stats = context.get("stats")
    if isinstance(stats, dict):
        slim_stats = {
            k: v
            for k, v in stats.items()
            if k not in {"profiles", "per_asset_quality"}
        }
        context["stats"] = slim_stats

    text = json.dumps(context)
    if not images:
        return text

    parts: list[Any] = [
        types.Part.from_text(
            text=(
                "Dataset reconnaissance context (JSON). Each attached image is labeled "
                "with its asset_id so you can cite evidence_asset_ids from visual content:\n"
                f"{text}"
            )
        )
    ]
    for img in images:
        parts.append(types.Part.from_text(text=f"Image asset_id={img.asset_id}"))
        parts.append(types.Part.from_bytes(data=img.data, mime_type=img.mime_type))
    return parts


class VertexAgentClient:
    """Real Vertex Gemini client using Application Default Credentials (ADC)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.project = (
            getattr(settings, "google_cloud_project", None)
            or os.getenv("GOOGLE_CLOUD_PROJECT")
            or getattr(settings, "firebase_project_id", None)
            or "prod-y-in2300452"
        ).strip()
        self.location = (
            getattr(settings, "vertex_location", None)
            or os.getenv("VERTEX_LOCATION")
            or "global"
        ).strip()
        self.model_id = (
            getattr(settings, "vertex_agent_model", None)
            or getattr(settings, "gemini_agent_model", None)
            or os.getenv("VERTEX_AGENT_MODEL")
            or "gemini-3.6-flash"
        ).strip()
        self._client: Any | None = None
        self.available: bool = True
        self.reason: str | None = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as exc:
            self.available = False
            self.reason = "google_genai_not_installed"
            raise ModelUnavailableError(
                "google-genai is not installed",
                details={"hint": "pip install google-genai"},
            ) from exc

        if not self.project:
            self.available = False
            self.reason = "google_cloud_project_missing"
            raise ModelUnavailableError(
                "GOOGLE_CLOUD_PROJECT is required for Vertex AI with Application Default Credentials (ADC)",
                details={
                    "model": self.model_id,
                    "location": self.location,
                    "auth": "ADC",
                    "next_step": "Set GOOGLE_CLOUD_PROJECT in your .env file",
                },
            )

        try:
            # Vertex AI with Application Default Credentials (ADC) ONLY.
            # No API keys; ADC credentials are automatically discovered by google-genai SDK.
            self._client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
            )
        except Exception as exc:  # noqa: BLE001
            self.available = False
            self.reason = "vertex_client_init_failed"
            logger.error(
                "vertex_client_init_failed",
                project=self.project,
                location=self.location,
                model=self.model_id,
                error=str(exc),
            )
            raise ModelUnavailableError(
                f"Failed to initialize Vertex AI Gemini client with ADC: {exc}",
                details={
                    "project": self.project,
                    "location": self.location,
                    "model": self.model_id,
                    "auth": "ADC",
                    "next_step": "Run 'gcloud auth application-default login' to refresh credentials",
                },
            ) from exc
        return self._client

    def probe(self) -> None:
        """Fail clearly if ADC or Vertex AI model is unavailable."""
        if not self.project:
            self.available = False
            self.reason = "google_cloud_project_missing"
            logger.warning(
                "vertex_agent_probe_skipped",
                model=self.model_id,
                reason="GOOGLE_CLOUD_PROJECT is not configured in .env",
            )
            raise ModelUnavailableError(
                "GOOGLE_CLOUD_PROJECT is not configured",
                details={"next_step": "Add GOOGLE_CLOUD_PROJECT=your-project-id to .env"},
            )

        try:
            client = self._ensure_client()
            client.models.generate_content(
                model=self.model_id,
                contents="Reply with OK",
            )
            self.available = True
            self.reason = None
        except Exception as exc:  # noqa: BLE001
            self.available = False
            err_str = str(exc).lower()
            if (
                "credentials" in err_str
                or "auth" in err_str
                or "unauthenticated" in err_str
                or "permission" in err_str
                or "reauthentication" in err_str
                or "expired" in err_str
                or "default credentials" in err_str
            ):
                self.reason = "authentication_required"
            else:
                self.reason = "model_unavailable"
            logger.error(
                "vertex_agent_unavailable",
                model=self.model_id,
                project=self.project,
                location=self.location,
                auth="ADC",
                reason=self.reason,
                error=str(exc),
            )
            raise ModelUnavailableError(
                f"Vertex AI Gemini model {self.model_id!r} unavailable: {exc}",
                details={
                    "model": self.model_id,
                    "project": self.project,
                    "location": self.location,
                    "auth": "ADC",
                    "next_step": "Run 'gcloud auth application-default login' to refresh credentials",
                },
            ) from exc
        logger.info(
            "vertex_agent_probe_ok",
            project=self.project,
            location=self.location,
            model=self.model_id,
            auth="ADC",
        )

    def _extract_usage(self, response: Any, *, images_sent: int = 0) -> AgentUsage:
        um = getattr(response, "usage_metadata", None)
        tokens_in = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
        tokens_out = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
        # Include thinking tokens in out estimate when present
        thoughts = int(getattr(um, "thoughts_token_count", 0) or 0) if um else 0
        tokens_out += thoughts
        raw = {
            "prompt_token_count": tokens_in,
            "candidates_token_count": int(getattr(um, "candidates_token_count", 0) or 0)
            if um
            else 0,
            "thoughts_token_count": thoughts,
            "total_token_count": int(getattr(um, "total_token_count", 0) or 0) if um else 0,
            "images_sent": images_sent,
        }
        return AgentUsage(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_id=self.model_id,
            raw=raw,
            images_sent=images_sent,
        )

    def _generate_json(
        self,
        *,
        system: str,
        contents: Any,
        images_sent: int = 0,
    ) -> tuple[dict[str, Any], AgentUsage]:
        from google.genai import types

        client = self._ensure_client()
        user_chars = len(contents) if isinstance(contents, str) else -1
        logger.info(
            "vertex_agent_request_start",
            model=self.model_id,
            system_chars=len(system),
            user_chars=user_chars,
            images_sent=images_sent,
            multimodal=not isinstance(contents, str),
        )
        response = None
        max_retries = 2
        retry_delay = 0.5
        for attempt in range(max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=self.model_id,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                    ),
                )
                break
            except Exception as exc:  # noqa: BLE001
                if attempt < max_retries:
                    logger.warning(
                        "vertex_agent_request_retry",
                        model=self.model_id,
                        attempt=attempt + 1,
                        error=str(exc),
                        delay=retry_delay,
                    )
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2.0
                else:
                    logger.error("vertex_agent_request_failed", error=str(exc), model=self.model_id)
                    raise ModelUnavailableError(
                        f"Vertex agent request failed: {exc}",
                        details={"model": self.model_id},
                    ) from exc

        usage = self._extract_usage(response, images_sent=images_sent)
        text = (response.text or "").strip()
        logger.info(
            "vertex_agent_request_complete",
            model=self.model_id,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            images_sent=images_sent,
        )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AppError(
                "Agent returned non-JSON content",
                code="agent_parse_error",
                status_code=502,
                details={"snippet": text[:200]},
            ) from exc
        if not isinstance(data, dict):
            raise AppError(
                "Agent JSON root must be an object",
                code="agent_parse_error",
                status_code=502,
            )
        return data, usage

    def intake(
        self, *, name: str, goal: str, task_type: str, strategy: str, labels: list[str], modality: str = "image"
    ) -> tuple[IntakeAgentResult, AgentUsage]:
        system = (
            "You are the Ingenii annotation planning agent. "
            "Return ONLY JSON matching the schema fields: summary, needs_clarification, "
            "clarifying_questions[{id,question,options,rationale,decision_type,proposed_default,"
            "affects_count,example_asset_ids}], proposed_labels, "
            "label_strategy (generic|detailed|custom), "
            "recommended_models[{key,purpose,required}] where key is one of yolo26,faster_rcnn,dino,sam2,florence,tracker,gliner,qwen3_embedding,qwen3_reranker,paddleocr. "
            "OCR is supported via Florence/PaddleOCR. Video tracking requires yolo26 and tracker. Text requires gliner and optional qwen3_embedding/qwen3_reranker. Document requires paddleocr. "
            "Ask at most 2 clarifying questions, only when a decision would resolve many images. "
            "Prefer Decision needed language; do not escalate merely for low confidence."
        )
        user = json.dumps(
            {
                "project_name": name,
                "goal": goal,
                "task_type": task_type,
                "modality": modality,
                "label_strategy": strategy,
                "seed_labels": labels,
            }
        )
        data, usage = self._generate_json(system=system, contents=user)
        return IntakeAgentResult.model_validate(data), usage

    def propose_ontology(
        self,
        *,
        recon_context: dict[str, Any],
        images: list[AgentImagePart] | None = None,
    ) -> tuple[OntologyProposal, AgentUsage]:
        attached = list(images or [])
        has_images = bool(attached)
        system = (
            "You are the Ingenii dataset ontology agent. "
            + (
                "You receive dataset statistics, visual clusters, and representative images "
                "from reconnaissance. Ground proposed labels in what you SEE in the images "
                "plus cluster structure — not filenames or generic priors. "
                if has_images
                else "You receive dataset statistics, visual clusters, and sample metadata only "
                "(no image pixels attached). Propose carefully from structure; do not invent "
                "visual details you cannot verify. "
            )
            + "Propose a thoughtful label ontology — not a flat bag of nouns. "
            "Return ONLY JSON with: summary (string), proposed_labels[{name (string),"
            "definition (string), includes (string — not array), excludes (string — not array),"
            "aliases (string array), relations (array of objects), evidence_asset_ids (string array),"
            "prevalence_estimate (number 0-1, not words), kind (object|image|attribute)}], "
            "needs_decision (bool), clarifying_questions[{id,question,options,rationale,"
            "decision_type,proposed_default,affects_count,example_asset_ids}], "
            "recommended_models[{key,purpose,required}] (keys: yolo26, faster_rcnn, dino, sam2, florence, tracker, gliner, qwen3_embedding, qwen3_reranker, paddleocr), "
            "risks (string array), review_policy_notes (string — not array), "
            "label_strategy (generic|detailed|custom). "
            "Merge synonyms. Avoid visually indistinguishable labels. "
            "Cite evidence_asset_ids only for images that visually support that label. "
            "Use the optional goal as context, not ground truth. "
            "Escalate with Decision needed only when a boundary call improves many annotations. "
            "OCR is supported via Florence/PaddleOCR. Do not expose chain-of-thought."
        )
        contents = build_ontology_user_contents(recon_context, attached if has_images else None)
        data, usage = self._generate_json(
            system=system,
            contents=contents,
            images_sent=len(attached),
        )
        parsed = OntologyAgentResult.model_validate(normalize_ontology_payload(data))
        proposal = OntologyProposal(
            summary=parsed.summary,
            proposed_labels=[
                ProposedLabel(
                    name=lab.name,
                    definition=lab.definition,
                    includes=lab.includes,
                    excludes=lab.excludes,
                    aliases=lab.aliases,
                    relations=lab.relations,
                    evidence_asset_ids=lab.evidence_asset_ids,
                    prevalence_estimate=lab.prevalence_estimate,
                    kind=lab.kind,
                )
                for lab in parsed.proposed_labels
            ],
            needs_decision=parsed.needs_decision,
            clarifying_questions=parsed.clarifying_questions,
            recommended_models=parsed.recommended_models,
            risks=parsed.risks,
            review_policy_notes=parsed.review_policy_notes,
            label_strategy=parsed.label_strategy,
        )
        return proposal, usage

    def plan(
        self,
        *,
        name: str,
        goal: str,
        task_type: str,
        strategy: str,
        labels: list[str],
        clarifications: dict[str, str],
        intake_summary: str,
        modality: str = "image",
    ) -> tuple[ProjectPlanPayload, AgentUsage]:
        system = (
            "You are the Ingenii annotation planning agent. Produce an executable project plan. "
            "Return ONLY JSON with fields: summary, taxonomy (string array), label_strategy, "
            "workflow[{key,purpose,required}] (keys: yolo26, faster_rcnn, dino, sam2, florence, tracker, gliner, qwen3_embedding, qwen3_reranker, paddleocr), "
            "ambiguities (array), risks, review_policy (object), clarifications (object), rationale. "
            "When there is no ambiguity, review policy, or clarification, return [] or {} rather than null. "
            "Do not invent model runs."
        )
        user = json.dumps(
            {
                "project_name": name,
                "goal": goal,
                "task_type": task_type,
                "modality": modality,
                "label_strategy": strategy,
                "labels": labels,
                "clarifications": clarifications,
                "intake_summary": intake_summary,
            }
        )
        data, usage = self._generate_json(system=system, contents=user)
        logger.info("agent_plan_raw_received", model=self.model_id, affected_fields=[field for field in ("ambiguities", "review_policy", "clarifications") if data.get(field) is None])
        normalized = normalize_project_plan_response(data)
        logger.info("agent_plan_normalized", model=self.model_id)
        try:
            payload = ProjectPlanPayload.model_validate(normalized)
        except ValidationError as exc:
            logger.error(
                "agent_plan_validation_failed",
                model=self.model_id,
                affected_fields=sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()}),
                error=str(exc),
            )
            raise
        logger.info("agent_plan_validation_success", model=self.model_id)
        return payload, usage


# Backward and forward compatibility alias
GeminiAgentClient = VertexAgentClient



class AzureOpenAIAgentClient:
    """Agent client backed by Azure OpenAI / Azure AI Foundry (e.g. gpt-5.4-mini)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.endpoint = (
            getattr(settings, "azure_openai_endpoint", None)
            or os.getenv("AZURE_OPENAI_ENDPOINT")
            or ""
        ).strip()
        self.api_key = (
            getattr(settings, "azure_openai_api_key", None)
            or os.getenv("AZURE_OPENAI_API_KEY")
            or ""
        ).strip()
        self.model_id = (
            getattr(settings, "azure_openai_deployment", None)
            or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or "gpt-5.4-mini"
        ).strip()
        self.available: bool = True
        self.reason: str | None = None

    def _get_chat_url(self) -> str:
        base = self.endpoint.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def probe(self) -> None:
        """Fail clearly if Azure OpenAI endpoint or key is unavailable."""
        if not self.endpoint or not self.api_key:
            self.available = False
            self.reason = "azure_openai_credentials_missing"
            raise ModelUnavailableError(
                "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be configured",
                details={"model": self.model_id, "endpoint": self.endpoint},
            )

        import httpx
        url = self._get_chat_url()
        try:
            r = httpx.post(
                url,
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json={
                    "model": self.model_id,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                    "max_completion_tokens": 10,
                },
                timeout=15.0,
            )
            if r.status_code >= 400:
                self.available = False
                self.reason = f"http_{r.status_code}"
                raise ModelUnavailableError(
                    f"Azure OpenAI probe returned HTTP {r.status_code}: {r.text[:200]}",
                    details={"status_code": r.status_code, "model": self.model_id},
                )
            self.available = True
            self.reason = None
            logger.info("azure_openai_agent_probe_ok", endpoint=self.endpoint, model=self.model_id)
        except Exception as exc:
            self.available = False
            self.reason = "azure_connection_failed"
            logger.error("azure_openai_agent_unavailable", model=self.model_id, endpoint=self.endpoint, error=str(exc))
            raise ModelUnavailableError(
                f"Azure OpenAI agent model {self.model_id!r} unavailable: {exc}",
                details={"model": self.model_id, "endpoint": self.endpoint},
            ) from exc

    def _extract_usage(self, response_data: dict[str, Any], *, images_sent: int = 0) -> AgentUsage:
        raw = response_data.get("usage") or {}
        tokens_in = int(raw.get("prompt_tokens", 0) or 0)
        tokens_out = int(raw.get("completion_tokens", 0) or 0)
        return AgentUsage(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_id=self.model_id,
            raw=raw,
            images_sent=images_sent,
        )

    def _generate_json(
        self,
        *,
        system: str,
        contents: Any,
        images_sent: int = 0,
    ) -> tuple[dict[str, Any], AgentUsage]:
        import httpx
        import time

        url = self._get_chat_url()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system}
        ]

        if isinstance(contents, str):
            messages.append({"role": "user", "content": contents})
        elif isinstance(contents, list):
            messages.append({"role": "user", "content": contents})
        elif isinstance(contents, dict):
            messages.append({"role": "user", "content": json.dumps(contents)})
        else:
            messages.append({"role": "user", "content": str(contents)})

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "azure_openai_agent_request_start",
            model=self.model_id,
            system_chars=len(system),
            images_sent=images_sent,
            multimodal=not isinstance(contents, str),
        )

        max_retries = 2
        retry_delay = 0.5
        resp_data = None
        for attempt in range(max_retries + 1):
            try:
                r = httpx.post(
                    url,
                    headers={"api-key": self.api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=60.0,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                resp_data = r.json()
                break
            except Exception as exc:
                if attempt < max_retries:
                    logger.warning(
                        "azure_openai_agent_request_retry",
                        model=self.model_id,
                        attempt=attempt + 1,
                        error=str(exc),
                        delay=retry_delay,
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2.0
                else:
                    logger.error("azure_openai_agent_request_failed", error=str(exc), model=self.model_id)
                    raise ModelUnavailableError(
                        f"Azure OpenAI agent request failed: {exc}",
                        details={"model": self.model_id},
                    ) from exc

        usage = self._extract_usage(resp_data, images_sent=images_sent)
        choices = resp_data.get("choices") or []
        if not choices:
            raise AppError("Agent returned empty choices", code="agent_empty_response", status_code=502)
        text = ((choices[0].get("message") or {}).get("content") or "").strip()
        logger.info(
            "azure_openai_agent_request_complete",
            model=self.model_id,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            images_sent=images_sent,
        )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            m = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    data = None
            else:
                data = None
            if not isinstance(data, dict):
                raise AppError(
                    "Agent returned non-JSON content",
                    code="agent_parse_error",
                    status_code=502,
                    details={"snippet": text[:200]},
                ) from exc

        if not isinstance(data, dict):
            raise AppError("Agent JSON root must be an object", code="agent_parse_error", status_code=502)
        return data, usage

    def intake(
        self, *, name: str, goal: str, task_type: str, strategy: str, labels: list[str], modality: str = "image"
    ) -> tuple[IntakeAgentResult, AgentUsage]:
        system = (
            "You are the Ingenii annotation planning agent. "
            "Return ONLY JSON matching the schema fields: summary, needs_clarification, "
            "clarifying_questions[{id,question,options,rationale,decision_type,proposed_default,"
            "affects_count,example_asset_ids}], proposed_labels, "
            "label_strategy (generic|detailed|custom), "
            "recommended_models[{key,purpose,required}] where key is one of yolo26,faster_rcnn,dino,sam2,florence,tracker,gliner,qwen3_embedding,qwen3_reranker,paddleocr. "
            "OCR is supported via Florence/PaddleOCR. Video tracking requires yolo26 and tracker. Text requires gliner and optional qwen3_embedding/qwen3_reranker. Document requires paddleocr. "
            "Ask at most 2 clarifying questions, only when a decision would resolve many images. "
            "Prefer Decision needed language; do not escalate merely for low confidence."
        )
        user = json.dumps(
            {
                "project_name": name,
                "goal": goal,
                "task_type": task_type,
                "modality": modality,
                "label_strategy": strategy,
                "seed_labels": labels,
            }
        )
        data, usage = self._generate_json(system=system, contents=user)
        return IntakeAgentResult.model_validate(data), usage

    def propose_ontology(
        self,
        *,
        recon_context: dict[str, Any],
        images: list[AgentImagePart] | None = None,
    ) -> tuple[OntologyProposal, AgentUsage]:
        attached = list(images or [])
        has_images = bool(attached)
        system = (
            "You are the Ingenii dataset ontology agent. "
            + (
                "You receive dataset statistics, visual clusters, and representative images "
                "from reconnaissance. Ground proposed labels in what you SEE in the images "
                "plus cluster structure — not filenames or generic priors. "
                if has_images
                else "You receive dataset statistics, visual clusters, and sample metadata only "
                "(no image pixels attached). Propose carefully from structure; do not invent "
                "visual details you cannot verify. "
            )
            + "Propose a thoughtful label ontology — not a flat bag of nouns. "
            "Return ONLY JSON with: summary (string), proposed_labels[{name (string),"
            "definition (string), includes (string — not array), excludes (string — not array),"
            "aliases (string array), relations (array of objects), evidence_asset_ids (string array),"
            "prevalence_estimate (number 0-1, not words), kind (object|image|attribute)}], "
            "needs_decision (bool), clarifying_questions[{id,question,options,rationale,"
            "decision_type,proposed_default,affects_count,example_asset_ids}], "
            "recommended_models[{key,purpose,required}] (keys: yolo26, faster_rcnn, dino, sam2, florence, tracker, gliner, qwen3_embedding, qwen3_reranker, paddleocr), "
            "risks (string array), review_policy_notes (string — not array), "
            "label_strategy (generic|detailed|custom). "
            "Merge synonyms. Avoid visually indistinguishable labels. "
            "Cite evidence_asset_ids only for images that visually support that label. "
            "Use the optional goal as context, not ground truth. "
            "Escalate with Decision needed only when a boundary call improves many annotations. "
            "OCR is supported via Florence/PaddleOCR. Do not expose chain-of-thought."
        )
        context = dict(recon_context)
        stats = context.get("stats")
        if isinstance(stats, dict):
            slim_stats = {
                k: v
                for k, v in stats.items()
                if k not in {"profiles", "per_asset_quality"}
            }
            context["stats"] = slim_stats
        text = json.dumps(context)

        if not has_images:
            contents: Any = text
        else:
            import base64
            contents = [
                {
                    "type": "text",
                    "text": (
                        "Dataset reconnaissance context (JSON). Each attached image is labeled "
                        "with its asset_id so you can cite evidence_asset_ids from visual content:\n"
                        f"{text}"
                    ),
                }
            ]
            for img in attached:
                b64_data = base64.b64encode(img.data).decode("ascii")
                contents.append({"type": "text", "text": f"Image asset_id={img.asset_id}"})
                contents.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{img.mime_type};base64,{b64_data}"},
                    }
                )

        try:
            data, usage = self._generate_json(
                system=system,
                contents=contents,
                images_sent=len(attached) if has_images else 0,
            )
        except Exception as exc:
            # If multimodal failed due to an image format/parse error, retry gracefully with text-only
            if has_images and "image" in str(exc).lower():
                logger.warning("azure_openai_multimodal_fallback_to_text", error=str(exc))
                data, usage = self._generate_json(system=system, contents=text, images_sent=0)
            else:
                raise

        parsed = OntologyAgentResult.model_validate(normalize_ontology_payload(data))
        proposal = OntologyProposal(
            summary=parsed.summary,
            proposed_labels=[
                ProposedLabel(
                    name=lab.name,
                    definition=lab.definition,
                    includes=lab.includes,
                    excludes=lab.excludes,
                    aliases=lab.aliases,
                    relations=lab.relations,
                    evidence_asset_ids=lab.evidence_asset_ids,
                    prevalence_estimate=lab.prevalence_estimate,
                    kind=lab.kind,
                )
                for lab in parsed.proposed_labels
            ],
            needs_decision=parsed.needs_decision,
            clarifying_questions=parsed.clarifying_questions,
            recommended_models=parsed.recommended_models,
            risks=parsed.risks,
            review_policy_notes=parsed.review_policy_notes,
            label_strategy=parsed.label_strategy,
        )
        return proposal, usage

    def plan(
        self,
        *,
        name: str,
        goal: str,
        task_type: str,
        strategy: str,
        labels: list[str],
        clarifications: dict[str, str],
        intake_summary: str,
        modality: str = "image",
    ) -> tuple[ProjectPlanPayload, AgentUsage]:
        system = (
            "You are the Ingenii annotation planning agent. Produce an executable project plan. "
            "Return ONLY JSON with fields: summary, taxonomy (string array), label_strategy, "
            "workflow[{key,purpose,required}] (keys: yolo26, faster_rcnn, dino, sam2, florence, tracker, gliner, qwen3_embedding, qwen3_reranker, paddleocr), "
            "ambiguities (array), risks, review_policy (object), clarifications (object), rationale. "
            "When there is no ambiguity, review policy, or clarification, return [] or {} rather than null. "
            "Do not invent model runs."
        )
        user = json.dumps(
            {
                "project_name": name,
                "goal": goal,
                "task_type": task_type,
                "modality": modality,
                "label_strategy": strategy,
                "labels": labels,
                "clarifications": clarifications,
                "intake_summary": intake_summary,
            }
        )
        data, usage = self._generate_json(system=system, contents=user)
        logger.info(
            "agent_plan_raw_received",
            model=self.model_id,
            affected_fields=[field for field in ("ambiguities", "review_policy", "clarifications") if data.get(field) is None],
        )
        normalized = normalize_project_plan_response(data)
        logger.info("agent_plan_normalized", model=self.model_id)
        try:
            payload = ProjectPlanPayload.model_validate(normalized)
        except ValidationError as exc:
            logger.error(
                "agent_plan_validation_failed",
                model=self.model_id,
                affected_fields=sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()}),
                error=str(exc),
            )
            raise
        logger.info("agent_plan_validation_success", model=self.model_id)
        return payload, usage


# Backward and forward compatibility alias
AzureAgentClient = AzureOpenAIAgentClient
