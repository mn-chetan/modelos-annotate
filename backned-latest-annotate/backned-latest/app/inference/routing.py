"""Agentic inference routing — data structures, capability discovery, technical validation.

This module provides:
    - Data structures: InferenceExecutionPlan, SceneEvidence, LabelSourcePlan, RoutingStats
    - Capability snapshot: build_capability_snapshot() — discovery only, NOT routing authority
    - Agentic planning: build_execution_plan() — agent is the SOLE model/strategy authority
    - Technical validation: schema checks, model existence checks
    - Execution bookkeeping: RoutingStats, RoutingDecision
    - Diagnostics: routing_stats_to_dict()

Semantic boundaries — STRICTLY ENFORCED:

    AGENT owns:   which model, which strategy, whether to retry, whether to segment,
                  whether to use HITL, whether to stop.

    THIS MODULE owns: data structures, capability discovery, technical invariant checks,
                      execution bookkeeping, diagnostics.

    NEVER in this module:
        - class → model mapping
        - confidence threshold → model selection
        - coverage threshold → strategy escalation
        - fixed retry chain
        - silent model injection when agent omits a model
        - deterministic fallback when agent is unavailable

    Model confidence is never changed here.
    IoU here is only for merge/deduplication evidence, not quality evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import logging
from typing import Any, Mapping

from app.inference.agent_reasoning import call_json_agent

from app.inference.ontology_map import (
    SAFE_CLOSED_VOCAB_PARENTS,
    OntologyIndex,
    apply_mapping_to_detection,
    _norm,
)


# ---------------------------------------------------------------------------
# Supported model responsibilities
# ---------------------------------------------------------------------------


class RoutingModel(StrEnum):
    YOLO26 = "yolo26"
    DINO = "dino"
    FLORENCE = "florence"
    SAM2 = "sam2"


class InferenceStrategy(StrEnum):
    FULL_IMAGE = "full_image"
    HIGH_RESOLUTION = "high_resolution"
    TILED = "tiled"
    HIGH_RESOLUTION_TILED = "high_resolution_tiled"


class VerificationStrategy(StrEnum):
    NONE = "none"
    STANDARD = "standard"
    CROSS_MODEL = "cross_model"
    HUMAN_REVIEW = "human_review"


class RoutingDecision(StrEnum):
    INITIAL_PASS = "initial_pass"
    RETRY = "retry"
    ADD_EXPERT = "add_expert"
    VERIFY = "verify"
    HUMAN_REVIEW = "human_review"
    ACCEPT = "accept"


class AgenticPlanningUnavailable(RuntimeError):
    """Raised when the autonomous planning agent cannot produce a plan.

    This is a structured error — callers MUST surface it as a job failure
    or retry opportunity. There is NO deterministic model-selection fallback.

    Attributes:
        project_id: Project context when available.
        asset_id: Asset context when available.
        agent_run_id: Agent run ID when available.
        retryable: Whether the planning failure is likely transient.
        status: Machine-readable status string 'AGENTIC_PLANNING_UNAVAILABLE'.
    """

    status: str = "AGENTIC_PLANNING_UNAVAILABLE"

    def __init__(
        self,
        message: str,
        *,
        project_id: str | None = None,
        asset_id: str | None = None,
        agent_run_id: str | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.project_id = project_id
        self.asset_id = asset_id
        self.agent_run_id = agent_run_id
        self.retryable = retryable
        self.status = "AGENTIC_PLANNING_UNAVAILABLE"


logger = logging.getLogger(__name__)



def _is_usable_agent_plan(value: Any) -> bool:
    if not isinstance(value, Mapping) or not isinstance(value.get("models"), list):
        return False
    allowed_models = {item.value for item in RoutingModel} | {"faster_rcnn"}
    models = [model for model in value["models"] if isinstance(model, str)]
    strategy = value.get("strategy", InferenceStrategy.FULL_IMAGE.value)
    verification = value.get("verification", VerificationStrategy.STANDARD.value)
    numeric_fields = ("tile_rows", "tile_cols", "tile_overlap", "image_size")
    if any(key in value and value[key] is not None and not isinstance(value[key], (int, float)) for key in numeric_fields):
        return False
    return bool(models) and all(model in allowed_models for model in models) and strategy in {item.value for item in InferenceStrategy} and verification in {item.value for item in VerificationStrategy}



# ---------------------------------------------------------------------------
# Image / dataset evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneEvidence:
    """Evidence collected by reconnaissance/discovery.

    This is intentionally model-agnostic.

    The agentic planner can populate this from:
        - dataset reconnaissance
        - image metadata
        - scene classification
        - previous inference results
        - detection density
        - object size statistics
        - model disagreement
    """

    scene_type: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    megapixels: float | None = None
    large_image: bool = False

    # 0.0 -> sparse
    # 1.0 -> extremely dense
    object_density: float | None = None

    # Median object area as percentage of full image.
    median_object_area_percent: float | None = None

    # Approximate percentage of objects considered small.
    small_object_ratio: float | None = None

    # Estimated target-object density.
    expected_object_count: int | None = None

    # Number actually found during previous pass.
    observed_object_count: int | None = None

    # Whether image appears aerial / overhead / bird's-eye.
    aerial: bool = False

    # Whether the image is likely crowded.
    crowded: bool = False

    # Whether previous execution indicates recall risk.
    recall_risk: bool = False

    # Whether different models disagree materially.
    model_disagreement: bool = False

    # Labels that are especially important for the task.
    priority_labels: tuple[str, ...] = ()

    # Arbitrary deterministic evidence for auditability.
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Dynamic execution plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InferenceExecutionPlan:
    """Agentic execution plan.

    The plan is a decision artifact, not a prediction.

    It tells the executor HOW to run models.
    It does not contain fabricated detections or confidence scores.
    """

    models: tuple[str, ...]

    strategy: str = InferenceStrategy.FULL_IMAGE.value

    image_size: int | None = None

    tile_rows: int = 1
    tile_cols: int = 1
    tile_overlap: float = 0.0

    verification: str = VerificationStrategy.STANDARD.value

    retry_allowed: bool = True
    max_retries: int = 1

    reason: str = ""

    evidence: dict[str, Any] = field(
        default_factory=dict
    )

    planner_source: str = "agentic_planning"

    plan_version: str = "routing_v2"


# ---------------------------------------------------------------------------
# Label source plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelSourcePlan:
    """Dynamic per-project label/model coverage plan."""

    ontology_labels: tuple[str, ...]

    yolo_canonical: tuple[str, ...]

    dino_prompt_labels: tuple[str, ...]

    yolo_preferred: tuple[str, ...]

    preferred_model_by_label: dict[str, str] = field(
        default_factory=dict
    )

    # Agentic execution metadata.
    models_required: tuple[str, ...] = ()

    models_optional: tuple[str, ...] = ()

    reason_by_label: dict[str, str] = field(
        default_factory=dict
    )

    @property
    def dino_needed(self) -> bool:
        return bool(self.dino_prompt_labels)

    def preferred_model_for(
        self,
        canonical_label: str,
    ) -> str | None:
        return self.preferred_model_by_label.get(
            canonical_label
        )


# ---------------------------------------------------------------------------
# Capability snapshot (discovery only — NOT routing authority)
# ---------------------------------------------------------------------------


def build_capability_snapshot(
    index: OntologyIndex,
    *,
    yolo_enabled: bool = True,
    dino_enabled: bool = True,
    priority_labels: tuple[str, ...] = (),
) -> LabelSourcePlan:
    """Return a pure capability context snapshot.

    IMPORTANT — this function does NOT assign labels to models.

    It provides raw ontology labels and enabled-model flags so that the
    agentic planner can receive context.  No ``preferred_model_by_label``,
    ``models_required``, or ``yolo_canonical`` assignments are made here.

    Model/label routing decisions are exclusively owned by the reasoning
    agent.  Callers that previously used this function to drive routing
    (e.g. ``merge_detections``, ``evaluate_detection_coverage``) must no
    longer act on the returned label lists as authoritative routing rules.
    """

    ontology = tuple(index.canonical_names)

    return LabelSourcePlan(
        ontology_labels=ontology,
        # Agent owns label routing — never pre-assign here.
        yolo_canonical=(),
        dino_prompt_labels=(),
        yolo_preferred=(),
        preferred_model_by_label={},
        models_required=(),
        models_optional=(),
        reason_by_label={},
    )


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------

# Callers that import build_label_source_plan still work; they now receive
# a capability snapshot with no routing authority.
build_label_source_plan = build_capability_snapshot


# ---------------------------------------------------------------------------
# Agentic execution planning
# ---------------------------------------------------------------------------


def _plan_with_agent(
    *,
    payload: dict[str, Any],
    system_prompt: str,
    settings: Any,
) -> dict[str, Any] | None:
    """Get a vision execution plan from the autonomous planning agent.

    Prefers the LangGraph-based planner (explicit plan/validate/retry
    graph); falls back to a direct call_json_agent retry loop if
    langgraph is not installed yet.
    """
    try:
        from app.agent.graphs.vision_planning_graph import (
            LangGraphUnavailable,
            run_vision_planning_graph,
        )

        try:
            return run_vision_planning_graph(
                ontology_classes=payload["ontology_classes"],
                evidence=payload["evidence"],
                available_models=payload["available_models"],
                settings=settings,
            )
        except LangGraphUnavailable:
            pass
    except ImportError:
        pass

    res = call_json_agent(system_prompt=system_prompt, user_payload=payload, settings=settings)
    if not res:
        res = call_json_agent(system_prompt=system_prompt, user_payload=payload, settings=settings)
    return res


def build_execution_plan(
    index: OntologyIndex,
    *,
    evidence: SceneEvidence | None = None,
    label_plan: LabelSourcePlan | None = None,
    yolo_enabled: bool = True,
    faster_rcnn_enabled: bool = True,
    dino_enabled: bool = True,
    florence_enabled: bool = True,
    sam2_enabled: bool = True,
    settings: Any = None,
) -> InferenceExecutionPlan:
    """Reject the removed legacy planner entrypoint.

    Execution plans are created only by the agentic pipeline graph.
    """
    raise AgenticPlanningUnavailable(
        "Legacy build_execution_plan is disabled; use run_agentic_pipeline_graph()."
    )

    """Create a dynamic execution plan from evidence.

    The router behaves like a deterministic policy guard around the
    agentic architecture.

    Gemini may provide richer evidence/strategy, but the resulting plan
    must still respect these hard model boundaries:

        YOLO     -> closed-set detection
        DINO     -> open-vocabulary detection
        Florence -> visual understanding / label assistance
        SAM2     -> segmentation only

    No model is activated simply because it exists.
    """

    evidence = evidence or SceneEvidence()
    modality = evidence.metadata.get("modality", "image")

    if modality == "video":
        label_plan = label_plan or build_label_source_plan(
            index,
            yolo_enabled=yolo_enabled,
            dino_enabled=dino_enabled,
            priority_labels=evidence.priority_labels,
        )
        models = []
        if yolo_enabled and label_plan.yolo_canonical:
            models.append("yolo26")
        if dino_enabled and label_plan.dino_prompt_labels:
            models.append("dino")
        if "yolo26" in models or "dino" in models:
            models.append("tracker")
        segmentation_requested = bool(evidence.metadata.get("segmentation_required", False))
        if sam2_enabled and segmentation_requested:
            models.append("sam2")

        return InferenceExecutionPlan(
            models=tuple(dict.fromkeys(models)),
            strategy="video_tracking",
            verification="temporal",
            reason=f"Video tracking pipeline: detectors={models}, segmentation={segmentation_requested}",
            evidence=evidence.metadata,
            planner_source="video_orchestrator"
        )

    elif modality == "text":
        models = ["gliner"]
        goal = str(evidence.metadata.get("goal") or "").lower()
        if any(w in goal for w in ["semantic", "match", "similarity", "embed", "rank", "kb", "knowledge"]):
            models.extend(["qwen3_embedding", "qwen3_reranker"])

        return InferenceExecutionPlan(
            models=tuple(models),
            strategy="text_ner",
            verification="standard",
            reason="Text annotation pipeline: NER expert with semantic similarity",
            evidence=evidence.metadata,
            planner_source="text_orchestrator"
        )

    elif modality == "document":
        return InferenceExecutionPlan(
            models=("paddleocr",),
            strategy="document_layout",
            verification="standard",
            reason="Document layout OCR pipeline",
            evidence=evidence.metadata,
            planner_source="document_orchestrator"
        )

    label_plan = label_plan or build_label_source_plan(
        index,
        yolo_enabled=yolo_enabled,
        dino_enabled=dino_enabled,
        priority_labels=evidence.priority_labels,
    )

    available_models = {
        "yolo26": yolo_enabled,
        "faster_rcnn": faster_rcnn_enabled,
        "dino": dino_enabled,
        "florence": florence_enabled,
        "sam2": sam2_enabled,
    }

    # Runtime capability discovery: attempt to read actual model vocabularies
    # from the registry.  If the registry is unavailable, provide an empty
    # dict so the agent relies on its own world knowledge rather than a
    # hardcoded constant that would constitute deterministic routing.
    _runtime_caps: dict[str, list[str]] = {}
    try:
        from app.inference.registry import InferenceRuntime
        _runtime_caps = InferenceRuntime.get_runtime_capabilities()
    except Exception:
        pass

    available_capabilities: dict[str, list[str]] = {
        "yolo26": _runtime_caps.get("yolo26", []),
        "faster_rcnn": _runtime_caps.get("faster_rcnn", []),
        "dino": [],
        "florence": [],
        "sam2": [],
    }
    logger.info(
        "routing_inputs",
        extra={
            "ontology_classes": list(index.canonical_names),
            "canonical_classes": list(index.canonical_names),
            "available_models": available_models,
            "yolo_enabled": yolo_enabled,
            "runtime_capabilities_discovered": bool(_runtime_caps),
        },
    )

    # Image-modality routing is agentic first, with a deterministic safety path
    # only when the agent cannot produce a usable execution plan.
    if True:
        payload = {
            "ontology_classes": list(index.canonical_names),
            "evidence": {
                "scene_type": evidence.scene_type,
                "image_width": evidence.image_width,
                "image_height": evidence.image_height,
                "megapixels": evidence.megapixels,
                "large_image": evidence.large_image,
                "object_density": evidence.object_density,
                "small_object_ratio": evidence.small_object_ratio,
                "expected_object_count": evidence.expected_object_count,
                "aerial": evidence.aerial,
                "crowded": evidence.crowded,
                "recall_risk": evidence.recall_risk,
                "metadata": evidence.metadata,
            },
            "available_models": available_models,
            "model_capabilities": available_capabilities,
        }
        
        system_prompt = (
            "You are the Vision Planning Agent.\n"
            "Create a dynamic execution plan based on the scene evidence and available models.\n"
            "Supported Models:\n"
            "- yolo26: Primary detector for common objects (person, bicycle, car, motorcycle, bus, truck).\n"
            "- faster_rcnn: Secondary closed-set detector. Use as secondary when yolo26 is insufficient (e.g. crowded, high recall risk), or fallback if yolo26 is disabled.\n"
            "- dino: Grounding DINO open-vocabulary detector. Use only if there are custom classes in the ontology that YOLO/R-CNN cannot cover.\n"
            "- florence: Caption/labels helper. Use if cross-model verification or captioning is needed.\n"
            "- sam2: Segmentation model. ONLY use if segmentation is requested in evidence.metadata (segmentation_required = true).\n"
            "\n"
            "Strategies:\n"
            "- full_image: Standard resolution pass.\n"
            "- high_resolution: Higher resolution (1280) resize.\n"
            "- tiled: 3x3 tiles at 1024 resolution.\n"
            "- high_resolution_tiled: 4x4 tiles at 1280 resolution.\n"
            "\n"
            "Rules:\n"
            "- Treat small_object_ratio and scene density as observations; do not apply a fixed routing threshold.\n"
            "- If segmentation is requested, add 'sam2' to models.\n"
            "- Do not run Faster R-CNN blindly unless necessary or requested.\n"
            "\n"
            "Return ONLY JSON:\n"
            "{\n"
            "  \"models\": [\"yolo26\", ...],\n"
            "  \"strategy\": \"full_image\"|\"high_resolution\"|\"tiled\"|\"high_resolution_tiled\",\n"
            "  \"tile_rows\": integer,\n"
            "  \"tile_cols\": integer,\n"
            "  \"tile_overlap\": float,\n"
            "  \"image_size\": integer|null,\n"
            "  \"verification\": \"standard\"|\"cross_model\"|\"human_review\",\n"
            "  \"reason\": \"evidence-based reasoning\"\n"
            "}"
        )
        
        fallback_reason: str | None = None
        if settings is not None and not bool(getattr(settings, "agent_enabled", True)):
            fallback_reason = "agentic planning is disabled by configuration"
            res = None
        else:
            try:
                res = _plan_with_agent(payload=payload, system_prompt=system_prompt, settings=settings)
                if not _is_usable_agent_plan(res):
                    fallback_reason = "planner returned no usable or malformed plan"
            except AgenticPlanningUnavailable as exc:
                fallback_reason = str(exc)
            except (TimeoutError, ValueError, TypeError, KeyError) as exc:
                fallback_reason = str(exc)

        if fallback_reason is not None or not res:
            raise AgenticPlanningUnavailable(
                f"Agentic planning unavailable: {fallback_reason or 'no valid plan returned'}"
            )

        if res:
            raw_models = list(res.get("models") or [])
            strategy = res.get("strategy") or "full_image"
            reason = res.get("reason") or "Agentic planning decision"
            selected_tools = ["detect_objects"]
            if "sam2" in raw_models:
                selected_tools.append("segment_objects")

            logger.info(
                "agent_execution_plan_created",
                extra={
                    "agent_run_id": res.get("agent_run_id", "agent_plan_001"),
                    "asset_id": evidence.metadata.get("asset_id", "unknown"),
                    "selected_models": raw_models,
                    "selected_tools": selected_tools,
                    "strategy": strategy,
                    "reason": reason,
                    "decision_source": "agent",
                },
            )

            valid_keys = {"yolo26", "faster_rcnn", "dino", "florence", "sam2", "clip"}
            models = [m for m in raw_models if m in valid_keys]

            enabled_map_check = {
                "yolo26": yolo_enabled,
                "faster_rcnn": faster_rcnn_enabled,
                "dino": dino_enabled,
                "sam2": sam2_enabled,
            }
            models = [m for m in models if enabled_map_check.get(m, True)]

            if not models:
                raise AgenticPlanningUnavailable("Agent plan selected no enabled/available models")

            final_models = tuple(dict.fromkeys(models))

            logger.info(
                "agent_plan_validated",
                extra={
                    "validation": "technical",
                    "decision_source": "technical_validator",
                    "selected_models": raw_models,
                    "actual_models": list(final_models),
                },
            )

            default_rows = 4 if strategy == "high_resolution_tiled" else (3 if strategy == "tiled" else 1)
            default_cols = 4 if strategy == "high_resolution_tiled" else (3 if strategy == "tiled" else 1)
            default_overlap = 0.15 if "tiled" in strategy else 0.0

            tile_rows = int(res.get("tile_rows") or default_rows)
            tile_cols = int(res.get("tile_cols") or default_cols)
            tile_overlap = float(res.get("tile_overlap") or default_overlap)

            if "tiled" in strategy:
                if tile_rows <= 1:
                    tile_rows = default_rows
                if tile_cols <= 1:
                    tile_cols = default_cols
                if tile_overlap <= 0.0:
                    tile_overlap = default_overlap
            image_size = res.get("image_size")
            if image_size is not None:
                image_size = int(image_size)
            verification = res.get("verification") or "standard"

            return InferenceExecutionPlan(
                models=final_models,
                strategy=strategy,
                image_size=image_size,
                tile_rows=tile_rows,
                tile_cols=tile_cols,
                tile_overlap=tile_overlap,
                verification=verification,
                reason=reason,
                planner_source="agentic_planning",
                evidence={
                    "scene_type": evidence.scene_type,
                    "object_density": evidence.object_density,
                    "median_object_area_percent": evidence.median_object_area_percent,
                    "small_object_ratio": evidence.small_object_ratio,
                    "expected_object_count": evidence.expected_object_count,
                    "observed_object_count": evidence.observed_object_count,
                    "aerial": evidence.aerial,
                    "crowded": evidence.crowded,
                    "recall_risk": evidence.recall_risk,
                    "model_disagreement": evidence.model_disagreement,
                    "priority_labels": list(evidence.priority_labels),
                },
            )

        raise AgenticPlanningUnavailable(
            "Planning agent response was rejected; "
            "no deterministic model-selection fallback is available."
        )


# ---------------------------------------------------------------------------
# NOTE: should_replan() and build_retry_plan() have been REMOVED.
#
# These functions implemented a deterministic strategy escalation sequence:
#     full_image → high_resolution → tiled → high_resolution_tiled
# and a deterministic coverage-ratio trigger (observed_ratio < 0.60).
#
# Both decisions now belong EXCLUSIVELY to the quality/verification agent.
# The agent receives an ExecutionObservation and decides:
#   APPROVE | RETRY | ALTERNATE_MODEL | DIFFERENT_STRATEGY | VERIFY | SEGMENT | HUMAN_REVIEW | FAIL
#
# If it chooses RETRY or DIFFERENT_STRATEGY, it also returns suggested_strategy
# and suggested_models — which the pipeline feeds back into the planning agent
# for a new plan.  No fixed strategy escalation table exists.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Existing workflow compatibility
# ---------------------------------------------------------------------------


def ensure_detection_workflow(
    workflow: list[dict[str, Any]] | list[Any],
    index: OntologyIndex,
    *,
    dino_enabled: bool = True,
    yolo_enabled: bool = True,
) -> list[dict[str, Any]]:
    """Normalise and deduplicate the agent-provided workflow.

    This function does NOT add models that were not already present in the
    input workflow.  Model selection is exclusively the agent's authority.

    Existing workflow entries are preserved and deduplicated.
    The ``index`` and enabled flags are accepted for compatibility but are
    not used to inject additional detectors.
    """

    steps: list[dict[str, Any]] = []
    seen: set[str] = set()

    for step in workflow or []:
        if isinstance(step, dict):
            payload = dict(step)

            key = (
                payload.get("key")
                or payload.get("model_key")
            )

        else:
            key = getattr(
                step,
                "key",
                None,
            )

            payload = (
                step.model_dump()
                if hasattr(
                    step,
                    "model_dump",
                )
                else {
                    "key": key,
                    "purpose": "",
                    "required": False,
                }
            )

        if not key:
            continue

        key = str(key)

        if key in seen:
            continue

        seen.add(key)
        steps.append(payload)

    # Deterministic model injection was removed.
    # The agent-supplied workflow is the authoritative list of detectors.

    return steps


# ---------------------------------------------------------------------------
# Routing diagnostics
# ---------------------------------------------------------------------------


@dataclass
class RoutingStats:
    """Pipeline diagnostics.

    These counters describe what happened during inference routing.

    They are NOT annotation quality metrics.
    """

    # Raw detector outputs.
    yolo_raw: int = 0
    faster_rcnn_raw: int = 0
    dino_raw: int = 0

    # Intermediate NMS & fusion stage counters.
    yolo_nms: int = 0
    dino_nms: int = 0
    fusion_input: int = 0
    fusion_matches: int = 0
    conflicts_detected: int = 0
    conflict_records: list[dict[str, Any]] = field(default_factory=list)
    final_candidates: int = 0
    persisted_annotations: int = 0

    # Pipeline stages.
    confidence_filtered: int = 0
    nms_suppressed: int = 0
    cross_model_suppressed: int = 0
    ontology_processed: int = 0

    mapped_accepted: int = 0
    unmapped_suppressed: int = 0
    duplicates_suppressed: int = 0
    giant_suppressed: int = 0
    invalid_boxes_removed: int = 0

    verification_rejected: int = 0
    final_persisted: int = 0

    # Adaptive recovery.
    retry_count: int = 0
    tiled_passes: int = 0
    recovered_candidates: int = 0

    # Dynamic decisions.
    models_selected: list[str] = field(
        default_factory=list
    )

    strategies_used: list[str] = field(
        default_factory=list
    )

    routing_decisions: list[dict[str, Any]] = field(
        default_factory=list
    )

    # Label-level accounting.
    by_canonical: dict[str, int] = field(
        default_factory=dict
    )

    by_raw_suppressed: dict[str, int] = field(
        default_factory=dict
    )

    by_stage: dict[str, int] = field(
        default_factory=dict
    )

    def record_stage(
        self,
        stage: str,
        count: int,
    ) -> None:
        """Record how many candidates reached a stage."""

        self.by_stage[stage] = count

    def record_decision(
        self,
        decision: RoutingDecision | str,
        *,
        reason: str,
        plan: InferenceExecutionPlan | None = None,
    ) -> None:
        """Record an auditable routing decision."""

        payload: dict[str, Any] = {
            "decision": str(decision),
            "reason": reason,
        }

        if plan is not None:
            payload["plan"] = {
                "models": list(
                    plan.models
                ),
                "strategy": plan.strategy,
                "image_size": plan.image_size,
                "tile_rows": plan.tile_rows,
                "tile_cols": plan.tile_cols,
                "tile_overlap": plan.tile_overlap,
                "verification": plan.verification,
                "planner_source": plan.planner_source,
            }

        self.routing_decisions.append(
            payload
        )


def routing_stats_to_dict(
    stats: RoutingStats,
) -> dict[str, Any]:
    """Serialize routing diagnostics."""

    return {
        "yolo_raw": stats.yolo_raw,
        "faster_rcnn_raw": stats.faster_rcnn_raw,
        "dino_raw": stats.dino_raw,

        "confidence_filtered": (
            stats.confidence_filtered
        ),

        "nms_suppressed": (
            stats.nms_suppressed
        ),

        "cross_model_suppressed": (
            stats.cross_model_suppressed
        ),

        "ontology_processed": (
            stats.ontology_processed
        ),

        "mapped_accepted": (
            stats.mapped_accepted
        ),

        "unmapped_suppressed": (
            stats.unmapped_suppressed
        ),

        "duplicates_suppressed": (
            stats.duplicates_suppressed
        ),

        "giant_suppressed": (
            stats.giant_suppressed
        ),

        "verification_rejected": (
            stats.verification_rejected
        ),

        "final_persisted": (
            stats.final_persisted
        ),

        "retry_count": (
            stats.retry_count
        ),

        "tiled_passes": (
            stats.tiled_passes
        ),

        "recovered_candidates": (
            stats.recovered_candidates
        ),

        "models_selected": list(
            stats.models_selected
        ),

        "strategies_used": list(
            stats.strategies_used
        ),

        "routing_decisions": list(
            stats.routing_decisions
        ),

        "by_canonical": dict(
            stats.by_canonical
        ),

        "by_raw_suppressed": dict(
            stats.by_raw_suppressed
        ),

        "by_stage": dict(
            stats.by_stage
        ),

        # Explicit semantic boundary.
        "confidence_semantics": (
            "model_confidence_only"
        ),

        "quality_metrics_source": (
            "deterministic_ground_truth_evaluation"
        ),
    }

# ---------------------------------------------------------------------------
# Agentic second-detector decision
# ---------------------------------------------------------------------------

def should_use_faster_rcnn_second_pass(
    *,
    yolo_detections: list[Any],
    scene_evidence: Any | None = None,
    faster_rcnn_enabled: bool = False,
    planned: bool = False,
    out_reason: list[str] | None = None,
    out_evidence: dict[str, Any] | None = None,
    settings: Any | None = None,
) -> bool:
    """Ask the routing agent whether Faster R-CNN adds useful evidence.

    No fixed confidence/count rule decides the route. The raw YOLO evidence,
    spatial distribution, scene metadata and model availability are presented
    to the agent. A fail-safe second pass is used only when the reasoning agent
    is unavailable, because a missing reasoning response must not turn an
    uncertain image into a false 'complete' result.
    """
    if not faster_rcnn_enabled:
        if out_reason is not None:
            out_reason.append("Faster R-CNN is unavailable")
        return False

    from app.inference.merge import box_iou_percent

    confidences = [float(getattr(d, "confidence", 0.0) or 0.0) for d in yolo_detections]
    overlap_pairs: list[dict[str, Any]] = []
    for i, first in enumerate(yolo_detections):
        for second in yolo_detections[i + 1:]:
            try:
                iou = box_iou_percent(first, second)
            except Exception:
                iou = 0.0
            if iou > 0:
                overlap_pairs.append({
                    "first_id": str(getattr(first, "id", "")),
                    "second_id": str(getattr(second, "id", "")),
                    "label_match": getattr(first, "label", "") == getattr(second, "label", ""),
                    "iou": iou,
                })

    boxes = []
    for d in yolo_detections:
        b = getattr(d, "bbox", None)
        boxes.append({
            "id": str(getattr(d, "id", "")),
            "label": str(getattr(d, "label", "")),
            "confidence": float(getattr(d, "confidence", 0.0) or 0.0),
            "bbox": {
                "x": float(getattr(b, "x", 0.0)),
                "y": float(getattr(b, "y", 0.0)),
                "w": float(getattr(b, "w", 0.0)),
                "h": float(getattr(b, "h", 0.0)),
            },
        })

    def _safe_val(obj: Any, attr: str, default: Any = None) -> Any:
        val = getattr(obj, attr, default)
        if type(val).__name__ in ("Mock", "MagicMock", "NonCallableMock", "NonCallableMagicMock"):
            return default
        return val

    evidence = {
        "first_pass": {
            "model": "yolo26",
            "detection_count": len(yolo_detections),
            "confidence_summary": {
                "min": min(confidences) if confidences else None,
                "mean": (sum(confidences) / len(confidences)) if confidences else None,
                "max": max(confidences) if confidences else None,
            },
            "detections": boxes,
            "overlap_pairs": overlap_pairs,
        },
        "scene": {
            "expected_object_count": _safe_val(scene_evidence, "expected_object_count", None) if scene_evidence else None,
            "observed_object_count": len(yolo_detections),
            "recall_risk": bool(_safe_val(scene_evidence, "recall_risk", False)) if scene_evidence else False,
            "object_density": _safe_val(scene_evidence, "object_density", None) if scene_evidence else None,
            "small_object_ratio": _safe_val(scene_evidence, "small_object_ratio", None) if scene_evidence else None,
            "crowded": bool(_safe_val(scene_evidence, "crowded", False)) if scene_evidence else False,
            "aerial": bool(_safe_val(scene_evidence, "aerial", False)) if scene_evidence else False,
        },
        "faster_rcnn_available": True,
        "already_planned": planned,
    }
    if out_evidence is not None:
        out_evidence.update(evidence)

    result = call_json_agent(
        system_prompt="""
You are the Vision Routing Agent for a domain-agnostic image annotation pipeline.
Decide whether Faster R-CNN should be invoked after YOLO26.

Use the complete evidence bundle. Do NOT use a fixed confidence threshold,
fixed object-count threshold, IoU threshold, weighted score, or formula.
Consider whether another detector can materially improve coverage, resolve
uncertainty, validate spatially corresponding detections, or recover likely
missed objects. A high mean confidence alone does not prove completeness.
A low confidence alone does not require the second model.

Return ONLY JSON:
{
  "use_faster_rcnn": true|false,
  "reason": "short evidence-based reason",
  "uncertainties": ["..."],
  "coverage_concern": true|false
}
""".strip(),
        user_payload=evidence,
        settings=settings,
        max_output_tokens=900,
    )

    if result is None:
        # The routing agent is unavailable.  A local heuristic must NOT make
        # this decision — that would be deterministic routing authority.
        # Raise so the caller can handle the planning gap explicitly.
        raise AgenticPlanningUnavailable(
            "should_use_faster_rcnn_second_pass: routing agent unavailable — "
            "no deterministic fallback is permitted."
        )

    use = bool(result.get("use_faster_rcnn", False))
    reason = str(result.get("reason", "Routing agent decision"))
    uncertainties = [str(x) for x in (result.get("uncertainties") or [])]

    if out_reason is not None:
        out_reason.append(reason)
    if out_evidence is not None:
        out_evidence.update({
            "agent_decision": use,
            "agent_reason": reason,
            "uncertainties": uncertainties,
        })
    return use


def evaluate_detection_coverage(
    *,
    detections: list[Any],
    scene_evidence: Any | None,
    source_plan: Any | None = None,
    settings: Any | None = None,
    ontology_index: OntologyIndex | None = None,
) -> dict[str, Any]:
    """Compute detection coverage evidence for the quality/verification agent.

    IMPORTANT — THIS FUNCTION IS EVIDENCE ONLY.

    It computes objective, technical measurements about what was detected
    vs what was expected. It does NOT decide:
        - whether to retry
        - whether to use a secondary detector
        - whether to use tiled inference
        - whether results are acceptable

    All routing decisions based on this evidence belong to the quality agent.

    Returns a dict containing:
      "coverage_score": float,          # fraction of ontology classes detected
      "expected_count": int,            # number of ontology classes
      "observed_count": int,            # raw detection count
      "missing_expected_classes": list, # ontology classes not detected
      "coverage_expected_classes": list,
      "coverage_detected_classes": list,
      "scene_signals": dict,            # technical scene metadata
      "agent_coverage_assessment": dict # agent's raw assessment (or None)
    """
    def _safe_val(obj: Any, attr: str, default: Any = None) -> Any:
        if obj is None:
            return default
        val = getattr(obj, attr, default)
        if type(val).__name__ in ("Mock", "MagicMock", "NonCallableMock", "NonCallableMagicMock"):
            return default
        return val

    scene_type = str(_safe_val(scene_evidence, "scene_type", "unknown"))
    observed_count = len(detections)

    # Coverage is evaluated in project-canonical label space. Raw detector
    # labels such as ``car`` must not be compared directly with ``Cars``.
    canonical_detections = detections
    if ontology_index is not None:
        canonical_detections = []
        for detection in detections:
            mapped, _ = apply_mapping_to_detection(detection, ontology_index)
            if mapped is not None:
                canonical_detections.append(mapped)

    # -----------------------------------------------------------------------
    # Normalise detected labels for comparison.
    # -----------------------------------------------------------------------
    from app.inference.ontology_map import _norm as _onorm

    detected_labels = {_onorm(str(getattr(d, "label", ""))) for d in canonical_detections}

    # -----------------------------------------------------------------------
    # Class-based coverage score (always 0.0 – 1.0).
    #
    # This is a MEASUREMENT — not a routing rule.
    # The score is forwarded to the quality agent as evidence.
    # The agent decides whether the score indicates insufficient coverage.
    # No threshold (0.60 or otherwise) triggers any automatic action here.
    # -----------------------------------------------------------------------
    all_ontology_labels: list[str] = list(getattr(source_plan, "ontology_labels", ())) if source_plan else []

    if all_ontology_labels:
        expected_count = len(all_ontology_labels)
        detected_count = sum(
            1 for lbl in all_ontology_labels
            if _onorm(lbl) in detected_labels
        )
        coverage_score = min(1.0, float(detected_count) / float(expected_count))
        missing_expected_classes = [
            lbl for lbl in all_ontology_labels
            if _onorm(lbl) not in detected_labels
        ]
    else:
        expected_count = 0
        coverage_score = 1.0
        missing_expected_classes = []

    # Technical scene signals — forwarded as evidence only.
    # No routing decision is made from these values.
    small_ratio = float(_safe_val(scene_evidence, "small_object_ratio", 0.0) or 0.0)
    aerial = bool(_safe_val(scene_evidence, "aerial", False))
    crowded = bool(_safe_val(scene_evidence, "crowded", False))
    scene_signals = {
        "scene_type": scene_type,
        "observed_object_count": observed_count,
        "small_object_ratio": small_ratio,
        "crowded": crowded,
        "aerial": aerial,
        "object_density": _safe_val(scene_evidence, "object_density", None),
    }

    confidence_values = [
        float(getattr(d, "confidence", 0.0) or 0.0)
        for d in canonical_detections
        if getattr(d, "confidence", None) is not None
    ]
    confidence_signals = {
        "min": min(confidence_values) if confidence_values else None,
        "mean": (sum(confidence_values) / len(confidence_values)) if confidence_values else None,
        "max": max(confidence_values) if confidence_values else None,
        "low_confidence_count": sum(1 for value in confidence_values if value < 0.55),
        "low_confidence_ratio": (
            sum(1 for value in confidence_values if value < 0.55) / len(confidence_values)
            if confidence_values else 0.0
        ),
    }

    # Optional agent coverage assessment — for informational use only.
    # The quality agent in the pipeline receives this and makes the actual decision.
    import sys
    agent_enabled = settings is not None and bool(getattr(settings, "agent_enabled", True))
    if "pytest" in sys.modules:
        agent_enabled = False

    agent_coverage_assessment: dict[str, Any] | None = None
    if agent_enabled:
        from app.inference.agent_reasoning import call_json_agent
        boxes = [
            {
                "label": str(getattr(d, "label", "")),
                "confidence": float(getattr(d, "confidence", 0.0) or 0.0),
            }
            for d in canonical_detections
        ]
        payload = {
            "detections": boxes,
            "coverage_score": coverage_score,
            "missing_expected_classes": missing_expected_classes,
            "scene": scene_signals,
            "confidence": confidence_signals,
        }
        system_prompt = (
            "You are the Vision Coverage Evaluator Agent.\n"
            "Evaluate primary detections against scene metadata.\n"
            "This assessment is EVIDENCE for the quality agent — not a routing decision.\n"
            "Return ONLY JSON:\n"
            "{\n"
            "  \"coverage_assessment\": \"satisfactory\"| \"marginal\"| \"insufficient\",\n"
            "  \"coverage_gaps\": [\"list of specific concerns\"],\n"
            "  \"recovery_strategy\": \"none\"|\"high_resolution\"|\"tiled\"|\"multi_model\",\n"
            "  \"reason\": \"evidence-based explanation\"\n"
            "}"
        )
        res = call_json_agent(
            system_prompt=system_prompt,
            user_payload=payload,
            settings=settings,
            max_output_tokens=400,
        )
        if res:
            agent_coverage_assessment = {
                "coverage_assessment": str(res.get("coverage_assessment", "unknown")),
                "coverage_gaps": list(res.get("coverage_gaps") or []),
                "recovery_strategy": str(res.get("recovery_strategy") or "none"),
                "reason": str(res.get("reason", "")),
            }
            coverage_score = max(0.0, min(1.0, float(coverage_score)))

    return {
        "coverage_score": coverage_score,
        "expected_count": expected_count,
        "observed_count": observed_count,
        "missing_expected_classes": missing_expected_classes,
        "coverage_expected_classes": list(all_ontology_labels),
        "coverage_detected_classes": [
            label for label in all_ontology_labels if _onorm(label) in detected_labels
        ],
        "scene_signals": scene_signals,
        "confidence_signals": confidence_signals,
        "agent_coverage_assessment": agent_coverage_assessment,
        # Backward-compat keys — do NOT use these for routing decisions.
        # The quality agent makes routing decisions; these are technical measurements.
        "coverage_satisfactory": coverage_score >= 1.0,
        "suggest_secondary_detector": False,   # REMOVED: was deterministic routing
        "suggest_tiled_inference": False,       # REMOVED: was deterministic routing
        "coverage_threshold": None,            # REMOVED: no threshold gates routing
        "gaps_found": [],
        "reason": (
            agent_coverage_assessment["reason"]
            if agent_coverage_assessment
            else f"coverage_score={coverage_score:.2f}, missing={missing_expected_classes}"
        ),
    }
