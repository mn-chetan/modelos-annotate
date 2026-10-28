"""LangGraph Agentic Annotation Orchestration Pipeline."""

from __future__ import annotations

import asyncio
import time
from typing import Any, TypedDict
from pathlib import Path

from app.db.models import AnnotationRow, AssetRow, MongoDoc, MongoSession, ProjectRow, get_database
from app.errors import NotFoundError
from app.domain.enums import AnnotationSource, GeometryType, ReviewStatus
from app.inference.contracts import ModelKey, NormalizedDetection
from app.inference.detection_quality import build_image_coverage_summary, log_pipeline_event
from app.inference.merge import box_iou_percent, merge_detections, stats_to_dict, verify_merged_detections
from app.inference.ontology_map import SAFE_ALIASES, build_ontology_index
from app.inference.registry import InferenceRuntime
from app.logging import get_logger
from app.agent.audit import AgentAuditRecord, create_audit_record
from app.agent.capability_registry import ModelCapabilityRegistry
from app.agent.intent import ParsedIntent, extract_explicit_object_labels, parse_user_intent
from app.agent.quality_review import review_execution_quality
from app.config import get_settings
from app.inference.agent_reasoning import call_json_agent
from app.services.annotations import AnnotationService
from app.services.quality_validation import validate_object_level_quality
from app.services.review_decision import ReviewDecision, decide_review
from app.storage.files import FileStorage
import sys
video_backend_path = Path(__file__).resolve().parents[3] / "annotation-video" / "backend"
if video_backend_path.exists() and str(video_backend_path) not in sys.path:
    sys.path.insert(0, str(video_backend_path))

logger = get_logger(__name__)

_EXCLUDED_AI_DETECTION_LABELS = {"auto"}


def _is_excluded_ai_label(label: Any) -> bool:
    clean = str(label or "").strip().casefold()
    return bool(clean) and SAFE_ALIASES.get(clean, clean) in _EXCLUDED_AI_DETECTION_LABELS


def _final_same_label_deduplicate(
    detections: list[Any],
    *,
    iou_threshold: float = 0.85,
) -> tuple[list[Any], int]:
    """Final safety net preventing duplicate boxes from reaching persistence.

    The main fusion pipeline handles cross-model association. This last pass
    only removes near-identical boxes with the same canonical label, preserving
    nearby objects that merely overlap in crowded scenes.
    """
    ordered = sorted(
        list(detections),
        key=lambda item: float(getattr(item, "confidence", 0.0) or 0.0),
        reverse=True,
    )
    kept: list[Any] = []
    suppressed = 0
    for candidate in ordered:
        label = str(getattr(candidate, "label", "")).strip().casefold()
        duplicate = any(
            label == str(getattr(existing, "label", "")).strip().casefold()
            and box_iou_percent(candidate, existing) >= iou_threshold
            for existing in kept
        )
        if duplicate:
            suppressed += 1
            continue
        kept.append(candidate)
    return kept, suppressed

def _resolve_authoritative_asset_id(
    *,
    asset_id: str | None,
    asset: Any,
    asset_snapshot: dict[str, Any] | None,
) -> str:
    identities = {
        "argument": str(asset_id) if asset_id else None,
        "asset": str(getattr(asset, "id", "") or "") or None,
        "snapshot": str((asset_snapshot or {}).get("id") or "") or None,
    }
    present = {value for value in identities.values() if value}
    if len(present) > 1:
        logger.critical(
            "asset_identity_violation",
            asset_ids=identities,
            stage="agent_graph_entry",
        )
        raise RuntimeError(f"Asset identity mismatch at graph entry: {identities!r}")
    if not present:
        raise RuntimeError("Agent graph requires an authoritative asset_id")
    return next(iter(present))


def _project_spatial_ontology(snapshot: dict[str, Any]) -> list[str]:
    """Return approved canonical ontology names, including non-target classes.

    ``labels``/``target_labels`` are mandatory targets, while
    ``label_ontology`` is the approved scope available to a configured image
    detection task.  Keeping both concepts separate prevents a custom target
    such as ``auto`` from narrowing the whole traffic scene to one class.
    """
    targets = list(snapshot.get("target_labels") or snapshot.get("labels") or [])
    rich = list(snapshot.get("label_ontology") or [])
    if rich:
        names = build_ontology_index(targets, ontology=rich).canonical_names
    else:
        names = [str(label).strip() for label in targets if str(label).strip()]

    return [
        name for name in names
        if not _is_excluded_ai_label(name)
    ]


def _validate_execution_results(
    detections: list[Any],
    *,
    asset_id: str,
    execution_id: str,
    model: str,
    state: PipelineState,
) -> list[Any]:
    """Reject model results that cannot belong to this graph execution."""
    mismatches = []
    for det in detections:
        result_asset_id = str(getattr(det, "asset_id", "") or "")
        result_execution_id = str(
            (getattr(det, "provenance", {}) or {}).get("execution_id") or ""
        )
        if result_asset_id != str(asset_id) or result_execution_id != str(execution_id):
            mismatches.append({
                "result_asset_id": result_asset_id,
                "result_execution_id": result_execution_id,
            })
    if mismatches:
        logger.error(
            "execution_result_identity_mismatch",
            current_asset_id=asset_id,
            result_asset_ids=list({item["result_asset_id"] for item in mismatches}),
            current_execution_id=execution_id,
            result_execution_ids=list({item["result_execution_id"] for item in mismatches}),
            model=model,
            job_id=state.get("job_id"),
            job_item_id=state.get("job_item_id"),
        )
        raise RuntimeError(
            f"Execution result identity mismatch for {model}: "
            f"expected asset_id={asset_id!r}, execution_id={execution_id!r}"
        )
    return detections


class PipelineState(TypedDict, total=False):
    # Context
    project: Any
    asset: Any
    user_request: str
    session: Any
    storage: FileStorage
    runtime: InferenceRuntime
    
    # State tracking
    parsed_intent: ParsedIntent | None
    ontology_labels: list[str]
    available_models: dict[str, bool]
    capability_gaps: list[dict[str, Any]]
    runtime_capabilities: list[dict[str, Any]]
    execution_plan: dict[str, Any]
    
    # Execution outputs
    raw_detections: list[Any]
    merged_detections: list[Any]
    masks: list[Any]
    quality_report: dict[str, Any] | None
    mean_confidence: float | None
    review_decision: Any
    quality_agent_decision: dict[str, Any] | None
    
    # Flow control
    actions_taken: list[str]
    replan_count: int
    max_replans: int
    next_node: str
    audit_record: AgentAuditRecord | None
    duration_ms: float
    planner_source: str
    agent_plan_invalid: dict[str, Any]
    batch_id: str | None
    job_id: str | None
    job_item_id: str | None
    execution_errors: list[dict[str, Any]]
    project_id: str
    asset_id: str
    project_snapshot: dict[str, Any]
    asset_snapshot: dict[str, Any]
    final_status: str | None
    human_feedback: dict[str, Any] | None
    reprocess_count: int
    max_reprocess_cycles: int
    review_cycle_id: str | None
    escalation_required: bool
    # Retry context: missing_labels populated by quality agent on RETRY decision
    missing_labels: list[str]
    # Per-asset execution ledger.  This is deliberately part of the graph
    # state, rather than a module/global cache, so concurrent assets cannot
    # observe or suppress one another's inference.
    execution_history: list[dict[str, Any]]
    execution_id: str
    previous_attempts: list[dict[str, Any]]
    fusion_conflicts: list[dict[str, Any]]
    text_annotations: list[dict[str, Any]]
    text_result: dict[str, Any]


async def understand_request_node(state: PipelineState) -> PipelineState:
    t0 = time.perf_counter()
    snapshot = state["project_snapshot"]
    is_text = snapshot.get("modality") in {"text", "document"}
    if is_text:
        from app.services.text_capability import resolve_text_target_labels
        ontology = resolve_text_target_labels(snapshot, snapshot.get("task_type"))
    else:
        ontology = list(snapshot.get("target_labels") or snapshot.get("labels", []))
    feedback = state.get("human_feedback")
    effective_request = state["user_request"]
    if feedback:
        reason_str = feedback.get("reason", "reprocess_requested")
        human_lbl = feedback.get("human_label")
        geom = feedback.get("geometry")
        effective_request = (
            f"{effective_request}\n"
            f"[Human Reviewer Feedback - Reprocess Requested]: Reason={reason_str}"
        )
        if human_lbl:
            effective_request += f", Human Target Label={human_lbl}"
        if geom:
            effective_request += f", Region={geom}"
        logger.info(
            "understand_request_with_hitl_feedback",
            reason=reason_str,
            human_label=human_lbl,
            reprocess_count=state.get("reprocess_count", 0),
        )

    intent = parse_user_intent(
        effective_request,
        ontology,
        allow_generic_object_fallback=False,
        modality=snapshot.get("modality") if is_text else None,
        configured_task=snapshot.get("task_type") if is_text else None,
    )
    if not is_text:
        configured_task = str(snapshot.get("task_type") or "object_detection").strip().lower()
        configured_intent = {
            "object_detection": ("detection", "box"),
            "detection": ("detection", "box"),
            "segmentation": ("segmentation", "polygon"),
            "instance_segmentation": ("segmentation", "polygon"),
            "classification": ("classification", "classification"),
        }.get(configured_task)
        if configured_intent:
            from dataclasses import replace
            configured_labels = list(snapshot.get("target_labels") or snapshot.get("labels", []))
            explicit_labels = extract_explicit_object_labels(effective_request, configured_labels)
            # Project labels remain the default, but an explicit requirement
            # list is the request-level source of truth for this execution.
            effective_labels = explicit_labels or configured_labels
            if configured_intent[0] == "detection":
                # Mandatory targets are retained, while the approved ontology
                # remains in scope for scene-relevant object detection.
                effective_labels = list(dict.fromkeys([
                    *effective_labels,
                    *_project_spatial_ontology(snapshot),
                ]))
            effective_labels = [
                label for label in effective_labels
                if not _is_excluded_ai_label(label)
            ]
            intent = replace(
                intent,
                task_type=configured_intent[0],
                geometry_type=configured_intent[1],
                requested_labels=effective_labels,
                spatial_labels=effective_labels,
                reasoning=(
                    "Resolved from the explicit annotation requirement."
                    if explicit_labels
                    else "Resolved from the current project configuration."
                ),
            )
    intent_ms = (time.perf_counter() - t0) * 1000.0
    timings = dict(state.get("timings", {}))
    timings["intent_ms"] = intent_ms
    
    logger.info(
        "agent_intent_completed",
        project_id=state.get("project_id") or snapshot.get("id"),
        task_type=intent.task_type,
        geometry=intent.geometry_type,
        requested_labels=intent.requested_labels,
        high_precision=intent.high_precision,
        small_object_focus=intent.small_object_focus,
    )
    logger.info(
        "agent_intent_resolved",
        project_id=state.get("project_id") or snapshot.get("id"),
        task_type=intent.task_type,
        geometry=intent.geometry_type,
        requested_labels=intent.requested_labels,
        source=("explicit_requirement" if extract_explicit_object_labels(effective_request, ontology) else "project_configuration"),
    )
    logger.info(
        "agent_detection_scope_resolved",
        project_id=state.get("project_id") or snapshot.get("id"),
        asset_id=state.get("asset_id") or state.get("asset_snapshot", {}).get("id"),
        requested_labels=ontology,
        resolved_detection_labels=intent.requested_labels,
        mandatory_target_labels=list(snapshot.get("target_labels") or snapshot.get("labels") or []),
    )
    if is_text:
        logger.info(
            "agent_text_intent_completed",
            project_id=state.get("project_id") or snapshot.get("id"),
            asset_id=state.get("asset_id") or state.get("asset_snapshot", {}).get("id"),
            task_type=intent.task_type,
            geometry=intent.geometry_type,
            requested_labels=intent.requested_labels,
        )
    
    audit = state.get("audit_record")
    if audit:
        audit.structured_intent = {
            "task_type": intent.task_type,
            "geometry_type": intent.geometry_type,
            "requested_labels": intent.requested_labels,
            "high_precision": intent.high_precision,
            "small_object_focus": intent.small_object_focus,
            "reasoning": intent.reasoning,
        }
        audit.log_event("understand_request", {"task_type": intent.task_type, "geometry": intent.geometry_type})
        
    return {"parsed_intent": intent, "ontology_labels": ontology, "timings": timings}


async def discover_capabilities_node(state: PipelineState) -> PipelineState:
    t0 = time.perf_counter()
    intent: ParsedIntent = state["parsed_intent"]  # type: ignore[assignment]
    runtime: InferenceRuntime = state["runtime"]
    
    status_list = runtime.registry.status() if (runtime and getattr(runtime, "registry", None)) else []
    avail_map = {s.key: (s.availability == "available" or s.availability == "not_loaded") for s in status_list}
    
    registry = ModelCapabilityRegistry(avail_map)
    runtime_capabilities = runtime.registry.get_runtime_capabilities() if (runtime and getattr(runtime, "registry", None)) else []
    capability_aliases = {
        "object_detection": "detection",
        "open_vocabulary_detection": "open_vocab_detection",
        "instance_segmentation": "segmentation",
    }
    discovered_capabilities: dict[str, list[str]] = {}
    for model_key, metadata in registry.capabilities.items():
        if not avail_map.get(model_key, False):
            continue
        for task_type in metadata.get("task_types", []):
            capability = capability_aliases.get(task_type, task_type)
            discovered_capabilities.setdefault(capability, []).append(model_key)
    if state["project_snapshot"].get("modality") in {"text", "document"}:
        for key, metadata in registry.text_capabilities().items():
            capability = str(metadata.get("capability", key))
            # Text implementations are registered services, not image models;
            # expose only the capability implemented by this registry entry.
            discovered_capabilities.setdefault(capability, []).append(key)
            avail_map.setdefault(key, True)
    gaps = [
        {"capability": capability, "available_models": []}
        for capability in ("detection", "open_vocab_detection", "segmentation")
        if not discovered_capabilities.get(capability)
    ]
    cap_ms = (time.perf_counter() - t0) * 1000.0
    
    timings = dict(state.get("timings", {}))
    timings["capability_discovery_ms"] = cap_ms

    for cap in runtime_capabilities if isinstance(runtime_capabilities, list) else []:
        if isinstance(cap, dict):
            m_caps = [str(c).lower() for c in cap.get("capabilities", [])]
            is_open = bool(cap.get("is_open_vocabulary") or "open_vocab_detection" in m_caps or "open_vocabulary_detection" in m_caps)
            vocab = list(cap.get("vocabulary") or [])
            logger.info(
                "runtime_capability",
                model=cap.get("model_key"),
                vocabulary_type="open" if is_open else "closed",
                vocabulary_contains=vocab,
                vocabulary_count=len(vocab),
            )
            logger.info(
                "runtime_model_capability_discovered",
                model=cap.get("model_key"),
                capabilities=cap.get("capabilities", []),
                vocabulary_count=len(vocab),
                vocabulary_sample=vocab[:15],
            )
    
    logger.info(
        "agent_capabilities_discovered",
        available_models=list(avail_map.keys()),
        capabilities=discovered_capabilities,
        runtime_capabilities=runtime_capabilities,
        capability_gaps_count=len(gaps),
    )
    
    audit = state.get("audit_record")
    if audit:
        audit.available_models = avail_map
        audit.capability_gaps = gaps
        audit.log_event("discover_capabilities", {"capabilities": discovered_capabilities, "gaps_count": len(gaps)})
        
    return {
        "available_models": avail_map,
        "available_capabilities": discovered_capabilities,
        "capability_gaps": gaps,
        "runtime_capabilities": runtime_capabilities,
        "actions_taken": state.get("actions_taken", []) + ["discover_capabilities"],
        "timings": timings,
    }


def validate_plan_grounding(
    actions: list[dict[str, Any]],
    runtime_capabilities: list[dict[str, Any]],
    agent_run_id: str | None = None,
    asset_id: str | None = None,
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate every execution action and assigned label against CURRENT runtime capability metadata.

    Architectural Rules:
    1. Read the selected model's CURRENT runtime capability metadata.
    2. Determine whether the model is closed-vocabulary or open-vocabulary.
    3. For a CLOSED-VOCABULARY model:
       - requested label must exactly exist in the runtime vocabulary.
       - exact string membership is required.
       - no semantic aliases, no ontology expansion, no fuzzy matching, no domain-specific mapping.
    4. For an OPEN-VOCABULARY model:
       - semantic requested labels may be passed when supported by that model's capability.
    5. Never silently rewrite the user's requested label.
    6. If a requested label cannot be executed by the selected closed-vocabulary model,
       mark the action INVALID with structured evidence.

    Produces structured logs:
      - 'grounding': model, label, vocabulary_type, supported, validation, [reason]
      - 'technical_validation': status='VALID' | 'INVALID'

    Returns:
        (is_valid, validation_records, invalid_reasons)
    """
    caps_by_model = {
        str(c.get("model_key")): c
        for c in runtime_capabilities
        if isinstance(c, dict) and c.get("model_key")
    }
    records: list[dict[str, Any]] = []
    invalid_reasons: list[dict[str, Any]] = []

    for action in actions:
        m_key = str(action.get("model") or "").strip()
        m_cap = caps_by_model.get(m_key, {})
        m_caps = [str(c).lower() for c in (m_cap.get("capabilities") or m_cap.get("task_types") or [])]
        is_open_vocab = bool(
            m_cap.get("is_open_vocabulary")
            or "open_vocab_detection" in m_caps
            or "open_vocabulary_detection" in m_caps
        )
        vocab_type = "open" if is_open_vocab else "closed"
        action_labels = action.get("labels", [])
        m_vocab = {str(v).strip().casefold() for v in m_cap.get("vocabulary", [])}

        spatial_detection_capability = "detection" in m_caps or "object_detection" in m_caps or "open_vocab_detection" in m_caps or "open_vocabulary_detection" in m_caps
        if action_labels and not spatial_detection_capability:
            lbl_str = ", ".join(map(str, action_labels)) if action_labels else ""
            invalid_reasons.append({
                "model": m_key,
                "label": lbl_str,
                "labels": list(action_labels),
                "vocabulary_type": vocab_type,
                "supported": False,
                "validation": "invalid",
                "reason": "Model does not provide spatial detection capability",
            })
            logger.warning(
                "grounding",
                model=m_key,
                label=lbl_str,
                labels=list(action_labels),
                vocabulary_type=vocab_type,
                supported=False,
                validation="invalid",
                reason="Model does not provide spatial detection capability",
                agent_run_id=agent_run_id,
                asset_id=asset_id,
            )
            continue

        for lbl in action_labels:
            clean_lbl = str(lbl).strip()
            if not clean_lbl:
                continue
            if is_open_vocab:
                logger.info(
                    "grounding",
                    model=m_key,
                    label=clean_lbl,
                    vocabulary_type="open",
                    supported=True,
                    validation="valid",
                    capability="open_vocabulary",
                    agent_run_id=agent_run_id,
                    asset_id=asset_id,
                )
                records.append({
                    "model": m_key,
                    "label": clean_lbl,
                    "vocabulary_type": "open",
                    "supported": True,
                    "validation": "valid",
                })
                continue

            m_vocab_stems = {v.rstrip("s") for v in m_vocab}
            clean_cf = clean_lbl.casefold()
            clean_stem = clean_cf.rstrip("s")
            alias = SAFE_ALIASES.get(clean_cf, clean_cf).casefold()
            alias_stem = alias.rstrip("s")
            supported = (
                clean_cf in m_vocab
                or clean_stem in m_vocab
                or clean_stem in m_vocab_stems
                or alias in m_vocab
                or alias_stem in m_vocab
                or alias_stem in m_vocab_stems
            )
            if supported:
                logger.info(
                    "grounding",
                    model=m_key,
                    label=clean_lbl,
                    vocabulary_type="closed",
                    supported=True,
                    validation="valid",
                    agent_run_id=agent_run_id,
                    asset_id=asset_id,
                )
                records.append({
                    "model": m_key,
                    "label": clean_lbl,
                    "vocabulary_type":"closed",
                    "supported": True,
                    "validation": "valid",
                })
            else:
                reason = "Requested label is not present in runtime model vocabulary"
                logger.warning(
                    "grounding",
                    model=m_key,
                    label=clean_lbl,
                    vocabulary_type="closed",
                    supported=False,
                    validation="invalid",
                    reason=reason,
                    agent_run_id=agent_run_id,
                    asset_id=asset_id,
                )
                invalid_reasons.append({
                    "model": m_key,
                    "label": clean_lbl,
                    "vocabulary_type": "closed",
                    "supported": False,
                    "validation": "invalid",
                    "reason": reason,
                })

    is_valid = len(invalid_reasons) == 0
    if not is_valid:
        logger.error(
            "technical_validation",
            status="INVALID",
            invalid_count=len(invalid_reasons),
            invalid_reasons=invalid_reasons,
            agent_run_id=agent_run_id,
            asset_id=asset_id,
        )
    else:
        logger.info(
            "technical_validation",
            status="VALID",
            records_count=len(records),
            agent_run_id=agent_run_id,
            asset_id=asset_id,
        )
    return is_valid, records, invalid_reasons


def ground_labels_to_capabilities(
    requested_labels: list[str],
    runtime_capabilities: list[dict[str, Any]],
    preferred_models: list[str] | None = None,
    strategy: str = "full_image",
    parameters: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Ground requested labels dynamically to available runtime models.

    Ensures:
    - Closed-vocabulary models receive ONLY exact vocabulary matches.
    - Labels not present in closed-vocabulary models are assigned to open-vocabulary models (e.g. dino).
    - If no available model supports a label, that label is returned as unavailable.
    - Zero domain-specific or traffic-specific hardcoding.

    Returns:
        (actions, unavailable_labels)
    """
    caps_by_model = {
        str(c.get("model_key") or c.get("model")): c
        for c in runtime_capabilities
        if isinstance(c, dict) and (c.get("model_key") or c.get("model")) and c.get("available", True) is not False
    }
    
    # Identify closed-vocab and open-vocab detectors
    closed_models: list[str] = []
    open_models: list[str] = []
    
    pref = preferred_models or []
    ordered_keys = [k for k in pref if k in caps_by_model] + [k for k in caps_by_model if k not in pref]
    
    for k in ordered_keys:
        cap = caps_by_model[k]
        m_caps = [str(c).lower() for c in (cap.get("capabilities") or cap.get("task_types") or [])]
        has_detection = (
            "detection" in m_caps
            or "object_detection" in m_caps
            or "open_vocab_detection" in m_caps
            or "open_vocabulary_detection" in m_caps
        )
        if not has_detection:
            continue
        if bool(cap.get("is_open_vocabulary") or "open_vocab_detection" in m_caps or "open_vocabulary_detection" in m_caps):
            if k not in open_models:
                open_models.append(k)
        elif "detection" in m_caps or "object_detection" in m_caps:
            if k not in closed_models:
                closed_models.append(k)

    assignments: dict[str, list[str]] = {}
    unavailable_labels: list[str] = []

    for raw_label in requested_labels:
        clean = str(raw_label).strip()
        if not clean:
            continue
        if _is_excluded_ai_label(clean):
            continue
        # 1. Try closed-vocabulary models first if exact match exists
        assigned = False
        for cm in closed_models:
            vocab = {str(v).strip().casefold() for v in caps_by_model[cm].get("vocabulary", [])}
            vocab_stems = {v.rstrip("s") for v in vocab}
            clean_cf = clean.casefold()
            clean_stem = clean_cf.rstrip("s")
            alias = SAFE_ALIASES.get(clean_cf, clean_cf).casefold()
            alias_stem = alias.rstrip("s")
            if (
                clean_cf in vocab
                or clean_stem in vocab
                or clean_stem in vocab_stems
                or alias in vocab
                or alias_stem in vocab
                or alias_stem in vocab_stems
            ):
                assignments.setdefault(cm, []).append(clean)
                assigned = True
                break
        if assigned:
            continue

        # 2. Try open-vocabulary model for semantic or domain labels
        if open_models:
            om = open_models[0]
            assignments.setdefault(om, []).append(clean)
            assigned = True
            continue

        # 3. No available model supports this label
        unavailable_labels.append(clean)

    actions: list[dict[str, Any]] = []
    for model_key, labels in assignments.items():
        actions.append({
            "model": model_key,
            "strategy": strategy,
            "labels": labels,
            "parameters": dict(parameters or {}),
            "reason": f"Grounded {len(labels)} label(s) to {model_key} based on runtime capabilities",
        })

    return actions, unavailable_labels


async def create_execution_plan_node(state: PipelineState) -> PipelineState:
    t0 = time.perf_counter()
    intent: ParsedIntent = state["parsed_intent"]  # type: ignore[assignment]
    avail_map = state["available_models"]
    gaps = state["capability_gaps"]
    asset_id = state.get("asset_id") or state["asset_snapshot"].get("id")
    project_id = state.get("project_id") or state["project_snapshot"].get("id")
    
    selected_tools: list[str] = []

    if state["project_snapshot"].get("modality") in {"text", "document"}:
        from app.agent.capability_registry import ModelCapabilityRegistry
        from app.services.text_capability import resolve_text_entity_labels, resolve_text_target_labels
        task_raw = str(state["project_snapshot"].get("task_type") or state["project_snapshot"].get("task") or intent.task_type or "ENTITY_EXTRACTION")
        norm_task, capability = ModelCapabilityRegistry().resolve_text_task(task_raw)
        text_metadata = ModelCapabilityRegistry().text_capabilities().get(capability, {})
        plan_geometry = str((text_metadata.get("geometry_types") or ["text_span"])[0])
        available_capabilities = state.get("available_capabilities", {})
        if available_capabilities and not available_capabilities.get(capability):
            return {"execution_plan": {"modality": "text", "task": norm_task, "task_type": norm_task, "models": [], "requested_labels": [], "actions": [], "selected_tools": [], "errors": [{"code": "TEXT_CAPABILITY_UNAVAILABLE", "capability": capability}]}, "agent_plan_invalid": True}
        labels = resolve_text_target_labels(state["project_snapshot"], norm_task)
        entity_labels = resolve_text_entity_labels(state["project_snapshot"])
        if not labels:
            labels = list(getattr(intent, "requested_labels", None) or [])
        logger.info(
            "text_capability_selected",
            task=norm_task,
            capability=capability,
            selected_service=capability,
            project_id=project_id,
            asset_id=asset_id,
            requested_labels=labels,
        )
        logger.info(
            "text_planner_labels",
            graph_target_objects=state["project_snapshot"].get("target_objects"),
            planner_requested_labels=labels,
            capability=capability,
        )
        plan = {
            "decision_source": "agentic_text_planner",
            "plan_version": "1",
            "modality": "text",
            "task": norm_task,
            "task_type": norm_task,
            "geometry": plan_geometry,
            "models": [capability],
            "required_capabilities": [capability],
            "requested_labels": labels,
            "entity_labels": entity_labels,
            "actions": [{
                "model": capability,
                "strategy": "document",
                "labels": labels,
                "parameters": {},
                "reason": "Selected from the registered text capability set."
            }],
            "selected_tools": [capability],
            "verification_required": True
        }
        if state.get("audit_record"):
            state["audit_record"].execution_plan = plan
            state["audit_record"].log_event("create_text_execution_plan", plan)
        return {"execution_plan": plan, "planner_source": "agentic_text_planner", "timings": {**state.get("timings", {}), "planning_ms": (time.perf_counter() - t0) * 1000.0}}
        
    spatial_labels = getattr(intent, "spatial_labels", intent.requested_labels) or intent.requested_labels
    activity_labels = getattr(intent, "activity_labels", [])
    event_labels = getattr(intent, "event_labels", [])

    planner_payload = {
        "asset_metadata": {
            "asset_width": state["asset_snapshot"].get("width"),
            "asset_height": state["asset_snapshot"].get("height"),
            "fps": state["asset_snapshot"].get("fps"),
            "duration": state["asset_snapshot"].get("duration"),
            "frame_count": state["asset_snapshot"].get("frame_count"),
            "byte_size": state["asset_snapshot"].get("byte_size"),
        },
        "project_metadata": {
            "modality": state["project_snapshot"].get("modality", "image"),
            "goal": state["project_snapshot"].get("goal", ""),
            "video_config": state["project_snapshot"].get("video_config"),
        },
        "ontology": _project_spatial_ontology(state["project_snapshot"]),
        "requested_labels": spatial_labels,
        "spatial_labels": spatial_labels,
        "activity_labels": activity_labels,
        "event_labels": event_labels,
        "scene_evidence": state["project_snapshot"].get("scene_evidence", {}),
        "available_models": avail_map,
        "capability_gaps": gaps,
        "runtime_capabilities": state.get("runtime_capabilities", []),
        "human_feedback": state.get("human_feedback"),
        "reprocess_count": state.get("reprocess_count", 0),
        "intent": {
            "task": intent.task_type,
            "geometry": intent.geometry_type,
            "high_precision": intent.high_precision,
            "small_object_focus": intent.small_object_focus,
        },
    }
    planner_prompt = (
        "You are the authoritative detection execution planner. Return ONLY "
        "the canonical JSON plan: {decision_source:'agent', plan_version:'1', "
        "task_type, geometry, actions:[{model, strategy, labels, parameters, reason}]}. "
        "The runtime_capabilities list contains each available model's exact capabilities, "
        "supported geometry, and vocabulary. Use it as authoritative evidence before choosing models. "
        "Spatial object detectors (such as yolo26, dino, faster_rcnn) MUST ONLY be assigned spatial object labels (from spatial_labels). "
        "Do NOT assign temporal activity labels or temporal event labels to spatial object detectors. "
        "A model is only acceptable when it is both available and capable of the labels it is asked to cover.\n"
        "CRITICAL MODEL CAPABILITY & VOCABULARY GROUNDING RULES:\n"
        "1. Check each model's 'capabilities' and 'vocabulary' in runtime_capabilities.\n"
        "2. CLOSED-VOCABULARY MODELS (models WITHOUT 'open_vocab_detection' in capabilities, e.g. yolo26, faster_rcnn):\n"
        "   - The model has a fixed runtime vocabulary (listed in 'vocabulary').\n"
        "   - An action for a closed-vocabulary model MUST ONLY contain labels that appear verbatim (case-insensitive) in that model's runtime 'vocabulary'.\n"
        "   - NEVER assign a label to a closed-vocabulary model if it does NOT exist in that model's vocabulary!\n"
        "   - NEVER invent aliases, semantic mappings, or hypernyms (e.g. NEVER assign 'vehicle' to yolo26, because 'vehicle' is NOT in yolo26's vocabulary).\n"
        "3. OPEN-VOCABULARY MODELS (models WITH 'open_vocab_detection' in capabilities, e.g. dino):\n"
        "   - The model natively detects arbitrary open-world text concepts.\n"
        "   - Any requested spatial label that does not exist in a closed-set model's vocabulary (such as semantic labels like 'vehicle' or domain labels like 'traffic_sign') MUST be assigned to an open-vocabulary model (e.g. dino).\n"
        "   - Open-vocabulary detectors excel at detecting ALL requested spatial labels, including common concepts like 'car', 'bus', 'truck', 'person', 'motorcycle'.\n"
        "   - In complex, crowded, or low-light/night scenes, assign ALL target spatial classes to dino for comprehensive text-grounded detection coverage.\n"
        "4. When complementary detectors (e.g. yolo26 and dino) are both available:\n"
        "   - Assign valid closed-set classes to yolo26 for fast closed-set candidate generation.\n"
        "   - For dino, assign all target spatial classes (both open-set concepts and common classes) to ensure maximum recall. The downstream fusion layer will automatically merge overlapping detections across models.\n"
        "5. Technical validation will strictly reject any plan where an action assigns unsupported labels to a closed-set model.\n"
        "RECALL-FIRST EXECUTION POLICY:\n"
        "- The objective is to find as many requested objects as the evidence supports, not merely the easiest high-confidence objects. Preserve valid low-confidence candidates for quality review/HITL.\n"
        "- For crowded scenes, small objects, occlusion, aerial views, or a previous recall risk, prefer high_resolution_tiled or tiled inference with overlap so objects are not lost during resizing.\n"
        "- When complementary available detectors support the same requested labels, use more than one detector (for example yolo26 plus faster_rcnn) and let the merge/quality stages remove duplicates and resolve disagreement. Do not run an unavailable or vocabulary-incompatible model.\n"
        "- Use dino when configured labels are outside the closed-set vocabulary or when the evidence indicates open-vocabulary coverage is needed.\n"
        "- Select only the model actions justified by the task, ontology, scene evidence, and capability coverage. Never select all available models merely because they are available, and never force a three-model ensemble.\n"
        "Each action strategy MUST be exactly one of: full_image, high_resolution, "
        "tiled, high_resolution_tiled. Parameters may include image_size, tile_rows, "
        "tile_cols, tile_overlap. "
        "image_size is an inference configuration value and MUST be a single positive integer. "
        "Never return asset dimensions as [width,height] or any array/string. Asset dimensions are available only "
        "as asset_width and asset_height metadata. If no explicit resize is required, omit image_size."
    )
    planner_result = state.get("_planner_retry_result")
    if planner_result is None:
        planner_result = call_json_agent(
            system_prompt=planner_prompt,
            user_payload=planner_payload,
            settings=get_settings(),
            max_output_tokens=1000,
        )
    if not isinstance(planner_result, dict) or not planner_result:
        logger.warning(
            "agent_plan_retry",
            agent_run_id=state.get("audit_record").agent_run_id if state.get("audit_record") else None,
            asset_id=asset_id,
            reason="planning response was empty or not valid JSON",
        )
        planner_result = call_json_agent(
            system_prompt=planner_prompt + " Return a complete non-empty JSON object with at least one action.",
            user_payload=planner_payload,
            settings=get_settings(),
            max_output_tokens=1000,
        )
    planner_result = planner_result if isinstance(planner_result, dict) else {}
    audit = state.get("audit_record")
    agent_run_id = audit.agent_run_id if audit else None
    raw_strategy = planner_result.get("strategy")
    raw_actions = planner_result.get("actions")
    raw_models = planner_result.get("models")
    logger.info(
        "agent_plan_raw",
        agent_run_id=agent_run_id,
        batch_id=state.get("batch_id"),
        job_id=state.get("job_id"),
        asset_id=asset_id,
        task_type=intent.task_type,
        requested_labels=intent.requested_labels,
        raw_strategy=raw_strategy,
        selected_models=raw_models,
        plan_version=planner_result.get("plan_version"),
        response=planner_result,
    )

    for lbl in intent.requested_labels:
        logger.info(
            "agent_requested",
            label=lbl,
            task_type=intent.task_type,
            agent_run_id=agent_run_id,
            asset_id=asset_id,
        )

    strategy_aliases = {
        "full-image": "full_image",
        "full image": "full_image",
        "high-resolution": "high_resolution",
        "high resolution": "high_resolution",
        "tiled-image": "tiled",
        "high-resolution-tiled": "high_resolution_tiled",
    }
    supported_strategies = {"full_image", "high_resolution", "tiled", "high_resolution_tiled"}

    logger.info(
        "raw_gemini_plan",
        raw_plan=planner_result,
        agent_run_id=agent_run_id,
        asset_id=asset_id,
    )

    actions: list[dict[str, Any]] = []
    if isinstance(raw_actions, list) and raw_actions:
        for raw_action in raw_actions:
            if not isinstance(raw_action, dict):
                continue
            action = dict(raw_action)
            action["model"] = str(action.get("model") or "").strip()
            action_strategy = str(action.get("strategy") or raw_strategy or "").strip().lower()
            action["strategy"] = strategy_aliases.get(action_strategy, action_strategy)
            action["labels"] = [
                label for label in list(action.get("labels") if action.get("labels") is not None else intent.requested_labels)
                if not _is_excluded_ai_label(label)
            ]
            action_params = dict(action.get("parameters") or {})
            for p_key in ("image_size", "tile_rows", "tile_cols", "tile_overlap", "confidence_threshold"):
                if p_key not in action_params and p_key in planner_result:
                    action_params[p_key] = planner_result[p_key]
            action["parameters"] = action_params
            if action["labels"]:
                actions.append(action)
    else:
        shared_strategy = str(raw_strategy or "").strip().lower()
        shared_strategy = strategy_aliases.get(shared_strategy, shared_strategy)
        candidate_models = [str(m) for m in raw_models] if isinstance(raw_models, list) else []
        grounded_acts, _ = ground_labels_to_capabilities(
            requested_labels=intent.requested_labels,
            runtime_capabilities=state.get("runtime_capabilities", []),
            preferred_models=candidate_models,
            strategy=shared_strategy or "full_image",
            parameters={
                key: planner_result[key]
                for key in ("image_size", "tile_rows", "tile_cols", "tile_overlap", "confidence_threshold")
                if key in planner_result
            },
        )
        actions.extend(grounded_acts)

    # The agent may return syntactically valid JSON while accidentally
    # collapsing a multi-object requirement to one label.  Keep the agent as
    # the planning authority, but require its plan to cover the complete
    # requirement.  Any uncovered labels are assigned by the runtime
    # capability registry, which naturally produces e.g. YOLO26 + DINO.
    assigned_keys = {
        SAFE_ALIASES.get(str(label).strip().casefold(), str(label).strip().casefold())
        for action in actions
        for label in (action.get("labels") or [])
        if str(label).strip()
    }
    missing_labels = [
        label for label in intent.requested_labels
        if SAFE_ALIASES.get(str(label).strip().casefold(), str(label).strip().casefold()) not in assigned_keys
    ]
    if missing_labels:
        fallback_strategy = strategy_aliases.get(str(raw_strategy or "").strip().lower(), str(raw_strategy or "").strip().lower()) or "full_image"
        grounded_missing, unavailable_missing = ground_labels_to_capabilities(
            requested_labels=missing_labels,
            runtime_capabilities=state.get("runtime_capabilities", []),
            strategy=fallback_strategy,
            parameters={
                key: planner_result[key]
                for key in ("image_size", "tile_rows", "tile_cols", "tile_overlap", "confidence_threshold")
                if key in planner_result
            },
        )
        actions.extend(grounded_missing)
        logger.info(
            "agent_plan_requirement_coverage_completed",
            requested_labels=intent.requested_labels,
            missing_labels=missing_labels,
            grounded_actions=grounded_missing,
            unavailable_labels=unavailable_missing,
            agent_run_id=agent_run_id,
            asset_id=asset_id,
        )

    selected_models = list(dict.fromkeys(action["model"] for action in actions if action["model"]))
    if not selected_models:
        grounded_acts, _ = ground_labels_to_capabilities(
            requested_labels=intent.requested_labels,
            runtime_capabilities=state.get("runtime_capabilities", []),
            strategy="full_image",
        )
        actions = grounded_acts
        selected_models = list(dict.fromkeys(action["model"] for action in actions if action["model"]))

    caps_by_model: dict[str, dict[str, Any]] = {}
    for cap in state.get("runtime_capabilities", []):
        if isinstance(cap, dict) and cap.get("model_key"):
            caps_by_model[str(cap["model_key"])] = cap

    invalid_reason = None
    unsupported_assignments: list[dict[str, Any]] = []

    if not selected_models:
        invalid_reason = "Agent returned no execution actions"
    elif any(not avail_map.get(model, False) for model in selected_models):
        unavailable = [m for m in selected_models if not avail_map.get(m, False)]
        invalid_reason = f"Agent selected unavailable models: {unavailable}"
    elif any(action["strategy"] not in supported_strategies for action in actions):
        invalid_reason = "Agent returned an unsupported execution strategy"
    else:
        for action in actions:
            parameters = action["parameters"]
            if "image_size" in parameters and (
                not isinstance(parameters["image_size"], int)
                or isinstance(parameters["image_size"], bool)
                or parameters["image_size"] <= 0
            ):
                invalid_reason = "parameters.image_size must be a positive integer"
                break

        # Capability & Vocabulary Grounding Validation against runtime capability metadata
        if not invalid_reason:
            is_valid, records, invalid_reasons = validate_plan_grounding(
                actions=actions,
                runtime_capabilities=state.get("runtime_capabilities", []),
                agent_run_id=agent_run_id,
                asset_id=asset_id,
            )
            if not is_valid:
                unsupported_assignments = invalid_reasons
                details = "; ".join(
                    f"model '{item.get('model')}' does not support label '{item.get('label') or (', '.join(map(str, item.get('labels', []))) if item.get('labels') else 'unknown')}'"
                    for item in invalid_reasons
                )
                invalid_reason = (
                    f"Runtime capability grounding mismatch: {details}. "
                    f"Closed-vocabulary models can ONLY be assigned labels that exist exactly in their runtime vocabulary. "
                    f"Labels that do not exist in the closed vocabulary must be assigned to an open-vocabulary model or omitted."
                )

    if invalid_reason and not state.get("_planner_retry_attempted"):
        logger.warning(
            "replan",
            unresolved_labels=[
                r.get("label") or (", ".join(map(str, r.get("labels", []))) if r.get("labels") else "")
                for r in unsupported_assignments
            ],
            reason="not_in_runtime_vocabulary",
            invalid_reason=invalid_reason,
            unsupported_assignments=unsupported_assignments,
            agent_run_id=agent_run_id,
            asset_id=asset_id,
            raw_plan=planner_result,
        )
        correction_prompt = (
            planner_prompt
            + f"\n\nCRITICAL REPLANNING INSTRUCTION:\n"
            f"Your previous plan was REJECTED by technical validation:\n"
            f"{invalid_reason}\n\n"
            f"Grounding requirements:\n"
            f"1. For CLOSED-VOCABULARY models (e.g. yolo26): only assign labels that appear in that model's runtime vocabulary. Never assign ungrounded labels (e.g. never assign 'vehicle' to yolo26).\n"
            f"2. For OPEN-VOCABULARY models (e.g. dino): assign any requested labels that are not supported by closed-vocabulary models (e.g. 'vehicle', 'traffic_sign').\n"
            f"3. Parameters must be valid (e.g. image_size must be a single positive integer or omitted).\n"
            f"Return ONLY the corrected valid canonical JSON plan."
        )
        corrected_result = call_json_agent(
            system_prompt=correction_prompt,
            user_payload={
                **planner_payload,
                "previous_invalid_plan": planner_result,
                "validation_error": invalid_reason,
                "unsupported_assignments": unsupported_assignments,
            },
            settings=get_settings(),
            max_output_tokens=1000,
        )
        if isinstance(corrected_result, dict) and corrected_result:
            return await create_execution_plan_node({
                **state,
                "_planner_retry_result": corrected_result,
                "_planner_retry_attempted": True,
            })
        else:
            # Fallback to dynamic capability grounding if replan returned invalid/empty response
            grounded_actions, _ = ground_labels_to_capabilities(
                requested_labels=intent.requested_labels,
                runtime_capabilities=state.get("runtime_capabilities", []),
                preferred_models=selected_models,
            )
            actions = grounded_actions
            selected_models = list(dict.fromkeys(a["model"] for a in actions))
            if actions:
                invalid_reason = None
            else:
                invalid_reason = "No available model can detect the requested labels"

    if invalid_reason:
        # Fallback to dynamic capability grounding before failing
        grounded_actions, _ = ground_labels_to_capabilities(
            requested_labels=intent.requested_labels,
            runtime_capabilities=state.get("runtime_capabilities", []),
            preferred_models=[m for m in selected_models if avail_map.get(m, False)],
        )
        if grounded_actions:
            actions = grounded_actions
            selected_models = list(dict.fromkeys(a["model"] for a in actions))
            invalid_reason = None

    if not actions:
        # Graceful fallback: assign default available detector (e.g. yolo26)
        default_detector = None
        for cand in ("yolo26", "faster_rcnn"):
            if avail_map.get(cand, False):
                default_detector = cand
                break
        if default_detector:
            actions = [{
                "model": default_detector,
                "strategy": "full_image",
                "labels": [lbl for lbl in intent.requested_labels if not _is_excluded_ai_label(lbl)] or ["object"],
                "parameters": {},
                "reason": f"Fallback to available detector {default_detector}",
            }]
            selected_models = [default_detector]
            invalid_reason = None
        else:
            invalid = {
                "status": "AGENT_PLAN_INVALID",
                "reason": invalid_reason or "No execution actions available",
                "raw_strategy": raw_strategy,
                "supported_strategies": sorted(supported_strategies),
                "agent_run_id": agent_run_id,
                "raw_plan": planner_result,
                "unsupported_assignments": unsupported_assignments,
            }
            logger.error("agent_plan_invalid", **invalid)
            return {"agent_plan_invalid": invalid}

    strategy = actions[0]["strategy"]
    first_parameters = actions[0]["parameters"]
    image_size = first_parameters.get("image_size") or planner_result.get("image_size")
    tile_rows = first_parameters.get("tile_rows") or planner_result.get("tile_rows")
    tile_cols = first_parameters.get("tile_cols") or planner_result.get("tile_cols")
    tile_overlap = first_parameters.get("tile_overlap") or planner_result.get("tile_overlap")

    for act in actions:
        p = act.setdefault("parameters", {})
        if image_size is not None and "image_size" not in p:
            p["image_size"] = image_size
        if tile_rows is not None and "tile_rows" not in p:
            p["tile_rows"] = tile_rows
        if tile_cols is not None and "tile_cols" not in p:
            p["tile_cols"] = tile_cols
        if tile_overlap is not None and "tile_overlap" not in p:
            p["tile_overlap"] = tile_overlap

    # Final validation check: enforce valid grounding
    is_valid, records, invalid_reasons = validate_plan_grounding(
        actions=actions,
        runtime_capabilities=state.get("runtime_capabilities", []),
        agent_run_id=agent_run_id,
        asset_id=asset_id,
    )
    if not is_valid:
        # Final fallback to dynamic capability grounding if models failed final check
        grounded_actions, _ = ground_labels_to_capabilities(
            requested_labels=intent.requested_labels,
            runtime_capabilities=state.get("runtime_capabilities", []),
        )
        if grounded_actions:
            actions = grounded_actions
            selected_models = list(dict.fromkeys(a["model"] for a in actions))
            is_valid, records, invalid_reasons = validate_plan_grounding(
                actions=actions,
                runtime_capabilities=state.get("runtime_capabilities", []),
                agent_run_id=agent_run_id,
                asset_id=asset_id,
            )
        if not is_valid:
            invalid = {
                "status": "AGENT_PLAN_INVALID",
                "reason": "Final execution plan contains ungrounded labels",
                "unsupported_assignments": invalid_reasons,
                "agent_run_id": agent_run_id,
                "actions": actions,
            }
            logger.error("agent_plan_invalid", **invalid)
            return {"agent_plan_invalid": invalid}

    plan = {
        "task": intent.task_type,
        "requested_labels": intent.requested_labels,
        "resolved_detection_labels": list(dict.fromkeys(
            str(label).strip()
            for action in actions
            for label in (action.get("labels") or [])
            if not _is_excluded_ai_label(label)
        )),
        "geometry": intent.geometry_type,
        "candidate_models": [],
        "models": selected_models,
        "actions": actions,
        "strategy": strategy,
        "image_size": image_size,
        "tile_rows": tile_rows,
        "tile_cols": tile_cols,
        "tile_overlap": tile_overlap,
        "verification_required": bool(planner_result.get("verification_required", True)),
        "selected_tools": [str(tool) for tool in planner_result.get("selected_tools", [])],
        "high_precision": intent.high_precision,
        "small_object_focus": intent.small_object_focus,
        "reasoning_summary": intent.reasoning,
        "capability_gaps": gaps,
    }
    plan_ms = (time.perf_counter() - t0) * 1000.0
    
    timings = dict(state.get("timings", {}))
    timings["agent_planning_ms"] = plan_ms
    
    logger.info(
        "agent_plan_created",
        task=plan["task"],
        geometry=plan["geometry"],
        selected_models=selected_models,
        selected_tools=plan["selected_tools"],
        reason=intent.reasoning,
        strategy=strategy,
        image_size=image_size,
        tile_rows=tile_rows,
        tile_cols=tile_cols,
        decision_source="agent",
        agent_run_id=agent_run_id,
        asset_id=asset_id,
        batch_id=state.get("batch_id"),
        job_id=state.get("job_id"),
    )
    logger.info(
        "agent_model_combination_selected",
        project_id=project_id,
        asset_id=asset_id,
        agent_run_id=agent_run_id,
        selected_models=selected_models,
        requested_labels=intent.requested_labels,
        resolved_detection_labels=intent.requested_labels,
        reason="; ".join(str(action.get("reason") or "") for action in actions),
    )
    logger.info(
        "agent_model_selection_reason",
        project_id=project_id,
        asset_id=asset_id,
        agent_run_id=agent_run_id,
        selected_models=selected_models,
        requested_labels=intent.requested_labels,
        reason="; ".join(str(action.get("reason") or "") for action in actions),
    )
    logger.info(
        "agent_plan_validated",
        validation="technical",
        selected_models=selected_models,
        actual_models=selected_models,
        decision_source="technical_validator",
        agent_run_id=agent_run_id,
        asset_id=asset_id,
        batch_id=state.get("batch_id"),
        job_id=state.get("job_id"),
    )
    logger.info(
        "final_grounded_execution_plan",
        models=selected_models,
        actions=actions,
        strategy=strategy,
        image_size=image_size,
        agent_run_id=agent_run_id,
        asset_id=asset_id,
    )
    for action in actions:
        m_key = action["model"]
        m_cap = caps_by_model.get(m_key, {})
        m_caps = [str(c).lower() for c in m_cap.get("capabilities", [])]
        is_open = "open_vocab_detection" in m_caps or "open_vocabulary_detection" in m_caps
        logger.info(
            "capability_grounding_resolved",
            model=m_key,
            model_type="open_vocabulary" if is_open else "closed_vocabulary",
            assigned_labels=action["labels"],
            strategy=action["strategy"],
            decision_source="grounded_planner",
            agent_run_id=agent_run_id,
            asset_id=asset_id,
        )
    
    if audit:
        audit.execution_plan = plan
        audit.selected_models = selected_models
        audit.selected_tools = plan["selected_tools"]
        audit.log_event("create_execution_plan", plan)
        
    return {"execution_plan": plan, "timings": timings}


async def execute_model_node(state: PipelineState) -> PipelineState:
    plan = state["execution_plan"]
    storage = state["storage"]
    runtime = state["runtime"]
    avail_map = state.get("available_models", {})
    asset_id = state.get("asset_id") or state["asset_snapshot"].get("id")
    project_id = state.get("project_id") or state["project_snapshot"].get("id")

    if state["project_snapshot"].get("modality") in {"text", "document"}:
        from app.services.text_capability import TextCapabilityService, normalize_text_task, resolve_text_target_labels
        text_path = storage.resolve(state["asset_snapshot"].get("storage_path", ""))
        raw_task = plan.get("task_type") or plan.get("task") or state["project_snapshot"].get("task_type") or "ENTITY_EXTRACTION"
        norm_task, capability = normalize_text_task(raw_task)
        selected_model = str(plan.get("models", [capability])[0])
        labels = list(plan.get("requested_labels") or [])
        entity_labels = list(plan.get("entity_labels") or [])
        if not labels:
            labels = resolve_text_target_labels(state["project_snapshot"], norm_task)
        logger.info(
            "text_execution_labels",
            graph_target_objects=state["project_snapshot"].get("target_objects"),
            requested_labels=labels,
            selected_tools=plan.get("models", []),
            task=norm_task,
            capability=capability,
        )
        result = await TextCapabilityService().execute(
            path=text_path,
            task_type=norm_task,
            labels=labels,
            asset_id=str(asset_id),
            model_id=selected_model,
            entity_labels=entity_labels,
            analysis_level=str(
                state["project_snapshot"].get(
                    "sentiment_analysis_level" if norm_task == "SENTIMENT_ANALYSIS" else "classification_analysis_level"
                ) or "document"
            ),
        )
        errors = list(result.get("errors", []))
        ann_count = len(result.get("annotations", []))
        logger.info(
            "text_execution_started",
            task=norm_task,
            capability=selected_model,
            service=selected_model,
            project_id=project_id,
            asset_id=asset_id,
            requested_labels=labels,
        )
        logger.info(
            "text_execution_dispatch",
            capability=selected_model,
            task_type=norm_task,
            asset_id=str(asset_id),
            requested_labels=labels,
            selected_model=selected_model,
            annotation_count=ann_count,
            persistence_count=ann_count,
            errors=errors,
        )
        logger.info(
            "text_execution_completed",
            task=norm_task,
            capability=selected_model,
            annotation_count=ann_count,
            errors=errors,
        )
        if state.get("audit_record"):
            state["audit_record"].log_event("execute_text_capability", {
                "capability": selected_model,
                "task_type": norm_task,
                "asset_id": str(asset_id),
                "requested_labels": labels,
                "annotation_count": ann_count,
                "errors": errors,
            })
        return {"text_result": result, "text_annotations": result.get("annotations", []), "raw_detections": [], "merged_detections": [], "masks": [], "models_executed": [selected_model], "execution_models": [selected_model], "execution_errors": errors, "execution_failed": bool(errors), "execution_history": list(state.get("execution_history", [])) + [{"execution_id": f"{asset_id}:text:{len(state.get('execution_history', [])) + 1}", "models": [selected_model], "result_count": ann_count, "errors": errors}], "timings": {**state.get("timings", {})}}

    
    image_path = storage.resolve(state["asset_snapshot"]["storage_path"])
    candidate_models = list(plan.get("models", []))
    requested_labels = plan.get("requested_labels", [])

    # A retry is allowed to reuse a model only when the planner selected a
    # genuinely different strategy.  This prevents accidental duplicate
    # inference while preserving intentional full-image -> tiled retries.
    history = list(state.get("execution_history", []))
    planned_actions = {
        str(action.get("model")): str(action.get("strategy") or plan.get("strategy") or "full_image")
        for action in plan.get("actions", []) if isinstance(action, dict)
    }
    prior_keys = {
        (str(item.get("model")), str(item.get("strategy") or "full_image"))
        for item in history
    }
    duplicate_models = [
        model for model in candidate_models
        if (model, planned_actions.get(model, str(plan.get("strategy") or "full_image"))) in prior_keys
    ]
    if duplicate_models:
        candidate_models = [model for model in candidate_models if model not in duplicate_models]
        logger.info(
            "duplicate_model_execution_prevented",
            asset_id=asset_id,
            skipped_models=duplicate_models,
            execution_history=history,
        )
    
    # Execute exactly what the agent plan specified — technically validate only.
    # NEVER inject a model the agent did not choose.
    # NEVER add a default model when the plan is empty.
    unavailable_models = [
        model for model in candidate_models
        if not avail_map.get(model, False) or not runtime.registry.try_load(model)
    ]
    execution_models: list[str] = list(candidate_models)

    if not execution_models or unavailable_models:
        # Technical validation rejects the complete plan. It never removes a
        # model and executes the remainder.
        logger.error(
            "agent_plan_invalid",
            status="AGENT_PLAN_INVALID",
            reason="Agent plan selected unavailable or unloadable models",
            candidate_models=candidate_models,
            unavailable_models=unavailable_models,
            project_id=project_id,
            asset_id=asset_id,
        )
        return {
            "raw_detections": [],
            "merged_detections": [],
            "masks": [],
            "execution_models": [],
            "models_executed": [],
            "agent_plan_invalid": {
                "status": "AGENT_PLAN_INVALID",
                "reason": "Agent plan selected unavailable or unloadable models",
                "unavailable_models": unavailable_models,
                "agent_run_id": state.get("audit_record").agent_run_id if state.get("audit_record") else None,
            },
        }

    logger.info(
        "model_execution_started",
        project_id=project_id,
        asset_id=asset_id,
        models=execution_models,
    )
    logger.info(
        "agent_action_selected",
        candidate_models=candidate_models,
        execution_models=execution_models,
        selected_models=execution_models,
        selected_tools=plan.get("selected_tools", []),
    )
    execution_id = f"{state.get('audit_record').agent_run_id if state.get('audit_record') else asset_id}:execution:{len(history) + 1}"
    pipeline_execution_id = execution_id
    
    all_detections: list[Any] = []
    executed_models: list[str] = []
    execution_errors: list[dict[str, Any]] = []
    timings: dict[str, float] = dict(state.get("timings", {}))
    action_by_model = {
        str(action.get("model")): action
        for action in plan.get("actions", [])
        if isinstance(action, dict)
    }
    agent_run_id = state.get("audit_record").agent_run_id if state.get("audit_record") else None
    prior_models = [
        str(model)
        for item in history
        for model in (item.get("models", []) if isinstance(item, dict) else [])
    ]

    if state["project_snapshot"].get("modality") == "video":
        logger.info(
            "selected_video_capabilities_executed",
            asset_id=asset_id,
            capabilities=plan.get("required_capabilities"),
            models=plan.get("models"),
        )
        t_vid_start = time.perf_counter()
        import cv2
        import tempfile
        from app.models.video_asset import VideoAsset
        from app.models.video_frame import VideoFrame
        from app.video.pipeline.video_pipeline import VideoPipeline

        video_path = storage.resolve(state["asset_snapshot"]["storage_path"])
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file {video_path}")
        
        width = state["asset_snapshot"].get("width") or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = state["asset_snapshot"].get("height") or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = state["asset_snapshot"].get("fps") or cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = state["asset_snapshot"].get("frame_count") or int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = state["asset_snapshot"].get("duration") or (frame_count / fps if fps > 0 else 0.0)

        video_model = VideoAsset(
            id=asset_id,
            name=str(video_path.name),
            file_path=str(video_path),
            fps=fps,
            duration=duration,
            width=width,
            height=height,
            total_frames=frame_count,
        )

        frames: list[VideoFrame] = []
        frame_idx = 0
        temp_dir = Path(tempfile.mkdtemp(prefix="vid_frames_"))
        
        try:
            stride = plan.get("sampling_stride", 1)
            while cap.isOpened():
                ret, frame_img = cap.read()
                if not ret:
                    break
                if frame_idx % stride == 0:
                    frame_path = temp_dir / f"frame_{frame_idx:06d}.jpg"
                    cv2.imwrite(str(frame_path), frame_img)
                    ts_ms = (frame_idx / fps) * 1000.0 if fps > 0 else 0.0
                    frames.append(VideoFrame(
                        video_id=asset_id,
                        frame_index=frame_idx,
                        timestamp_ms=ts_ms,
                        timestamp_str=f"00:00:{int(ts_ms/1000):02d}:{frame_idx%int(fps)}",
                        file_path=str(frame_path),
                        width=width,
                        height=height,
                    ))
                frame_idx += 1
        finally:
            cap.release()

        pipeline = VideoPipeline()
        target_spatial_labels = plan.get("spatial_labels") or state["project_snapshot"].get("labels", [])
        
        pipeline_res = pipeline.run(
            video=video_model,
            frames=frames,
            plan=plan,
            target_labels=target_spatial_labels,
            runtime=runtime,
        )

        for f in frames:
            if f.file_path and Path(f.file_path).exists():
                try:
                    Path(f.file_path).unlink()
                except Exception:
                    pass
        if temp_dir.exists():
            try:
                temp_dir.rmdir()
            except Exception:
                pass

        logger.info(
            "temporal_processing_where_required",
            asset_id=asset_id,
            num_tracks=len(pipeline_res.get("tracks", [])),
            num_activities=len(pipeline_res.get("activities", [])),
            num_events=len(pipeline_res.get("events", [])),
            qa_score=pipeline_res.get("temporal_qa", {}).get("qa_score"),
        )
        logger.info(
            "temporal_processing_completed",
            asset_id=asset_id,
            num_tracks=len(pipeline_res.get("tracks", [])),
            num_activities=len(pipeline_res.get("activities", [])),
            num_events=len(pipeline_res.get("events", [])),
            qa_score=pipeline_res.get("temporal_qa", {}).get("qa_score"),
        )

        raw_dets = pipeline_res.get("detections", [])
        normalized_video_dets = []
        for d in raw_dets:
            conf = float(d.confidence)
            normalized_video_dets.append(NormalizedDetection(
                label=d.label,
                confidence=conf,
                bbox=[float(x) for x in d.bbox],
                geometry_type=GeometryType.BOX.value,
                source=d.source or "yolo26",
                asset_id=asset_id,
                metadata={
                    "frame_index": d.frame_index,
                    "track_id": d.track_id,
                    "timestamp_ms": d.attributes.get("timestamp_ms", 0.0),
                }
            ))

        vid_exec_ms = (time.perf_counter() - t_vid_start) * 1000.0
        timings = dict(state.get("timings", {}))
        timings["video_execution_ms"] = vid_exec_ms

        return {
            "raw_detections": normalized_video_dets,
            "merged_detections": normalized_video_dets,
            "video_tracks": pipeline_res.get("tracks", []),
            "video_activities": pipeline_res.get("activities", []),
            "video_events": pipeline_res.get("events", []),
            "video_masks": pipeline_res.get("segmentations", []),
            "video_keypoints": pipeline_res.get("keypoints", []),
            "temporal_qa": pipeline_res.get("temporal_qa", {}),
            "execution_models": list(set(plan.get("models", []))),
            "models_executed": list(dict.fromkeys(prior_models + list(set(plan.get("models", []))))),
            "execution_id": execution_id,
            "execution_history": history + [
                {"execution_id": execution_id, "models": list(set(plan.get("models", []))),
                 "actions": list(plan.get("actions", [])), "result_count": len(normalized_video_dets),
                 "errors": []}
            ],
            "timings": timings,
        }
    
    # 1. Closed-set pass (YOLO26 / Faster R-CNN)
    if ModelKey.YOLO26.value in execution_models:
        t0 = time.perf_counter()
        action = action_by_model.get(ModelKey.YOLO26.value, {})
        action_parameters = action.get("parameters", {})
        action_strategy = action.get("strategy", plan.get("strategy"))
        action_labels = list(action.get("labels") if action.get("labels") is not None else requested_labels)
        
        # Grounding check: strictly verify labels against runtime vocabulary before adapter invocation
        caps_by_model = {str(c.get("model_key")): c for c in state.get("runtime_capabilities", []) if isinstance(c, dict)}
        yolo_vocab = {str(v).strip().casefold() for v in caps_by_model.get("yolo26", {}).get("vocabulary", [])}
        if yolo_vocab:
            unsupported = []
            for lbl in action_labels:
                clean_cf = str(lbl).strip().casefold()
                clean_stem = clean_cf.rstrip("s")
                alias = SAFE_ALIASES.get(clean_cf, clean_cf).casefold()
                alias_stem = alias.rstrip("s")
                if not (
                    clean_cf in yolo_vocab
                    or clean_stem in yolo_vocab
                    or alias in yolo_vocab
                    or alias_stem in yolo_vocab
                ):
                    unsupported.append(lbl)
            if unsupported:
                raise ValueError(
                    f"Execution action for closed-vocabulary model 'yolo26' contains unsupported labels: {unsupported}. "
                    f"Execution layer strictly rejects ungrounded labels."
                )

        execution_id = f"{pipeline_execution_id}:yolo26"
        logger.info(
            "model_execution_grounded",
            model="yolo26",
            requested_labels=requested_labels,
            selected_model="yolo26",
            model_supported_labels=action_labels,
            strategy=action_strategy,
            asset_id=asset_id,
        )
        logger.info("agent_plan_executing", agent_run_id=agent_run_id, execution_id=execution_id, model="yolo26", strategy=action_strategy, requested_labels=action_labels)
        logger.info("execution_started", agent_run_id=agent_run_id, execution_id=execution_id, project_id=project_id, asset_id=asset_id, batch_id=state.get("batch_id"), job_id=state.get("job_id"), model="yolo26", strategy=action_strategy, requested_labels=action_labels)
        raw_img_size = action_parameters.get("image_size", plan.get("image_size"))
        if isinstance(raw_img_size, (list, tuple)):
            safe_image_size = int(raw_img_size[0]) if raw_img_size else None
        elif raw_img_size is not None:
            try:
                safe_image_size = int(raw_img_size)
            except (ValueError, TypeError):
                safe_image_size = None
        else:
            safe_image_size = None

        logger.info(
            "actual_adapter_requested_labels",
            model="yolo26",
            requested_labels=action_labels,
            strategy=action_strategy,
            image_size=safe_image_size,
            asset_id=asset_id,
        )

        raw_tile_rows = action_parameters.get("tile_rows", plan.get("tile_rows", 1))
        if isinstance(raw_tile_rows, (list, tuple)):
            safe_tile_rows = int(raw_tile_rows[0]) if raw_tile_rows else 1
        else:
            try:
                safe_tile_rows = int(raw_tile_rows)
            except (ValueError, TypeError):
                safe_tile_rows = 1

        raw_tile_cols = action_parameters.get("tile_cols", plan.get("tile_cols", 1))
        if isinstance(raw_tile_cols, (list, tuple)):
            safe_tile_cols = int(raw_tile_cols[0]) if raw_tile_cols else 1
        else:
            try:
                safe_tile_cols = int(raw_tile_cols)
            except (ValueError, TypeError):
                safe_tile_cols = 1

        raw_tile_overlap = action_parameters.get("tile_overlap", plan.get("tile_overlap", 0.0))
        if isinstance(raw_tile_overlap, (list, tuple)):
            safe_tile_overlap = float(raw_tile_overlap[0]) if raw_tile_overlap else 0.0
        else:
            try:
                safe_tile_overlap = float(raw_tile_overlap)
            except (ValueError, TypeError):
                safe_tile_overlap = 0.0

        try:
            dets = await asyncio.to_thread(
                runtime.detect,
                ModelKey.YOLO26.value,
                image_path,
                asset_id=asset_id,
                labels=action_labels,
                execution_options={
                    "execution_id": execution_id,
                    "job_id": state.get("job_id"),
                    "job_item_id": state.get("job_item_id"),
                    "strategy": action_strategy,
                    "image_size": safe_image_size,
                    "tile_rows": safe_tile_rows,
                    "tile_cols": safe_tile_cols,
                    "tile_overlap": safe_tile_overlap,
                    "confidence_threshold": action_parameters.get("confidence_threshold"),
                    "plan_source": "agent",
                    "plan_reason": plan.get("reasoning_summary", ""),
                },
            )
            dets = _validate_execution_results(
                dets,
                asset_id=asset_id,
                execution_id=execution_id,
                model=ModelKey.YOLO26.value,
                state=state,
            )
            all_detections.extend(dets)
            executed_models.append(ModelKey.YOLO26.value)
            log_pipeline_event(
                "raw_detection_result",
                project_id=project_id,
                asset_id=asset_id,
                agent_run_id=state.get("audit_record").agent_run_id if state.get("audit_record") else None,
                execution_id=execution_id,
                model=ModelKey.YOLO26.value,
                count=len(dets),
            )
            logger.info("raw_detection_count", model="yolo26", count=len(dets), asset_id=asset_id)
            logger.info("normalized_detection_count", model="yolo26", count=len(dets), asset_id=asset_id)
            logger.info("filtered_detection_count", model="yolo26", count=len(dets), asset_id=asset_id)
            logger.info(
                "model_inference_diagnostic",
                model="yolo26",
                raw_result_count=len(dets),
                normalized_result_count=len(dets),
                state_result_count=len(all_detections),
            )
            logger.info("model_execution_result", model="yolo26", strategy=action_strategy, detection_count=len(dets), labels=sorted({d.label for d in dets}), confidence_min=min((d.confidence for d in dets), default=None), confidence_max=max((d.confidence for d in dets), default=None), confidence_mean=(sum(d.confidence for d in dets) / len(dets) if dets else None))
        except Exception as exc:
            execution_errors.append({"model": "yolo26", "error": str(exc)})
            logger.exception("execution_failed", model="yolo26", error=str(exc))
        timings["yolo_ms"] = (time.perf_counter() - t0) * 1000.0
        if not execution_errors:
            logger.info("detection_completed", model="yolo26", count=len(dets))

    if ModelKey.FASTER_RCNN.value in execution_models:
        t0 = time.perf_counter()
        action = action_by_model.get(ModelKey.FASTER_RCNN.value, {})
        action_parameters = action.get("parameters", {})
        execution_id = f"{pipeline_execution_id}:faster_rcnn"
        logger.info("detection_started", model="faster_rcnn", asset_id=asset_id)
        try:
            faster_labels = list(action.get("labels") if action.get("labels") is not None else requested_labels)
            dets = await asyncio.to_thread(
                runtime.detect,
                ModelKey.FASTER_RCNN.value,
                image_path,
                asset_id=asset_id,
                labels=faster_labels,
                execution_options={
                    "execution_id": execution_id,
                    "job_id": state.get("job_id"),
                    "job_item_id": state.get("job_item_id"),
                    "confidence_threshold": action_parameters.get("confidence_threshold"),
                },
            )
            dets = _validate_execution_results(
                dets,
                asset_id=asset_id,
                execution_id=execution_id,
                model=ModelKey.FASTER_RCNN.value,
                state=state,
            )
            all_detections.extend(dets)
            executed_models.append(ModelKey.FASTER_RCNN.value)
            logger.info("raw_detection_count", model="faster_rcnn", count=len(dets), asset_id=asset_id)
            logger.info("normalized_detection_count", model="faster_rcnn", count=len(dets), asset_id=asset_id)
            logger.info("filtered_detection_count", model="faster_rcnn", count=len(dets), asset_id=asset_id)
            logger.info(
                "model_inference_diagnostic",
                model="faster_rcnn",
                raw_result_count=len(dets),
                normalized_result_count=len(dets),
                state_result_count=len(all_detections),
            )
        except Exception as exc:
            execution_errors.append({"model": "faster_rcnn", "error": str(exc)})
            logger.exception("execution_failed", model="faster_rcnn", error=str(exc))
        timings["faster_rcnn_ms"] = (time.perf_counter() - t0) * 1000.0
        if not execution_errors:
            logger.info("detection_completed", model="faster_rcnn", count=len(dets))
            
    # 2. Open-vocabulary pass (Grounding DINO)
    if ModelKey.DINO.value in execution_models:
        t0 = time.perf_counter()
        action = action_by_model.get(ModelKey.DINO.value, {})
        action_strategy = action.get("strategy", plan.get("strategy"))
        from app.inference.ontology_map import is_invalid_workflow_label
        raw_action_labels = list(action.get("labels") if action.get("labels") is not None else requested_labels or [])
        action_labels = [
            l for l in raw_action_labels
            if l and not is_invalid_workflow_label(str(l))
        ]
        if not action_labels:
            action_labels = list(state["project_snapshot"].get("labels", []))
        execution_id = f"{pipeline_execution_id}:dino"
        logger.info(
            "model_execution_grounded",
            model="dino",
            requested_labels=requested_labels,
            selected_model="dino",
            model_supported_labels=action_labels,
            strategy=action_strategy,
            asset_id=asset_id,
        )
        logger.info(
            "actual_adapter_requested_labels",
            model="dino",
            requested_labels=action_labels,
            strategy=action_strategy,
            asset_id=asset_id,
        )
        logger.info("execution_started", agent_run_id=agent_run_id, execution_id=execution_id, project_id=project_id, asset_id=asset_id, batch_id=state.get("batch_id"), job_id=state.get("job_id"), model="dino", strategy=action_strategy, requested_labels=action_labels)
        try:
            dets = await asyncio.to_thread(
                runtime.detect,
                ModelKey.DINO.value,
                image_path,
                asset_id=asset_id,
                labels=action_labels,
                execution_options={
                    "execution_id": execution_id,
                    "job_id": state.get("job_id"),
                    "job_item_id": state.get("job_item_id"),
                    "confidence_threshold": (action.get("parameters") or {}).get("confidence_threshold"),
                },
            )
            dets = _validate_execution_results(
                dets,
                asset_id=asset_id,
                execution_id=execution_id,
                model=ModelKey.DINO.value,
                state=state,
            )
            all_detections.extend(dets)
            executed_models.append(ModelKey.DINO.value)
            logger.info("raw_detection_count", model="dino", count=len(dets), asset_id=asset_id)
            logger.info("normalized_detection_count", model="dino", count=len(dets), asset_id=asset_id)
            logger.info("filtered_detection_count", model="dino", count=len(dets), asset_id=asset_id)
            logger.info(
                "model_inference_diagnostic",
                model="dino",
                raw_result_count=len(dets),
                normalized_result_count=len(dets),
                state_result_count=len(all_detections),
            )
            logger.info("model_execution_result", model="dino", strategy=action_strategy, detection_count=len(dets), labels=sorted({d.label for d in dets}), confidence_min=min((d.confidence for d in dets), default=None), confidence_max=max((d.confidence for d in dets), default=None), confidence_mean=(sum(d.confidence for d in dets) / len(dets) if dets else None))
        except Exception as exc:
            execution_errors.append({"model": "dino", "error": str(exc)})
            logger.exception("execution_failed", model="dino", error=str(exc))
        timings["dino_ms"] = (time.perf_counter() - t0) * 1000.0
        if not execution_errors:
            logger.info("detection_completed", model="dino", count=len(dets))
            
    # 3. Merge detections deterministically
    t0 = time.perf_counter()
    resolved_detection_labels = list(dict.fromkeys(
        str(label).strip()
        for action in (plan.get("actions") or [])
        for label in (action.get("labels") or [])
        if not _is_excluded_ai_label(label)
    ))
    logger.info(
        "multi_model_fusion_started",
        project_id=project_id,
        asset_id=asset_id,
        agent_run_id=agent_run_id,
        selected_models=execution_models,
        requested_labels=requested_labels,
        resolved_detection_labels=resolved_detection_labels,
        raw_count=len(all_detections),
    )
    action_scope_labels = [
        str(label).strip()
        for action in (plan.get("actions") or [])
        for label in (action.get("labels") or [])
        if not _is_excluded_ai_label(label)
    ]
    ontology = list(dict.fromkeys([
        *_project_spatial_ontology(state["project_snapshot"]),
        *((plan.get("requested_labels") or []) if isinstance(plan, dict) else []),
        *action_scope_labels,
    ]))
    onto_index = build_ontology_index(
        ontology,
        ontology=list(state["project_snapshot"].get("label_ontology") or []),
    )
    
    merged, merge_stats = merge_detections(
        detections=all_detections,
        index=onto_index,
    )
    merged, final_duplicate_count = _final_same_label_deduplicate(
        merged,
        iou_threshold=float(get_settings().duplicate_iou_threshold),
    )
    fusion_ms = (time.perf_counter() - t0) * 1000.0
    timings["fusion_ms"] = fusion_ms
    fusion_dict = stats_to_dict(merge_stats)
    fusion_conflicts = list(fusion_dict.get("conflict_records") or [])
    logger.info("fusion_completed", **fusion_dict, fusion_ms=fusion_ms)
    logger.info(
        "multi_model_fusion_completed",
        project_id=project_id,
        asset_id=asset_id,
        agent_run_id=agent_run_id,
        selected_models=execution_models,
        requested_labels=requested_labels,
        resolved_detection_labels=resolved_detection_labels,
        raw_count=len(all_detections),
        fused_count=len(merged),
        final_count=len(merged),
        final_duplicate_suppressed=final_duplicate_count,
    )
    logger.info(
        "label_normalization_completed",
        project_id=project_id,
        asset_id=asset_id,
        agent_run_id=agent_run_id,
        selected_models=execution_models,
        requested_labels=requested_labels,
        resolved_detection_labels=resolved_detection_labels,
        raw_count=len(all_detections),
        fused_count=len(merged),
        final_count=len(merged),
    )
    log_pipeline_event(
        "fusion_detection_result",
        project_id=project_id,
        asset_id=asset_id,
        agent_run_id=state.get("audit_record").agent_run_id if state.get("audit_record") else None,
        execution_id=execution_id,
        model="multi_model",
        count=len(merged),
        raw_count=len(all_detections),
    )
    
    # SAM2 segmentation: when in agent plan or when segmentation is requested
    masks: list[Any] = []
    plan_task = plan.get("task") or state.get("evidence", {}).get("task_type")
    plan_geom = plan.get("geometry") or state.get("evidence", {}).get("geometry")
    segmentation_requested = (
        ModelKey.SAM2.value in execution_models
        or plan_task == "segmentation"
        or plan_geom in ("polygon", "segmentation", "mask")
        or bool(state.get("evidence", {}).get("segmentation_required"))
    )
    if segmentation_requested and merged:
        if runtime.registry.try_load(ModelKey.SAM2.value):
            t0 = time.perf_counter()
            logger.info("segmentation_started", model="sam2", box_count=len(merged))
            sam2_adapter = runtime.registry.get(ModelKey.SAM2.value)
            boxes = [d.bbox for d in merged]
            box_labels = [d.label for d in merged]
            ann_ids = [d.id for d in merged]
            masks = await asyncio.to_thread(
                sam2_adapter.segment_boxes,
                image_path,
                asset_id=asset_id,
                boxes=boxes,
                labels=box_labels,
                annotation_ids=ann_ids,
                storage_dir=storage.root / "masks" / asset_id,
            )
            if ModelKey.SAM2.value not in executed_models:
                executed_models.append(ModelKey.SAM2.value)
            timings["sam2_ms"] = (time.perf_counter() - t0) * 1000.0
            logger.info("segmentation_completed", model="sam2", mask_count=len(masks))
        else:
            logger.warning("sam2_unavailable", reason="SAM2 requested but model not loaded")
            
    logger.info(
        "agent_action_executed",
        candidate_models=candidate_models,
        execution_models=execution_models,
        models_executed=executed_models,
        raw_count=len(all_detections),
        merged_count=len(merged),
        mask_count=len(masks),
        timings=timings,
    )

    audit = state.get("audit_record")
    if audit:
        audit.fusion_metrics = fusion_dict
        audit.log_event("execute_model", {
            "candidate_models": candidate_models,
            "execution_models": execution_models,
            "models_executed": executed_models,
            "raw_count": len(all_detections),
            "merged_count": len(merged),
            "mask_count": len(masks),
            "timings": timings,
        })
        
    return {
        "raw_detections": all_detections,
        "merged_detections": merged,
        "masks": masks,
        "execution_models": execution_models,
        "models_executed": list(dict.fromkeys(prior_models + executed_models)),
        "execution_errors": execution_errors,
        "execution_failed": bool(execution_errors),
        "execution_id": execution_id,
        "execution_history": history + [{
            "execution_id": execution_id,
            "models": list(executed_models),
            "actions": list(plan.get("actions", [])),
            "result_count": len(all_detections),
            "merged_count": len(merged),
            "errors": list(execution_errors),
        }],
        "fusion_conflicts": fusion_conflicts,
        "timings": timings,
    }


async def evaluate_quality_and_decision_node(state: PipelineState) -> PipelineState:
    t0 = time.perf_counter()
    if state["project_snapshot"].get("modality") in {"text", "document"}:
        from app.services.text_capability import verify_text_annotations
        annotations = list(state.get("text_annotations", []))
        # Exact duplicate spans are not additional predictions. Remove them
        # before semantic verification and persistence so they do not turn an
        # otherwise valid text result into an unnecessary review item.
        unique_annotations: list[dict[str, Any]] = []
        seen_annotation_keys: set[tuple[Any, Any, Any]] = set()
        for annotation in annotations:
            span = annotation.get("text_span") or annotation.get("geometry") or {}
            if annotation.get("geometry_type") == "text_relation":
                relation_geometry = annotation.get("geometry") or {}
                key = ("relation", relation_geometry.get("source"), relation_geometry.get("relation"), relation_geometry.get("target"))
            else:
                key = (annotation.get("label"), span.get("start"), span.get("end"))
            if key in seen_annotation_keys:
                continue
            seen_annotation_keys.add(key)
            unique_annotations.append(annotation)
        annotations = unique_annotations
        # Spell labels as the project's classes do ("POSITIVE" → "Positive"), so reviews,
        # colours and exports match the class list. A label outside the classes keeps its
        # own name, softened from capitals, and goes to a person.
        canonical = {str(name).casefold(): str(name) for name in state["project_snapshot"].get("labels") or []}
        for annotation in annotations:
            label = str(annotation.get("label") or "")
            annotation["label"] = canonical.get(label.casefold()) or (label.capitalize() if label.isupper() else label)
        state["text_annotations"] = annotations
        errors = list((state.get("text_result") or {}).get("errors", []))
        plan = state.get("execution_plan") or {}
        capability = str((plan.get("models") or [""])[0])
        text_result = state.get("text_result") or {}
        # Classification and sentiment services already validate their output
        # against their response schema and confidence. Re-sending dozens of
        # extracted chunks to a second Gemini verifier creates a huge prompt,
        # frequently times out, and adds no useful signal for document-level
        # labels. Keep semantic verification for entity/relation tasks where
        # span grounding is materially important.
        if capability in {"text_classification", "text_sentiment_analysis"}:
            semantic = {
                "verifications": [],
                "available": True,
                "skipped": "model_validated_document_labels",
            }
        else:
            semantic = await verify_text_annotations(
                text=text_result.get("text", ""),
                annotations=annotations,
                ontology=list(plan.get("requested_labels", []) or []),
                capability=capability,
                model_id=capability,
            )
        verification_by_id = {str(item.get("annotation_id")): item for item in semantic.get("verifications", [])}
        for index, annotation in enumerate(annotations):
            annotation_id = str(annotation.get("id") or f"annotation-{index}")
            evidence = verification_by_id.get(annotation_id)
            logger.info("semantic_verification_started", execution_id=state.get("execution_id"), asset_id=state.get("asset_id"), annotation_id=annotation_id, entity_text=(annotation.get("text_span") or {}).get("text", ""), predicted_label=annotation.get("label"))
            if evidence:
                logger.info("semantic_verification_completed", semantic_validity=evidence.get("semantic_validity"), ontology_validity=evidence.get("ontology_validity"), contextual_validity=evidence.get("contextual_validity"), conflict_detected=evidence.get("conflict_detected"), alternative_label=evidence.get("alternative_label"), verification_confidence=evidence.get("verification_confidence"))
                logger.info("semantic_verification_decision", decision=evidence.get("decision"), next_action="APPROVE" if evidence.get("decision") == "VALID" else ("REPLAN" if evidence.get("alternative_label") else "HUMAN_REVIEW"))
        semantic_conflicts = [item for item in semantic.get("verifications", []) if item.get("decision") != "VALID" or item.get("conflict_detected")]
        confidence_values = [
            float(annotation["confidence"])
            for annotation in annotations
            if isinstance(annotation.get("confidence"), (int, float))
        ]
        mean_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values else None
        )
        confidence_threshold = 0.95
        confidence_passed = mean_confidence is not None and mean_confidence >= confidence_threshold
        requested = {str(label).strip().lower() for label in plan.get("requested_labels", []) if str(label).strip()}
        invalid_spans = [a for a in annotations if a.get("geometry_type") != "text_relation" and (a.get("text_span", {}).get("start", -1) < 0 or a.get("text_span", {}).get("end", -1) < a.get("text_span", {}).get("start", -1))]
        annotation_keys = []
        for a in annotations:
            if a.get("geometry_type") == "text_relation":
                g = a.get("geometry") or {}
                annotation_keys.append(("relation", g.get("source"), g.get("relation"), g.get("target")))
            else:
                s = a.get("text_span", {})
                annotation_keys.append((a.get("label"), s.get("start"), s.get("end")))
        duplicate_keys = len(set(annotation_keys)) != len(annotation_keys)
        invalid_labels: list[dict[str, Any]] = []
        if capability == "text_entity_extraction" and requested:
            invalid_labels = [a for a in annotations if str(a.get("label", "")).strip().lower() not in requested]
        result_payload = text_result
        raw_result = result_payload.get("raw_result") or {}
        valid_sentiments = {"POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"}
        invalid_output = False
        if capability == "text_sentiment_analysis":
            invalid_output = str(raw_result.get("sentiment", "")).upper() not in valid_sentiments
        elif capability == "text_classification":
            invalid_output = not bool(str(raw_result.get("label", "")).strip())
        elif capability == "text_relation_extraction":
            document_text = str(text_result.get("text", ""))
            invalid_output = any(
                not (a.get("geometry") or {}).get("relation")
                or not (a.get("geometry") or {}).get("source")
                or not (a.get("geometry") or {}).get("target")
                or not (a.get("geometry") or {}).get("evidence")
                or str((a.get("geometry") or {}).get("source", "")).casefold() not in document_text.casefold()
                or str((a.get("geometry") or {}).get("target", "")).casefold() not in document_text.casefold()
                or str((a.get("geometry") or {}).get("evidence", "")).casefold() not in document_text.casefold()
                or str((a.get("geometry") or {}).get("source", "")).casefold() not in str((a.get("geometry") or {}).get("evidence", "")).casefold()
                or str((a.get("geometry") or {}).get("target", "")).casefold() not in str((a.get("geometry") or {}).get("evidence", "")).casefold()
                for a in annotations
            )
        quality_report = {"modality": "text", "capability": capability, "annotation_count": len(annotations), "invalid_spans": len(invalid_spans), "invalid_labels": len(invalid_labels), "duplicate_annotations": duplicate_keys, "invalid_output": invalid_output, "errors": errors, "semantic_verification": semantic, "semantic_conflicts": semantic_conflicts, "confidence_score": mean_confidence, "confidence_threshold": confidence_threshold, "confidence_passed": confidence_passed, "replan_attempted": state.get("replan_count", 0) > 0, "replan_count": state.get("replan_count", 0)}
        no_semantic_result = capability == "text_entity_extraction" and not annotations
        quality_report["no_semantic_result"] = no_semantic_result
        alternatives = [str(item.get("alternative_label")) for item in semantic_conflicts if item.get("alternative_label")]
        structural_failure = bool(errors or invalid_spans or invalid_labels or duplicate_keys or invalid_output or no_semantic_result)
        # A verifier timeout is a degraded quality signal, not proof that a
        # high-confidence, structurally valid result is wrong. Structural
        # failures and explicit semantic conflicts still require review.
        semantic_failure = bool(semantic_conflicts)
        can_replan = state.get("replan_count", 0) < state.get("max_replans", 1)
        if not confidence_passed:
            quality_action = "HUMAN_REVIEW"
            decision_status = "HUMAN_REVIEW"
            human_review_required = True
            reason = "Text annotation confidence is below the 0.95 auto-approve threshold"
        elif semantic_failure and alternatives and can_replan:
            quality_action = "RETRY"
            decision_status = "REPLAN"
            human_review_required = False
            reason = "Semantic verification found a replan candidate"
        elif semantic_failure or structural_failure:
            quality_action = "HUMAN_REVIEW"
            decision_status = "HUMAN_REVIEW"
            human_review_required = True
            reason = "Semantic verification or structural validation remains unresolved"
        else:
            quality_action = "APPROVE"
            decision_status = "AUTO_APPROVE"
            human_review_required = False
            reason = f"Capability-aware validation for {capability}"
        quality_report["final_decision"] = decision_status
        quality_report["replan_attempted"] = state.get("replan_count", 0) > 0 or quality_action == "RETRY"
        review_decision = ReviewDecision(status=decision_status, human_review_required=human_review_required, unresolved_reasons=tuple(["TEXT_VALIDATION"] if human_review_required else []), evidence=quality_report)
        quality_agent_decision = {"action": quality_action, "human_review_required": human_review_required, "reason": reason, "missing_labels": alternatives, "semantic_verification": semantic}
        logger.info("text_quality_decision", confidence_score=mean_confidence, confidence_threshold=confidence_threshold, semantic_verification="PASSED" if not semantic_failure else "FAILED", semantic_conflicts=semantic_conflicts, replan_attempted=quality_report["replan_attempted"], replan_count=state.get("replan_count", 0), final_decision=decision_status)
        logger.info("text_quality_evaluated", capability=capability, annotation_count=len(annotations), quality_report=quality_report, decision=decision_status)
        if state.get("audit_record"):
            state["audit_record"].quality_results = quality_report
            state["audit_record"].final_decision = decision_status
            state["audit_record"].log_event("evaluate_text_quality", {"decision": decision_status, "report": quality_report})
        return {"quality_report": quality_report, "quality_agent_decision": quality_agent_decision, "mean_confidence": mean_confidence, "review_decision": review_decision, "timings": {**state.get("timings", {}), "quality_ms": (time.perf_counter() - t0) * 1000.0}}
    merged = state.get("merged_detections", [])
    all_detections = state.get("raw_detections", [])
    avail_map = state["available_models"]
    
    # 1. Quality evaluation
    quality_report = validate_object_level_quality(merged, all_detections)
    conflict_records = list(state.get("fusion_conflicts") or [])
    requested_label_set = {
        str(label).strip().casefold()
        for label in (state.get("execution_plan") or {}).get("requested_labels", [])
    }
    unresolved_conflicts = [
        conflict for conflict in conflict_records
        if conflict.get("resolution_status") == "unresolved"
    ]
    unresolved_requested_conflicts = [
        conflict for conflict in unresolved_conflicts
        if any(
            str(candidate.get("label") or "").strip().casefold() in requested_label_set
            for candidate in (conflict.get("candidate_a"), conflict.get("candidate_b"))
            if isinstance(candidate, dict)
        )
    ]
    quality_report.update({
        "cross_model_conflicts": conflict_records,
        "unresolved_conflicts": unresolved_conflicts,
        "unresolved_conflict_count": len(unresolved_conflicts),
        "unresolved_requested_label_conflicts": unresolved_requested_conflicts,
        "resolved_conflict_count": sum(
            1 for conflict in conflict_records
            if conflict.get("resolution_status") == "resolved"
        ),
    })
    coverage = build_image_coverage_summary(
        merged,
        image_width=state["asset_snapshot"].get("width"),
        image_height=state["asset_snapshot"].get("height"),
    )
    quality_agent_decision = review_execution_quality(
        coverage=coverage,
        detections=merged,
        execution_plan={
            **(state.get("execution_plan") or {}),
            "executed_models": list(state.get("models_executed", [])),
            "execution_history": list(state.get("execution_history", [])),
            "execution_errors": state.get("execution_errors", []),
            "quality_report": quality_report,
            "segmentation_required": bool(
                (state.get("execution_plan") or {}).get("task") == "segmentation"
                or (state.get("execution_plan") or {}).get("geometry") in {"polygon", "segmentation", "mask"}
            ),
            "segmentation_observed": bool(state.get("masks")),
            "runtime_capabilities": state.get("runtime_capabilities", []),
            "unmapped_detections": [
                {
                    "raw_label": (getattr(det, "provenance", {}) or {}).get("raw_label"),
                    "requested_label": (getattr(det, "provenance", {}) or {}).get("requested_label"),
                    "mapping_status": (getattr(det, "provenance", {}) or {}).get("mapping_status"),
                    "asset_id": getattr(det, "asset_id", None),
                }
                for det in all_detections
                if (getattr(det, "provenance", {}) or {}).get("mapping_status") == "UNMAPPED_DETECTION"
            ],
        },
        previous_attempts=state.get("previous_attempts", []),
        available_models=avail_map,
        settings=get_settings(),
    )
    requested_coverage = list(quality_agent_decision.get("coverage", {}).get("requested_label_coverage", []))
    coverage_fields = {
        "requested_label_coverage": requested_coverage,
        "detected_labels": list(quality_agent_decision.get("coverage", {}).get("detected_labels", [])),
        "evaluated_true_negative_labels": list(
            quality_agent_decision.get("coverage", {}).get("evaluated_true_negative_labels", [])
        ),
        "uncertain_labels": list(quality_agent_decision.get("coverage", {}).get("uncertain_labels", [])),
        "unevaluated_labels": list(quality_agent_decision.get("coverage", {}).get("unevaluated_labels", [])),
        "coverage_complete": bool(quality_agent_decision.get("coverage", {}).get("coverage_complete")),
    }
    quality_report.update(coverage_fields)
    logger.info(
        "agent_quality_coverage_evaluated",
        asset_id=state.get("asset_id"),
        execution_id=state.get("execution_id"),
        requested_labels=list((state.get("execution_plan") or {}).get("requested_labels", [])),
        detected_labels=coverage_fields["detected_labels"],
        evaluated_true_negative_labels=coverage_fields["evaluated_true_negative_labels"],
        uncertain_labels=coverage_fields["uncertain_labels"],
        unevaluated_labels=coverage_fields["unevaluated_labels"],
        coverage_complete=coverage_fields["coverage_complete"],
    )
    
    # 2. Image-level AI mean confidence calculation
    ai_confidences = [d.confidence for d in merged if d.confidence is not None]
    mean_conf = (sum(ai_confidences) / len(ai_confidences)) if ai_confidences else None
    
    # 3. Decision agent: AUTO_APPROVE vs HUMAN_REVIEW
    policy = state["project_snapshot"].get("quality_policy", {})
    auto_thresh = float(policy.get("auto_approve_threshold", 0.95))

    review_dec = decide_review(
        merged=merged,
        all_detections=all_detections,
        scene_evidence=None,
        completed_models=list(state.get("models_executed", [])),
        required_verification="standard",
        rejected_count=0,
        model_availability=avail_map,
        auto_approve_threshold=auto_thresh,
        verification_report=quality_report,
    )
    quality_ms = (time.perf_counter() - t0) * 1000.0
    
    timings = dict(state.get("timings", {}))
    timings["quality_ms"] = quality_ms
    
    final_dec = "HUMAN_REVIEW" if review_dec.human_review_required else "AUTO_APPROVE"
    review_reason = getattr(review_dec, "review_reason", ", ".join(getattr(review_dec, "reasons", [])))
    
    logger.info(
        "agent_result_evaluated",
        valid_count=len(merged),
        mean_confidence=mean_conf,
        decision=final_dec,
        reason=review_reason,
        quality_action=quality_agent_decision.get("action"),
        quality_meaning=quality_agent_decision.get("quality_meaning"),
        verification_decision=(
            "HUMAN_REVIEW" if review_dec.human_review_required else "AUTO_APPROVE"
        ),
        verification_reasons=list(review_dec.unresolved_reasons),
        final_decision=final_dec,
    )
    logger.info(
        "execution_observed",
        raw_count=len(all_detections),
        merged_count=len(merged),
        models_executed=list(state.get("models_executed", [])),
        quality_action=quality_agent_decision.get("action"),
        unresolved_conflict_count=len(unresolved_conflicts),
        unresolved_requested_label_conflicts=unresolved_requested_conflicts,
    )
    
    audit = state.get("audit_record")
    if audit:
        audit.quality_results = quality_report
        audit.final_decision = final_dec
        audit.review_reason = review_reason
        audit.log_event("evaluate_quality", {
            "decision": final_dec,
            "quality_action": quality_agent_decision.get("action"),
            "quality_meaning": quality_agent_decision.get("quality_meaning"),
            "verification_decision": final_dec,
            "reason": review_reason,
            "mean_confidence": mean_conf,
            "evidence_evaluation": quality_agent_decision,
        })
        
    return {
        "quality_report": quality_report,
        "quality_agent_decision": quality_agent_decision,
        "mean_confidence": mean_conf,
        "review_decision": review_dec,
        "timings": timings,
    }


async def decide_next_action_node(state: PipelineState) -> PipelineState:
    review_dec = state.get("review_decision")
    quality_decision = state.get("quality_agent_decision") or {}
    agentic_unavailable = state.get("agentic_planning_unavailable", False)

    # If planning was unavailable entirely — surface as HITL, not retry
    if agentic_unavailable:
        next_node = "human_review"
        logger.error(
            "agentic_planning_unavailable_routed_to_hitl",
            status="AGENTIC_PLANNING_UNAVAILABLE",
            reason=state.get("agentic_planning_reason", "unknown"),
            decision_source="agentic_planning_unavailable_handler",
        )
        return {"next_node": next_node}

    quality_action = quality_decision.get("action", "APPROVE")

    # Agent-driven next action — forward quality agent's decision verbatim.
    # No confidence/coverage rule overrides the agent here.
    reprocess_count = state.get("reprocess_count", 0)
    max_reprocess_cycles = state.get("max_reprocess_cycles", 3)
    if reprocess_count >= max_reprocess_cycles:
        # Loop protection: exceed maximum review cycles -> route to second review / escalation
        logger.warning(
            "max_reprocess_cycles_exceeded_routing_to_escalation",
            reprocess_count=reprocess_count,
            max_reprocess_cycles=max_reprocess_cycles,
        )
        return {"next_node": "human_review", "escalation_required": True}

    replan_count = state.get("replan_count", 0)
    max_replans = state.get("max_replans", 1)

    # Decision priority: unresolved execution failure, quality retry/replan,
    # then final verification.  Quality APPROVE only permits verification; it
    # can never bypass review_decision.
    if quality_action in {"RETRY", "DIFFERENT_STRATEGY", "ALTERNATE_MODEL"} and replan_count < max_replans:
        next_node = "replan"
    elif (
        (review_dec and review_dec.human_review_required)
        or quality_decision.get("human_review_required")
        or quality_action in {"HUMAN_REVIEW", "FAIL", "VERIFY"}
        or (quality_action in {"RETRY", "DIFFERENT_STRATEGY", "ALTERNATE_MODEL"} and replan_count >= max_replans)
    ):
        next_node = "human_review"
        if quality_action in {"RETRY", "DIFFERENT_STRATEGY", "ALTERNATE_MODEL"} and replan_count >= max_replans:
            logger.info(
                "max_replans_reached_escalating_to_hitl",
                replan_count=replan_count,
                max_replans=max_replans,
                quality_action=quality_action,
                decision_source="agent",
            )
    elif quality_action == "APPROVE":
        next_node = "persist"
    else:
        # SEGMENT or other — default to persist after execution
        next_node = "persist"

    logger.info(
        "agent_next_action_decided",
        next_node=next_node,
        quality_action=quality_action,
        quality_meaning=quality_decision.get("quality_meaning"),
        suggested_strategy=quality_decision.get("suggested_strategy"),
        suggested_models=quality_decision.get("suggested_models"),
        review_required=bool(review_dec.human_review_required) if review_dec else False,
        verification_decision=(
            "HUMAN_REVIEW" if review_dec and review_dec.human_review_required else "AUTO_APPROVE"
        ),
        final_decision=(
            "HUMAN_REVIEW" if review_dec and review_dec.human_review_required else "AUTO_APPROVE"
        ) if next_node in {"persist", "human_review"} else next_node.upper(),
        decision_source="quality_agent",
    )
    audit = state.get("audit_record")
    if audit:
        audit.log_event("agent_decision", {
            "project_id": state.get("project_id"),
            "batch_id": state.get("batch_id"),
            "job_id": state.get("job_id"),
            "job_item_id": state.get("job_item_id"),
            "asset_id": state.get("asset_id"),
            "execution_id": state.get("execution_id"),
            "current_plan": state.get("execution_plan", {}),
            "previous_results": list(state.get("execution_history", [])),
            "evidence_evaluation": quality_decision,
            "decision": next_node,
            "selected_next_action": next_node,
            "reason": quality_decision.get("reason", ""),
            "replan_count": state.get("replan_count", 0),
        })
    return {"next_node": next_node}


async def persist_and_analytics_node(state: PipelineState) -> PipelineState:
    """Persist model output and review state after the agent decision."""
    started = time.perf_counter()
    session = state["session"]
    merged = state.get("merged_detections", [])
    masks = state.get("masks", [])
    review_decision = state.get("review_decision")

    asset_id = state.get("asset_id") or state["asset_snapshot"].get("id")
    project_id = state.get("project_id") or state["project_snapshot"].get("id")
    batch_id = state.get("batch_id")
    job_id = state.get("job_id")
    audit = state.get("audit_record")
    agent_run_id = audit.agent_run_id if audit else None

    foreign_asset_ids = sorted({
        str(det.get("asset_id") if isinstance(det, dict) else getattr(det, "asset_id", "") or "")
        for det in merged
        if str(det.get("asset_id") if isinstance(det, dict) else getattr(det, "asset_id", "") or "") != str(asset_id)
    })
    if foreign_asset_ids:
        logger.critical(
            "asset_identity_violation",
            current_asset_id=asset_id,
            result_asset_ids=foreign_asset_ids,
            stage="persistence",
            job_id=job_id,
            batch_id=batch_id,
        )
        raise RuntimeError(
            f"Refusing to persist detections for assets {foreign_asset_ids!r} "
            f"under asset_id={asset_id!r}"
        )

    if state["project_snapshot"].get("modality") in {"text", "document"}:
        if hasattr(session, "db") and not hasattr(session, "delete_many"):
            text_db = session.db
        elif hasattr(session, "__getitem__"):
            text_db = session
        else:
            from app.db import models as db_models
            text_db = db_models.get_database()
        annotations_col = text_db["annotations"] if hasattr(text_db, "__getitem__") else getattr(text_db, "annotations", text_db)
        await annotations_col.delete_many({"asset_id": asset_id, "source": AnnotationSource.AI.value})
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        docs = []
        for annotation in state.get("text_annotations", []):
            doc = dict(annotation)
            # The shared annotation collection keeps a stable spatial schema;
            # text relations carry their real payload in geometry/text_span.
            # Zero geometry values make them readable through the existing
            # annotations API without changing image annotation behavior.
            doc.setdefault("x", 0.0)
            doc.setdefault("y", 0.0)
            doc.setdefault("w", 0.0)
            doc.setdefault("h", 0.0)
            doc.update({"project_id": project_id, "source": AnnotationSource.AI.value, "created_at": now, "updated_at": now, "inferred_at": now, "provenance": {**dict(doc.get("provenance") or {}), "agent_run_id": agent_run_id, "job_id": job_id, "batch_id": batch_id}})
            docs.append(doc)
        if docs:
            await annotations_col.insert_many(docs)
        if audit:
            audit.persisted_annotation_count = len(docs)
            audit.log_event("persist_text_annotations", {"count": len(docs)})
        logger.info(
            "text_persistence_completed",
            project_id=project_id,
            asset_id=asset_id,
            capability=(state.get("execution_plan") or {}).get("models", [None])[0],
            persistence_count=len(docs),
            final_status="persisted",
        )
        return {"final_status": "persisted", "persisted_count": len(docs), "persisted_annotation_count": len(docs), "timings": {**state.get("timings", {}), "persist_ms": (time.perf_counter() - started) * 1000.0}}

    execution_models = state.get("execution_models") or state.get("models_executed") or []
    if len(execution_models) == 1:
        model_id = execution_models[0]
    elif len(execution_models) > 1:
        model_id = "+".join(sorted(execution_models))
    elif merged:
        first_det = merged[0]
        model_id = (
            (first_det.get("model_id") if isinstance(first_det, dict) else getattr(first_det, "model_id", None))
            or (first_det.get("source") if isinstance(first_det, dict) else getattr(first_det, "source", None))
            or "agentic_pipeline"
        )
    else:
        model_id = "agentic_pipeline"

    if hasattr(session, "db"):
        db = session.db
    elif hasattr(session, "name") and hasattr(session, "client"):
        db = session
    else:
        from app.db import models as db_models
        db = db_models.get_database()
    ann_service = AnnotationService(db)
    asset = await ann_service._require_asset(asset_id)
    raw_asset = asset

    run_provenance = {
        "agent_run_id": agent_run_id,
        "execution_models": execution_models,
        "planner_source": state.get("planner_source", "agentic"),
        "quality_action": (state.get("quality_agent_decision") or {}).get("action"),
        "verification_decision": (
            "HUMAN_REVIEW" if review_decision and review_decision.human_review_required else "AUTO_APPROVE"
        ),
        "verification_reasons": list(review_decision.unresolved_reasons) if review_decision else [],
        "resolved_detection_labels": list((state.get("execution_plan") or {}).get("resolved_detection_labels") or []),
    }

    effective_job_id = state.get("job_item_id") or job_id
    logger.info(
        "annotation_persistence_started",
        project_id=project_id,
        asset_id=asset_id,
        batch_id=batch_id,
        job_id=job_id,
        annotation_count=len(merged),
        persistence_status="writing_final_result",
        review_status=(
            ReviewStatus.HUMAN_REVIEW.value
            if review_decision and review_decision.human_review_required
            else ReviewStatus.AUTO_APPROVED.value
        ),
    )
    logger.info(
        "final_annotation_persistence_started",
        project_id=project_id,
        asset_id=asset_id,
        batch_id=batch_id,
        job_id=job_id,
        annotation_count=len(merged),
        final_decision=(
            "HUMAN_REVIEW"
            if review_decision and review_decision.human_review_required
            else "AUTO_APPROVE"
        ),
    )
    try:
        ann_result, mean_conf = await ann_service.replace_ai_detections(
            asset_id=asset_id,
            raw_detections=merged,
            model_id=model_id,
            project_id=project_id,
            job_item_id=effective_job_id,
            batch_id=batch_id,
            run_provenance=run_provenance,
        )
        await ann_service.verify_ai_detections_readback(
            asset_id=asset_id,
            project_id=project_id,
            expected=ann_result,
            batch_id=batch_id,
            job_item_id=effective_job_id,
        )
    except Exception as exc:
        logger.error(
            "annotation_persistence_failed",
            project_id=project_id,
            asset_id=asset_id,
            batch_id=batch_id,
            job_id=job_id,
            annotation_count=len(merged),
            persistence_status="failed",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        raise
    count = len(ann_result)
    logger.info(
        "annotation_persistence_readback_verified",
        project_id=project_id,
        asset_id=asset_id,
        batch_id=batch_id,
        job_id=job_id,
        annotation_count=count,
        persistence_status="readback_verified",
        review_status=(
            ReviewStatus.HUMAN_REVIEW.value
            if review_decision and review_decision.human_review_required
            else ReviewStatus.AUTO_APPROVED.value
        ),
    )
    logger.info(
        "final_annotation_readback_verified",
        project_id=project_id,
        asset_id=asset_id,
        batch_id=batch_id,
        job_id=job_id,
        annotation_count=count,
        final_decision=(
            "HUMAN_REVIEW"
            if review_decision and review_decision.human_review_required
            else "AUTO_APPROVE"
        ),
        persistence_status="readback_verified",
    )
    logger.info(
        "persisted_detection_count",
        asset_id=asset_id,
        batch_id=batch_id,
        job_id=job_id,
        job_item_id=state.get("job_item_id") or job_id,
        final_fused_count=len(merged),
        count=count,
        model_id=model_id,
    )
    logger.info(
        "annotations_persisted",
        asset_id=asset_id,
        annotation_count=count,
        batch_id=batch_id,
        job_id=job_id,
    )
    if masks:
        from app.jobs.worker import _persist_mask_polygons
        await _persist_mask_polygons(session, state["storage"], masks)

    if state["project_snapshot"].get("modality") == "video":
        logger.info(
            "annotations_persisted",
            asset_id=asset_id,
            num_detections=len(merged),
            num_tracks=len(state.get("video_tracks", [])),
            num_activities=len(state.get("video_activities", [])),
            num_events=len(state.get("video_events", [])),
            num_masks=len(state.get("video_masks", [])),
            num_keypoints=len(state.get("video_keypoints", [])),
        )
        db = get_database()
        
        # 1. Tracks
        tracks = state.get("video_tracks", [])
        if tracks:
            import uuid
            track_docs = []
            for t in tracks:
                t_dict = t.model_dump() if hasattr(t, "model_dump") else dict(t)
                t_dict["asset_id"] = asset_id
                t_dict["project_id"] = project_id
                t_dict["id"] = t_dict.get("id") or str(uuid.uuid4())
                track_docs.append(t_dict)
            await db.tracks.delete_many({"asset_id": asset_id})
            await db.tracks.insert_many(track_docs)

        # 2. Activities
        activities = state.get("video_activities", [])
        if activities:
            import uuid
            act_docs = []
            for a in activities:
                a_dict = a.model_dump() if hasattr(a, "model_dump") else dict(a)
                a_dict["asset_id"] = asset_id
                a_dict["project_id"] = project_id
                a_dict["id"] = a_dict.get("id") or str(uuid.uuid4())
                a_dict["start_time"] = a_dict.get("start_timestamp_ms", 0.0) / 1000.0
                a_dict["end_time"] = a_dict.get("end_timestamp_ms", 0.0) / 1000.0
                act_docs.append(a_dict)
            await db.activities.delete_many({"asset_id": asset_id})
            await db.activities.insert_many(act_docs)

        # 3. Events
        events = state.get("video_events", [])
        if events:
            import uuid
            evt_docs = []
            for e in events:
                e_dict = e.model_dump() if hasattr(e, "model_dump") else dict(e)
                e_dict["asset_id"] = asset_id
                e_dict["project_id"] = project_id
                e_dict["id"] = e_dict.get("id") or str(uuid.uuid4())
                e_dict["timestamp"] = e_dict.get("timestamp_ms", 0.0) / 1000.0
                e_dict["time_range"] = [
                    e_dict.get("timestamp_ms", 0.0) / 1000.0,
                    (e_dict.get("timestamp_ms", 0.0) + e_dict.get("duration_ms", 2000.0)) / 1000.0
                ]
                e_dict["evidence_frames"] = [e_dict.get("frame_index", 0)]
                e_dict["associated_tracks"] = e_dict.get("track_ids", [])
                e_dict["verification_status"] = "verified"
                evt_docs.append(e_dict)
            await db.events.delete_many({"asset_id": asset_id})
            await db.events.insert_many(evt_docs)

        # 4. Masks
        video_masks = state.get("video_masks", [])
        if video_masks:
            import uuid
            mask_docs = []
            for m in video_masks:
                m_dict = m.model_dump() if hasattr(m, "model_dump") else dict(m)
                m_dict["asset_id"] = asset_id
                m_dict["project_id"] = project_id
                m_dict["id"] = m_dict.get("id") or str(uuid.uuid4())
                m_dict["annotation_id"] = m_dict.get("id")
                m_dict["area_px"] = len(m_dict.get("polygon", []))
                mask_docs.append(m_dict)
            await db.masks.delete_many({"asset_id": asset_id})
            await db.masks.insert_many(mask_docs)

        # 5. Keypoints
        keypoints = state.get("video_keypoints", [])
        if keypoints:
            import uuid
            kp_docs = []
            for k in keypoints:
                k_dict = k.model_dump() if hasattr(k, "model_dump") else dict(k)
                now = _utcnow()
                kp_docs.append({
                    "id": k_dict.get("id") or str(uuid.uuid4()),
                    "asset_id": asset_id,
                    "project_id": project_id,
                    "frame_index": k_dict.get("frame_index", 0),
                    "track_id": k_dict.get("track_id"),
                    "geometry_type": "keypoints",
                    "label": k_dict.get("label", "person"),
                    "points": k_dict.get("keypoints", []),
                    "confidence": float(k_dict.get("confidence", 0.9)),
                    "source": k_dict.get("source", "pose_tracker"),
                    "created_at": now,
                    "updated_at": now,
                })
            await db.annotations.insert_many(kp_docs)

    if review_decision:
        asset.review_status = (
            ReviewStatus.HUMAN_REVIEW.value
            if review_decision.human_review_required
            else ReviewStatus.AUTO_APPROVED.value
        )
        asset.review_reason = getattr(
            review_decision,
            "review_reason",
            ", ".join(getattr(review_decision, "reasons", [])),
        )
        def _extract_c(det: Any) -> float | None:
            c = det.get("confidence") if isinstance(det, dict) else getattr(det, "confidence", None)
            if isinstance(c, (int, float)) and not isinstance(c, bool) and 0.0 <= float(c) <= 1.0:
                return float(c)
            return None

        confidences = [c for c in (_extract_c(det) for det in merged) if c is not None]
        asset.mean_confidence = sum(confidences) / len(confidences) if confidences else None
        db = get_database()

        status_to_set = ReviewStatus.ESCALATED.value if state.get("escalation_required") else asset.review_status
        asset.review_status = status_to_set

        update_payload: dict[str, Any] = {
            "review_status": status_to_set,
            "review_reason": asset.review_reason,
            "mean_confidence": asset.mean_confidence,
            "reprocess_count": state.get("reprocess_count", 0),
        }
        if state.get("review_cycle_id"):
            update_payload["review_cycle_id"] = state["review_cycle_id"]
        if state.get("escalation_required"):
            update_payload["escalation_required"] = True

        await db["assets"].update_one(
            {"id": asset.id},
            {"$set": update_payload},
        )
        persisted_asset = await db["assets"].find_one({"id": asset.id})
        if not persisted_asset or persisted_asset.get("review_status") != status_to_set:
            raise RuntimeError(
                f"Asset review-status read-back failed for {asset_id}: "
                f"expected={status_to_set!r}, actual={persisted_asset.get('review_status') if persisted_asset else None!r}"
            )
        logger.info(
            "annotations_persisted",
            project_id=project_id,
            asset_id=asset_id,
            batch_id=batch_id,
            count=count,
        )
        logger.info(
            "annotation_persistence_completed",
            project_id=project_id,
            asset_id=asset_id,
            batch_id=batch_id,
            job_id=job_id,
            annotation_count=count,
            persistence_status="completed",
            review_status=status_to_set,
        )
        logger.info(
            "final_annotation_persistence_completed",
            project_id=project_id,
            asset_id=asset_id,
            batch_id=batch_id,
            job_id=job_id,
            annotation_count=count,
            final_decision=(
                "HUMAN_REVIEW" if status_to_set != ReviewStatus.AUTO_APPROVED.value else "AUTO_APPROVE"
            ),
            review_status=status_to_set,
            persistence_status="completed",
        )

        from app.services.audit_trail import record_audit_event
        await record_audit_event(
            db,
            asset_id=asset_id,
            action="ai_reprocess_completed" if state.get("human_feedback") else "ai_annotation_completed",
            actor_type="ai",
            after_state={
                "review_status": asset.review_status,
                "mean_confidence": asset.mean_confidence,
                "annotation_count": count,
                "reprocess_count": state.get("reprocess_count", 0),
                "execution_models": execution_models,
            },
            reason=asset.review_reason or "",
            project_id=project_id,
            batch_id=batch_id,
            job_id=job_id,
            metadata={"human_feedback": state.get("human_feedback")} if state.get("human_feedback") else {},
        )

    duration_ms = (time.perf_counter() - started) * 1000.0
    logger.info(
        "persistence_completed",
        project_id=project_id,
        asset_id=asset_id,
        batch_id=state.get("batch_id"),
        job_id=state.get("job_id"),
        job_item_id=state.get("job_item_id") or state.get("job_id"),
        final_fused_count=len(merged),
        annotation_count=count,
        duration_ms=duration_ms,
    )
    audit = state.get("audit_record")
    if audit:
        audit.persisted_annotation_count = count
        audit.log_event("persist_and_analytics", {"persisted_count": count})
    return {
        "actions_taken": state.get("actions_taken", []) + ["persist_and_analytics"],
        "timings": {**state.get("timings", {}), "persistence_ms": duration_ms},
        "persisted_count": count,
        "final_status": getattr(asset, "review_status", None),
    }


async def replan_node(state: PipelineState) -> PipelineState:
    """Agent-driven replanning based on quality agent's observation.

    The quality agent has already decided RETRY/DIFFERENT_STRATEGY/ALTERNATE_MODEL.
    This node passes its suggested_strategy, suggested_models, and missing_labels
    back to the planning agent for a new authoritative execution plan.

    CRITICAL: This is NOT a deterministic strategy escalation.
    The planning agent receives the full quality observation (including which labels
    are missing and which models cover them per runtime_capabilities) and decides
    the new plan. No domain-specific label→model hardcoding.
    """
    quality_decision = state.get("quality_agent_decision") or {}
    merged = state.get("merged_detections", [])
    replan_count = state.get("replan_count", 0)

    if state["project_snapshot"].get("modality") in {"text", "document"}:
        alternatives = [
            str(label).strip()
            for label in quality_decision.get("missing_labels", [])
            if str(label).strip()
        ]
        if not alternatives:
            return {"next_node": "human_review", "escalation_required": True}
        current_plan = dict(state.get("execution_plan", {}))
        requested = list(dict.fromkeys([
            *[str(label) for label in current_plan.get("requested_labels", []) if str(label).strip()],
            *alternatives,
        ]))
        current_plan["requested_labels"] = requested
        current_plan["actions"] = [
            {**action, "labels": requested}
            for action in current_plan.get("actions", [])
        ]
        logger.info(
            "semantic_replan_requested",
            reason=quality_decision.get("reason", "semantic conflict"),
            previous_label=quality_decision.get("semantic_verification", {}).get("verifications", []),
            alternative_label=alternatives,
            evidence=quality_decision.get("semantic_verification", {}),
        )
        if state.get("audit_record"):
            state["audit_record"].log_event("semantic_replan_requested", {
                "reason": quality_decision.get("reason", "semantic conflict"),
                "alternative_labels": alternatives,
                "evidence": quality_decision.get("semantic_verification", {}),
            })
        return {
            "execution_plan": current_plan,
            "replan_count": replan_count + 1,
            "missing_labels": alternatives,
            "previous_attempts": list(state.get("previous_attempts", [])) + [{
                "replan_count": replan_count,
                "plan": state.get("execution_plan", {}),
                "quality_action": quality_decision.get("action"),
                "semantic_verification": quality_decision.get("semantic_verification", {}),
            }],
        }

    # Concrete missing labels — populated by quality agent in quality_review.py
    # Falls back to coverage data if LLM omitted the field.
    missing_labels: list[str] = (
        quality_decision.get("missing_labels")
        or state.get("missing_labels")
        or [
            lbl for lbl in (state.get("execution_plan") or {}).get("requested_labels", [])
            if lbl not in {getattr(d, "label", "") for d in merged}
        ]
    )

    # Summarize runtime capabilities so the replan agent can match missing labels
    # to model vocabulary without guessing.
    runtime_capabilities = state.get("runtime_capabilities")
    if not runtime_capabilities and state.get("runtime") and getattr(state.get("runtime"), "registry", None):
        runtime_capabilities = state["runtime"].registry.get_runtime_capabilities()
    if not runtime_capabilities:
        registry = ModelCapabilityRegistry(state.get("available_models", {}))
        runtime_capabilities = [
            {
                "model_key": k,
                "capabilities": meta.get("task_types", []),
                "task_types": meta.get("task_types", []),
                "vocabulary": meta.get("supported_classes", []) if meta.get("supported_classes") != "*" else ["anything"],
                "is_open_vocabulary": meta.get("open_vocabulary", False),
                "available": state.get("available_models", {}).get(k, True),
            }
            for k, meta in registry.capabilities.items()
        ]

    caps_summary: list[dict] = []
    caps_dict: dict[str, dict[str, Any]] = {}
    for cap in runtime_capabilities if isinstance(runtime_capabilities, list) else []:
        if not isinstance(cap, dict):
            continue
        key = str(cap.get("model_key") or "")
        if not key or not state.get("available_models", {}).get(key, False):
            continue
        vocab = list(cap.get("vocabulary") or [])
        caps = [str(c).lower() for c in (cap.get("capabilities") or cap.get("task_types") or [])]
        is_open = "open_vocab_detection" in caps or "open_vocabulary_detection" in caps
        cap_entry = {
            "model": key,
            "model_key": key,
            "capabilities": caps,
            "is_open_vocabulary": is_open,
            "vocabulary": vocab,
        }
        caps_summary.append(cap_entry)
        caps_dict[key] = cap_entry

    confidences = [d.confidence for d in merged if d.confidence is not None]
    observation = {
        "replan_reason": quality_decision.get("reason", "Quality agent requested retry"),
        "quality_action": quality_decision.get("action"),
        "suggested_strategy": quality_decision.get("suggested_strategy"),
        "suggested_models": quality_decision.get("suggested_models", []),
        "missing_labels": missing_labels,
        "requested_labels": list((state.get("execution_plan") or {}).get("requested_labels", [])),
        "detected_labels": list(dict.fromkeys(
            getattr(d, "label", "") for d in merged if getattr(d, "label", "")
        )),
        "uncertain_detection_ids": quality_decision.get("uncertain_detection_ids", []),
        "previous_detection_count": len(merged),
        "previous_confidence_stats": {
            "min": min(confidences) if confidences else None,
            "mean": (sum(confidences) / len(confidences)) if confidences else None,
            "max": max(confidences) if confidences else None,
        },
        "replan_count": replan_count,
        "previous_plan": {
            "models": list((state.get("execution_plan") or {}).get("models", [])),
            "strategy": (state.get("execution_plan") or {}).get("strategy"),
        },
        "runtime_capabilities_with_vocabulary": caps_summary,
    }

    logger.info(
        "quality_retry_requested",
        replan_count=replan_count + 1,
        quality_action=quality_decision.get("action"),
        quality_reason=quality_decision.get("reason"),
        missing_labels=missing_labels,
        suggested_models=quality_decision.get("suggested_models", []),
        suggested_strategy=quality_decision.get("suggested_strategy"),
        decision_source="quality_agent",
    )
    logger.info(
        "agent_retry_planning_started",
        replan_count=replan_count + 1,
        missing_labels=missing_labels,
        available_models=list(state.get("available_models", {}).keys()),
    )

    settings = get_settings()
    avail_map = state.get("available_models", {})
    new_plan_result = call_json_agent(
        system_prompt=(
            "You are the detection execution planner. "
            "The quality agent has reviewed the previous execution and found missing labels. "
            "Use the quality observation fields (missing_labels, suggested_models, "
            "runtime_capabilities_with_vocabulary) to select the correct model(s) and actions for the retry.\n"
            "CRITICAL CAPABILITY & VOCABULARY GROUNDING RULES:\n"
            "1. CLOSED-VOCABULARY models (models without open_vocab_detection, e.g. yolo26): "
            "   ONLY assign labels that exist verbatim in that model's vocabulary list. Never invent aliases or semantic mappings.\n"
            "2. OPEN-VOCABULARY models (models with open_vocab_detection, e.g. dino): "
            "   assign any missing labels that are not in closed-set vocabularies.\n"
            "3. Return canonical JSON plan: {decision_source:'agent', plan_version:'1', task_type, geometry, actions:[{model, strategy, labels, parameters, reason}], models:[...], strategy, image_size, tile_rows, tile_cols, tile_overlap}."
        ),
        user_payload={
            "observation": observation,
            "available_models": avail_map,
            "ontology": list(state["project_snapshot"].get("labels", [])),
        },
        settings=settings,
        max_output_tokens=700,
    )

    allowed_strategies = {"full_image", "high_resolution", "tiled", "high_resolution_tiled"}
    actions: list[dict[str, Any]] = []
    new_strategy = str(quality_decision.get("suggested_strategy") or "full_image")
    if new_strategy not in allowed_strategies:
        new_strategy = "full_image"
    suggested_models = [str(m) for m in (quality_decision.get("suggested_models") or []) if str(m) in avail_map and avail_map.get(str(m), False)]
    asset_id = str(state.get("asset_id") or "")
    audit_rec = state.get("audit_record")
    agent_run_id = str(
        getattr(audit_rec, "agent_run_id", "")
        or (audit_rec.get("agent_run_id") if isinstance(audit_rec, dict) else "")
        or ""
    )
    
    # Check if Gemini provided a plan with actions
    if isinstance(new_plan_result, dict) and isinstance(new_plan_result.get("actions"), list) and new_plan_result.get("actions"):
        candidate_actions: list[dict[str, Any]] = []
        for act in new_plan_result["actions"]:
            if not isinstance(act, dict):
                continue
            m = str(act.get("model") or "").strip()
            if m in avail_map and avail_map.get(m, False):
                strat = str(act.get("strategy") or new_strategy or "full_image")
                if strat not in allowed_strategies:
                    strat = new_strategy
                candidate_actions.append({
                    "model": m,
                    "strategy": strat,
                    "labels": list(act.get("labels") or []),
                    "parameters": dict(act.get("parameters") or {}),
                    "reason": str(act.get("reason") or "Replan action"),
                })
        # Strictly validate Gemini's replan actions against runtime capabilities
        is_valid, records, invalid_reasons = validate_plan_grounding(
            candidate_actions,
            state.get("runtime_capabilities", []),
            agent_run_id=agent_run_id,
            asset_id=asset_id,
        )
        if is_valid and candidate_actions:
            actions = candidate_actions
        else:
            logger.warning(
                "replan",
                unresolved_labels=[
                    r.get("label") or (", ".join(map(str, r.get("labels", []))) if r.get("labels") else "")
                    for r in invalid_reasons
                ],
                reason="retry_plan_contained_ungrounded_labels",
                agent_run_id=agent_run_id,
                asset_id=asset_id,
            )

    # If Gemini plan was absent or rejected, ground missing labels dynamically against runtime capabilities
    if not actions:
        gemini_models = (
            [str(m) for m in new_plan_result.get("models", []) if str(m) in avail_map and avail_map.get(str(m), False)]
            if isinstance(new_plan_result, dict) and new_plan_result.get("models")
            else []
        )
        candidate_models = gemini_models or suggested_models or [str(m) for m in (state.get("execution_plan") or {}).get("models", [])]
        grounded_acts, unavail = ground_labels_to_capabilities(
            requested_labels=missing_labels,
            runtime_capabilities=state.get("runtime_capabilities", []),
            preferred_models=candidate_models,
            strategy=new_strategy,
        )
        actions = grounded_acts
        if unavail:
            logger.warning(
                "replan_unavailable_labels",
                unavailable_labels=unavail,
                missing_labels=missing_labels,
                agent_run_id=agent_run_id,
                asset_id=asset_id,
            )

    new_models = list(dict.fromkeys(a["model"] for a in actions))
    if not new_models:
        logger.error(
            "agentic_planning_unavailable",
            status="AGENTIC_PLANNING_UNAVAILABLE",
            reason="Replan agent returned no valid models",
            missing_labels=missing_labels,
            suggested_models=quality_decision.get("suggested_models", []),
            decision_source="agent",
        )
        return {
            "next_node": "human_review",
            "agentic_planning_unavailable": True,
            "agentic_planning_reason": "Replan agent returned no valid models",
        }

    # Parameter propagation for replan actions
    image_size = (
        actions[0]["parameters"].get("image_size")
        or (1024 if "tiled" in new_strategy or "high_resolution" in new_strategy else None)
    )
    tile_rows = actions[0]["parameters"].get("tile_rows", 3 if "tiled" in new_strategy else 1)
    tile_cols = actions[0]["parameters"].get("tile_cols", 3 if "tiled" in new_strategy else 1)
    tile_overlap = actions[0]["parameters"].get("tile_overlap", 0.20 if "tiled" in new_strategy else 0.0)

    for act in actions:
        p = act.setdefault("parameters", {})
        if image_size is not None and "image_size" not in p:
            p["image_size"] = image_size
        if tile_rows is not None and "tile_rows" not in p:
            p["tile_rows"] = tile_rows
        if tile_cols is not None and "tile_cols" not in p:
            p["tile_cols"] = tile_cols
        if tile_overlap is not None and "tile_overlap" not in p:
            p["tile_overlap"] = tile_overlap

    # Enforce technical validation on final retry plan before execution
    is_valid, records, invalid_reasons = validate_plan_grounding(
        actions,
        state.get("runtime_capabilities", []),
        agent_run_id=agent_run_id,
        asset_id=asset_id,
    )
    if not is_valid:
        logger.error(
            "agent_retry_plan_invalid",
            reason="Retry plan contains ungrounded labels",
            unsupported_assignments=invalid_reasons,
            agent_run_id=agent_run_id,
            asset_id=asset_id,
        )
        return {
            "next_node": "human_review",
            "agentic_planning_unavailable": True,
            "agentic_planning_reason": "Retry plan contains ungrounded labels",
        }

    new_plan = dict(state.get("execution_plan", {}))
    new_plan["models"] = new_models
    new_plan["actions"] = actions
    new_plan["strategy"] = new_strategy
    new_plan["image_size"] = image_size
    new_plan["tile_rows"] = tile_rows
    new_plan["tile_cols"] = tile_cols
    new_plan["tile_overlap"] = tile_overlap
    new_plan["reasoning_summary"] = f"Replan #{replan_count + 1}: {observation['replan_reason']}"
    new_plan.setdefault("requested_labels", list((state.get("execution_plan") or {}).get("requested_labels", [])))

    logger.info(
        "agent_retry_plan_created",
        retry_model_selected=new_models,
        retry_strategy_selected=new_strategy,
        replan_count=replan_count + 1,
        missing_labels=missing_labels,
        decision_source="agent",
    )
    logger.info(
        "final_grounded_execution_plan",
        models=new_models,
        actions=actions,
        strategy=new_strategy,
        image_size=image_size,
        agent_run_id=agent_run_id,
        asset_id=asset_id,
    )

    previous_attempts = list(state.get("previous_attempts", []))
    previous_attempts.append({
        "replan_count": replan_count,
        "plan": state.get("execution_plan", {}),
        "quality_action": quality_decision.get("action"),
        "detection_count": len(merged),
        "missing_labels": missing_labels,
    })

    return {
        "execution_plan": new_plan,
        "replan_count": replan_count + 1,
        "previous_attempts": previous_attempts,
        "missing_labels": missing_labels,
    }
async def run_agentic_pipeline_graph(
    *,
    project: ProjectRow,
    asset: AssetRow,
    user_request: str,
    session: Any,
    storage: FileStorage,
    runtime: InferenceRuntime,
    batch_id: str | None = None,
    job_id: str | None = None,
    job_item_id: str | None = None,
    project_id: str | None = None,
    asset_id: str | None = None,
    project_snapshot: dict[str, Any] | None = None,
    asset_snapshot: dict[str, Any] | None = None,
    max_replans: int = 3,
    human_feedback: dict[str, Any] | None = None,
    reprocess_count: int = 0,
    max_reprocess_cycles: int = 3,
    review_cycle_id: str | None = None,
) -> PipelineState:
    """Async executor for the Agentic Orchestration Pipeline."""
    resolved_project_id = project_id or str(project.id)
    resolved_asset_id = _resolve_authoritative_asset_id(
        asset_id=asset_id,
        asset=asset,
        asset_snapshot=asset_snapshot,
    )
    resolved_project_snapshot = project_snapshot or {
        "id": resolved_project_id,
        "labels": list(project.labels or []),
        "target_labels": list(project.labels or []),
        "label_ontology": list(getattr(project, "label_ontology", None) or []),
        "quality_policy": dict(project.quality_policy or {}),
        "task_type": project.task_type,
        "modality": project.modality,
        "goal": getattr(project, "goal", ""),
    }
    resolved_asset_snapshot = asset_snapshot or {
        "id": resolved_asset_id,
        "width": asset.width,
        "height": asset.height,
        "storage_path": asset.storage_path,
    }
    audit = create_audit_record(
        project_id=resolved_project_id,
        asset_id=resolved_asset_id,
        user_request=user_request,
        ontology_snapshot=list(resolved_project_snapshot.get("labels", [])),
        available_models=(
            {s.key: True for s in runtime.registry.status()}
            if runtime and getattr(runtime, "registry", None) is not None
            else {}
        ),
    )
    
    logger.info(
        "agent_execution_started",
        agent_run_id=audit.agent_run_id if audit else None,
        project_id=resolved_project_id,
        asset_id=resolved_asset_id,
        batch_id=batch_id,
        job_id=job_id,
    )
    logger.info(
        "agent_run_started",
        agent_run_id=audit.agent_run_id if audit else None,
        project_id=resolved_project_id,
        asset_id=resolved_asset_id,
        batch_id=batch_id,
        job_id=job_id,
        reprocess_count=reprocess_count,
        has_human_feedback=bool(human_feedback),
    )
    
    policy = resolved_project_snapshot.get("quality_policy", {})
    configured_max_cycles = int(policy.get("max_reprocess_cycles", max_reprocess_cycles))
    configured_max_replans = int(policy.get("max_agentic_iterations", policy.get("max_replans", max_replans)))

    state: PipelineState = {
        "project": project,
        "asset": asset,
        "user_request": user_request,
        "session": session,
        "storage": storage,
        "runtime": runtime,
        "project_id": resolved_project_id,
        "asset_id": resolved_asset_id,
        "project_snapshot": resolved_project_snapshot,
        "asset_snapshot": resolved_asset_snapshot,
        "batch_id": batch_id,
        "job_id": job_id,
        # Some existing callers pass the job item as job_id.  Preserve that
        # established contract while keeping an explicit job-item scope in
        # the graph state for callers that provide both identifiers.
        "job_item_id": job_item_id or job_id,
        "replan_count": 0,
        "max_replans": max(0, configured_max_replans),
        "execution_history": [],
        "previous_attempts": [],
        "audit_record": audit,
        "planner_source": "agentic",
        "timings": {},
        "human_feedback": human_feedback,
        "reprocess_count": reprocess_count,
        "max_reprocess_cycles": configured_max_cycles,
        "review_cycle_id": review_cycle_id,
    }
    
    start_time = time.time()
    
    # Run orchestration nodes sequentially
    s1 = await understand_request_node(state)
    state.update(s1)
    
    s2 = await discover_capabilities_node(state)
    state.update(s2)
    
    s3 = await create_execution_plan_node(state)
    state.update(s3)
    if state.get("agent_plan_invalid"):
        return state
    
    s4 = await execute_model_node(state)
    state.update(s4)
    
    s5 = await evaluate_quality_and_decision_node(state)
    state.update(s5)
    
    s6 = await decide_next_action_node(state)
    state.update(s6)
    
    # Closed-loop evidence evaluation.  Each iteration observes the combined
    # result, lets the existing planner choose the next capability, and then
    # evaluates again.  decide_next_action_node enforces the hard bound and
    # routes unresolved uncertainty to the existing HITL path.
    while state.get("next_node") == "replan":
        s_replan = await replan_node(state)
        state.update(s_replan)

        # If replan itself decided to route to human_review (e.g. no valid models)
        # skip retry execution and fall through to persist/review.
        if state.get("next_node") != "human_review":
            # Bug 3 fix: snapshot original detections BEFORE retry execution so
            # we can combine them with retry results instead of discarding them.
            prior_raw_detections = list(state.get("raw_detections", []))

            asset_id = state.get("asset_id") or state["asset_snapshot"].get("id")
            logger.info(
                "retry_execution_started",
                asset_id=asset_id,
                retry_models=list((state.get("execution_plan") or {}).get("models", [])),
                missing_labels=state.get("missing_labels", []),
                replan_count=state.get("replan_count", 0),
            )

            s4_retry = await execute_model_node(state)

            retry_raw = s4_retry.get("raw_detections", [])
            logger.info(
                "retry_execution_completed",
                asset_id=asset_id,
                retry_raw_count=len(retry_raw),
                models_executed=s4_retry.get("models_executed", []),
            )

            # Bug 3 fix: combine original + retry raw detections, then re-fuse
            # through the existing merge pipeline so NMS deduplication applies
            # across the full combined candidate set.
            # Original detections (Cars, Pedestrians) are NOT discarded.
            combined_raw = prior_raw_detections + retry_raw
            ontology = list(state["project_snapshot"].get("labels", []))
            onto_index = build_ontology_index(ontology)
            combined_merged, combined_stats = merge_detections(
                detections=combined_raw,
                index=onto_index,
            )
            logger.info(
                "retry_fusion_completed",
                asset_id=asset_id,
                prior_raw_count=len(prior_raw_detections),
                retry_raw_count=len(retry_raw),
                combined_raw_count=len(combined_raw),
                combined_merged_count=len(combined_merged),
            )

            # Merge the retry execution state into pipeline state, then
            # override detections with the combined+fused set.
            prior_history = list(state.get("execution_history", []))
            state.update(s4_retry)
            # execute_model_node owns the ledger; retain it even if a custom
            # runtime/node returns a partial state.
            if not state.get("execution_history"):
                state["execution_history"] = prior_history
            state["raw_detections"] = combined_raw
            state["merged_detections"] = combined_merged
            state["fusion_conflicts"] = list(stats_to_dict(combined_stats).get("conflict_records") or [])

            # Quality recheck on the full combined result
            logger.info(
                "quality_recheck_started",
                asset_id=asset_id,
                combined_count=len(combined_merged),
                replan_count=state.get("replan_count", 0),
            )
            s5_retry = await evaluate_quality_and_decision_node(state)
            state.update(s5_retry)
            logger.info(
                "quality_recheck_completed",
                asset_id=asset_id,
                quality_action=(state.get("quality_agent_decision") or {}).get("action"),
                quality_reason=(state.get("quality_agent_decision") or {}).get("reason"),
            )
            s6_retry = await decide_next_action_node(state)
            state.update(s6_retry)
        else:
            break

    s7 = await persist_and_analytics_node(state)
    state.update(s7)
    
    total_ms = (time.time() - start_time) * 1000.0
    timings = dict(state.get("timings", {}))
    timings["total_ms"] = total_ms
    state["timings"] = timings
    state["duration_ms"] = total_ms
    
    if audit:
        audit.duration_ms = total_ms
        audit.timings = timings
        
    logger.info(
        "agent_run_completed",
        agent_run_id=audit.agent_run_id if audit else None,
        duration_ms=total_ms,
        persisted_count=audit.persisted_annotation_count if audit else 0,
        final_status=state.get("final_status"),
        timings=timings,
    )
    
    return state
