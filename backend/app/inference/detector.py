"""Backward-compatible detector facade over the multi-model registry.

Prefer ``app.inference.registry`` for new code.

This facade additionally connects the dynamic routing/execution plan to
the actual detector adapter while preserving the existing API:

    predict_with_yolo(image_path, asset_id=...)

New callers can optionally provide:
    - ontology index
    - scene evidence
    - execution plan

The legacy call remains valid and uses the normal full-image strategy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.errors import ModelUnavailableError
from app.inference.adapters.fake import FakeYoloAdapter
from app.inference.adapters.yolo26 import Yolo26Adapter
from app.inference.contracts import NormalizedDetection
from app.inference.device import clamp_box, resolve_device
from app.inference.ontology_map import OntologyIndex
from app.inference.registry import (
    InferenceRuntime,
    create_registry_from_settings,
    get_runtime,
    set_runtime,
)
from app.inference.routing import InferenceExecutionPlan, SceneEvidence

# ---------------------------------------------------------------------------
# Backward-compatible exports
# ---------------------------------------------------------------------------

FakeDetector = FakeYoloAdapter
Detector = FakeYoloAdapter | Yolo26Adapter

Yolo26Detector = Yolo26Adapter

__all__ = [
    "FakeDetector",
    "Yolo26Detector",
    "NormalizedDetection",
    "InferenceExecutionPlan",
    "SceneEvidence",
    "clamp_box",
    "resolve_device",
    "get_detector",
    "set_detector",
    "create_detector_from_settings",
    "predict_with_yolo",
    "predict_with_plan",
    "get_runtime",
    "set_runtime",
]


_detector: Detector | None = None


# ---------------------------------------------------------------------------
# Existing detector facade
# ---------------------------------------------------------------------------


def get_detector() -> Detector | None:
    """Return the configured YOLO detector.

    Existing behavior is preserved.
    """

    if _detector is not None:
        return _detector

    runtime = get_runtime()

    det = runtime.registry.get("yolo26")
    if isinstance(det, (FakeYoloAdapter, Yolo26Adapter)):
        return det
    return None


def set_detector(
    detector: Detector | None,
) -> None:
    """Override the detector.

    Primarily useful for tests and backwards compatibility.
    """

    global _detector

    _detector = detector


# ---------------------------------------------------------------------------
# Detector construction
# ---------------------------------------------------------------------------


def create_detector_from_settings(
    settings: Any,
    *,
    force_fake: bool = False,
) -> Any:
    """Create YOLO adapter and initialize the multi-model runtime."""
    global _detector
    try:
        runtime = get_runtime()
        yolo_adapter = runtime.registry._adapters.get("yolo26")
        is_existing_fake = isinstance(yolo_adapter, (FakeYoloAdapter, FakeDetector)) if yolo_adapter else False
        requested_fake = force_fake
        if is_existing_fake == requested_fake:
            _detector = yolo_adapter
            return yolo_adapter
    except ModelUnavailableError:
        pass

    registry = create_registry_from_settings(
        settings,
        force_fake=force_fake,
    )

    runtime = InferenceRuntime(
        registry
    )

    set_runtime(runtime)

    try:
        det = registry.get("yolo26")
    except ModelUnavailableError:
        if force_fake:
            det = registry._adapters.get("yolo26")
            if det is None:
                raise
        else:
            raise
    set_detector(det)

    return det


# ---------------------------------------------------------------------------
# Dynamic execution
# ---------------------------------------------------------------------------


def _default_plan() -> InferenceExecutionPlan:
    """Return a backward-compatible default execution plan."""

    return InferenceExecutionPlan(
        models=("yolo26",),
        strategy="full_image",
        image_size=None,
        tile_rows=1,
        tile_cols=1,
        tile_overlap=0.0,
        verification="standard",
        retry_allowed=True,
        max_retries=2,
        reason=(
            "No dynamic scene evidence supplied; "
            "using backward-compatible full-image YOLO inference."
        ),
        evidence={},
        planner_source="backward_compatible_default",
        plan_version="routing_v2",
    )


def build_yolo_execution_plan(
    *,
    ontology_index: OntologyIndex | None = None,
    scene_evidence: SceneEvidence | None = None,
    yolo_enabled: bool = True,
    dino_enabled: bool = True,
    florence_enabled: bool = True,
    sam2_enabled: bool = True,
) -> InferenceExecutionPlan:
    """Reject legacy planning; plans are created only by the agent graph."""
    raise RuntimeError(
        "Legacy detector planning is disabled; use run_agentic_pipeline_graph()."
    )


# ---------------------------------------------------------------------------
# Plan-aware YOLO execution
# ---------------------------------------------------------------------------


def predict_with_plan(
    image_path: Path,
    *,
    asset_id: str,
    plan: InferenceExecutionPlan,
    labels: list[str] | None = None,
    confidence_threshold: float | None = None,
) -> list[NormalizedDetection]:
    """Execute YOLO using a dynamic routing plan.

    The plan is interpreted here and passed into the YOLO adapter.

    IMPORTANT:

        This function does not modify model confidence.

        confidence_threshold only controls which predictions YOLO emits.
        It does not become the prediction's confidence value.
    """

    detector: Detector | None = get_detector()

    if detector is None:
        raise RuntimeError(
            "YOLO detector is not initialized."
        )

    # ---------------------------------------------------------------
    # Fake adapter compatibility.
    #
    # Existing tests may use FakeYoloAdapter whose predict() method
    # only accepts the original arguments.
    #
    # We preserve that behavior rather than breaking tests.
    # ---------------------------------------------------------------

    if isinstance(
        detector,
        FakeYoloAdapter,
    ):
        return detector.predict(
            image_path,
            asset_id=asset_id,
            labels=labels,
        )

    # ---------------------------------------------------------------
    # Real YOLO adapter.
    # ---------------------------------------------------------------

    return detector.predict(
        image_path,
        asset_id=asset_id,
        labels=labels,
        strategy=plan.strategy,
        image_size=plan.image_size,
        tile_rows=plan.tile_rows,
        tile_cols=plan.tile_cols,
        tile_overlap=plan.tile_overlap,
        confidence_threshold=confidence_threshold,
        plan_source=plan.planner_source,
        plan_reason=plan.reason,
    )


# ---------------------------------------------------------------------------
# Backward-compatible entry point
# ---------------------------------------------------------------------------


def predict_with_yolo(
    image_path: Path,
    *,
    asset_id: str,
    ontology_index: OntologyIndex | None = None,
    scene_evidence: SceneEvidence | None = None,
    plan: InferenceExecutionPlan | None = None,
    labels: list[str] | None = None,
    confidence_threshold: float | None = None,
) -> list[NormalizedDetection]:
    """Run YOLO with optional dynamic/agentic planning.

    Existing code can continue doing:

        predict_with_yolo(
            image_path,
            asset_id=asset_id,
        )

    New agentic flow can do:

        predict_with_yolo(
            image_path,
            asset_id=asset_id,
            ontology_index=ontology_index,
            scene_evidence=evidence,
        )

    Or provide an already-approved agentic plan directly.
    """

    if plan is None:
        if (
            ontology_index is None
            and scene_evidence is None
        ):
            plan = _default_plan()

        else:
            plan = build_yolo_execution_plan(
                ontology_index=ontology_index,
                scene_evidence=scene_evidence,
            )

    # ---------------------------------------------------------------
    # Hard safety boundary:
    #
    # If the dynamic planner decided YOLO is not required, don't
    # execute it.
    #
    # This prevents "agentic" from becoming "run every model always".
    # ---------------------------------------------------------------

    if "yolo26" not in plan.models:
        return []

    return predict_with_plan(
        image_path,
        asset_id=asset_id,
        plan=plan,
        labels=labels,
        confidence_threshold=confidence_threshold,
    )