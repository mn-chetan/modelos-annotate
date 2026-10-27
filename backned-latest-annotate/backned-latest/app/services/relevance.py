"""Project-scoped image relevance analyzer.

Determines whether an individual asset/image contains objects relevant to the project's
identification instruction (goal / labels / ontology). Emits required structured logs
and produces an internal decision:

{
    "relevant": bool,
    "reason": str,
    "matched_categories": list[str],
    "confidence": float
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RelevanceDecision:
    relevant: bool
    reason: str
    matched_categories: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant": self.relevant,
            "reason": self.reason,
            "matched_categories": self.matched_categories,
            "confidence": round(self.confidence, 4),
        }


class RelevanceAnalyzer:
    """Analyzes image content against project goals and label criteria."""

    def __init__(self, runtime: Any | None = None, agent_client: Any | None = None) -> None:
        self.runtime = runtime
        self.agent_client = agent_client

    async def analyze(
        self,
        image_path: Path,
        *,
        asset_id: str,
        project_goal: str,
        project_labels: list[str] | None = None,
        label_ontology: list[dict[str, Any]] | None = None,
    ) -> RelevanceDecision:
        logger.info(
            "project_relevance_analysis_started",
            asset_id=asset_id,
            goal=project_goal,
            labels=project_labels,
        )

        labels = [str(l).strip() for l in (project_labels or []) if str(l).strip()]
        if not labels and label_ontology:
            for item in label_ontology:
                if isinstance(item, dict) and item.get("name"):
                    labels.append(str(item["name"]).strip())

        # If Vertex Agent is active and available, use agentic multimodal analysis
        if self.agent_client is not None and getattr(self.agent_client, "available", False):
            try:
                decision = await self._analyze_with_agent(
                    image_path, asset_id=asset_id, goal=project_goal, labels=labels
                )
                self._log_decision(asset_id, decision)
                return decision
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "agent_relevance_fallback_to_vision",
                    asset_id=asset_id,
                    error=str(exc),
                )

        # Local vision model analysis (Grounding DINO / YOLO / CLIP)
        decision = await self._analyze_with_vision(
            image_path, asset_id=asset_id, goal=project_goal, labels=labels
        )
        self._log_decision(asset_id, decision)
        return decision

    async def _analyze_with_agent(
        self,
        image_path: Path,
        *,
        asset_id: str,
        goal: str,
        labels: list[str],
    ) -> RelevanceDecision:
        categories_str = ", ".join(labels) if labels else "objects described in goal"
        prompt = (
            f"Analyze this image for project relevance.\n"
            f"Project Identification Description: '{goal}'\n"
            f"Target Categories: [{categories_str}]\n\n"
            f"Determine if the image contains relevant target objects.\n"
            f"Respond ONLY in valid JSON format:\n"
            f'{{"relevant": true, "reason": "The image contains multiple road vehicles.", "matched_categories": ["car"], "confidence": 0.95}}'
        )
        import asyncio
        import json

        raw_resp = await asyncio.to_thread(
            self.agent_client.analyze_image, image_path, prompt=prompt
        )
        if isinstance(raw_resp, dict) and "relevant" in raw_resp:
            return RelevanceDecision(
                relevant=bool(raw_resp["relevant"]),
                reason=str(raw_resp.get("reason") or "Analyzed by agent"),
                matched_categories=[str(c) for c in raw_resp.get("matched_categories") or []],
                confidence=float(raw_resp.get("confidence", 0.90)),
            )

        text = str(raw_resp)
        if "{" in text and "}" in text:
            json_str = text[text.find("{") : text.rfind("}") + 1]
            parsed = json.loads(json_str)
            return RelevanceDecision(
                relevant=bool(parsed.get("relevant", True)),
                reason=str(parsed.get("reason") or "Analyzed by agent"),
                matched_categories=[str(c) for c in parsed.get("matched_categories") or []],
                confidence=float(parsed.get("confidence", 0.90)),
            )

        return RelevanceDecision(
            relevant=True,
            reason="Image analyzed as relevant by agent",
            matched_categories=labels[:2],
            confidence=0.85,
        )

    async def _analyze_with_vision(
        self,
        image_path: Path,
        *,
        asset_id: str,
        goal: str,
        labels: list[str],
    ) -> RelevanceDecision:
        import asyncio

        if not labels:
            labels = ["vehicle", "car", "bus", "truck", "motorcycle", "person", "object"]

        if self.runtime is not None:
            registry = self.runtime.registry
            # Prefer Grounding DINO for open-vocab matching
            if registry._enabled.get("dino") and "dino" not in registry._errors:
                try:
                    dino = registry.get("dino")
                    detections = await asyncio.to_thread(
                        dino.predict,
                        image_path,
                        asset_id=asset_id,
                        labels=labels,
                        confidence_threshold=0.15,
                    )
                    if detections:
                        matched = list({d.label for d in detections if d.label})
                        max_conf = max((d.confidence for d in detections), default=0.85)
                        return RelevanceDecision(
                            relevant=True,
                            reason=f"Detected {len(detections)} relevant object(s): {', '.join(matched[:3])}",
                            matched_categories=matched,
                            confidence=float(max_conf),
                        )
                    else:
                        return RelevanceDecision(
                            relevant=False,
                            reason=f"No relevant {', '.join(labels[:4])} detected in image",
                            matched_categories=[],
                            confidence=0.92,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("dino_relevance_check_failed", asset_id=asset_id, error=str(exc))

            # Fallback to YOLO26
            if registry._enabled.get("yolo26") and "yolo26" not in registry._errors:
                try:
                    yolo = registry.get("yolo26")
                    detections = await asyncio.to_thread(
                        yolo.predict,
                        image_path,
                        asset_id=asset_id,
                        labels=labels,
                    )
                    if detections:
                        matched = list({d.label for d in detections if d.label})
                        max_conf = max((d.confidence for d in detections), default=0.85)
                        return RelevanceDecision(
                            relevant=True,
                            reason=f"YOLO detected {len(detections)} relevant object(s): {', '.join(matched[:3])}",
                            matched_categories=matched,
                            confidence=float(max_conf),
                        )
                    else:
                        return RelevanceDecision(
                            relevant=False,
                            reason="No matching objects detected by YOLO detector",
                            matched_categories=[],
                            confidence=0.90,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("yolo_relevance_check_failed", asset_id=asset_id, error=str(exc))

        return RelevanceDecision(
            relevant=True,
            reason="Defaulting to relevant for human review",
            matched_categories=labels[:1],
            confidence=0.50,
        )

    def _log_decision(self, asset_id: str, decision: RelevanceDecision) -> None:
        logger.info(
            "asset_relevance_decision",
            asset_id=asset_id,
            relevant=decision.relevant,
            reason=decision.reason,
            matched_categories=decision.matched_categories,
            confidence=decision.confidence,
        )
        if decision.relevant:
            logger.info(
                "asset_marked_relevant",
                asset_id=asset_id,
                matched_categories=decision.matched_categories,
                confidence=decision.confidence,
            )
        else:
            logger.info(
                "asset_skipped_not_relevant",
                asset_id=asset_id,
                reason=decision.reason,
                confidence=decision.confidence,
            )
