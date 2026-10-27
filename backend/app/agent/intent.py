"""Natural Language User Intent Understanding Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from app.inference.ontology_map import SAFE_ALIASES


@dataclass
class ParsedIntent:
    user_request: str = ""
    task_type: str = "detection"  # "detection" | "segmentation" | "classification"
    requested_labels: list[str] = field(default_factory=list)
    geometry_type: str = "box"  # "box" | "polygon" | "classification"
    high_precision: bool = False
    small_object_focus: bool = False
    open_vocabulary_required: bool = False
    spatial_context: str | None = None
    reasoning: str = ""
    spatial_labels: list[str] = field(default_factory=list)
    activity_labels: list[str] = field(default_factory=list)
    event_labels: list[str] = field(default_factory=list)


# Grouping terms to ontology categories
CATEGORY_EXPANSIONS: dict[str, list[str]] = {
    "vehicle": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles"],
    "vehicles": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles"],
    "traffic": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "traffic object": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "traffic objects": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "traffic detection": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "autonomous traffic": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "autonomous traffic detection": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "road traffic": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "traffic scene": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "traffic monitoring": ["Cars", "Buses", "Trucks", "Autos", "Motorcycles", "Pedestrians", "Bicycles", "Traffic lights", "Traffic signs", "Road barriers"],
    "road sign": ["Traffic signs"],
    "road signs": ["Traffic signs"],
    "signal": ["Traffic lights"],
    "signals": ["Traffic lights"],
}

_ACTIVITY_PATTERNS = re.compile(r"\b(activit|action|interaction|movement|behavior|running|walking|driving|crossing|lane_change)\b", re.IGNORECASE)
_EVENT_PATTERNS = re.compile(r"\b(event|collision|braking|crash|incident|across video frames)\b", re.IGNORECASE)

_EXPLICIT_OBJECT_ALIASES = {
    "person": "person", "people": "person", "pedestrian": "person", "pedestrians": "person",
    "car": "car", "cars": "car", "bus": "bus", "buses": "bus", "truck": "truck", "trucks": "truck",
    "motorcycle": "motorcycle", "motorcycles": "motorcycle", "motorbike": "motorcycle", "motorbikes": "motorcycle",
    "bicycle": "bicycle", "bicycles": "bicycle", "bike": "bicycle", "bikes": "bicycle",
    "auto": "auto", "autos": "auto", "auto rickshaw": "auto", "auto rickshaws": "auto",
    "auto-rickshaw": "auto", "auto-rickshaws": "auto", "autorickshaw": "auto", "autorickshaws": "auto",
}


def extract_explicit_object_labels(prompt: str, ontology: list[str] | None = None) -> list[str]:
    """Extract labels only when the request contains an explicit object list."""
    text = str(prompt or "").strip()
    lower = text.casefold()
    explicit_list = (
        "+" in text
        or bool(re.search(r"\b(?:objects?|classes?|categories?|targets?)\s*(?:are|include|:)", lower))
        or bool(re.search(r"\b(?:detect|find|identify|annotate|label)\b[^.!?\n]*,", lower))
        or bool(re.search(r"\b(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be)\s*(?:identified|detected|annotated|labeled|labelled|found)\b", lower))
    )
    if not explicit_list:
        return []

    configured = {str(label).strip().casefold(): str(label).strip() for label in (ontology or []) if str(label).strip()}
    configured_aliases = {
        key: configured.get(key, value)
        for value in configured.values()
        for key in (value.casefold(), SAFE_ALIASES.get(value.casefold(), value).casefold())
    }
    found: list[str] = []
    for alias in sorted(_EXPLICIT_OBJECT_ALIASES, key=len, reverse=True):
        if not re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", lower):
            continue
        canonical = _EXPLICIT_OBJECT_ALIASES[alias]
        result = configured_aliases.get(canonical.casefold(), canonical)
        if result not in found:
            found.append(result)
    return found


def parse_user_intent(
    user_prompt: str,
    project_ontology: list[str] | None = None,
    *,
    allow_generic_object_fallback: bool = True,
    modality: str | None = None,
    configured_task: str | None = None,
) -> ParsedIntent:
    """Parse natural language user prompt into structured intent.

    Decomposes prompts like:
    - 'Detect all vehicles.'
    - 'Segment every vehicle.'
    - 'Find motorcycles and draw accurate boxes.'
    - 'Detect small and distant objects.'
    """
    prompt = (user_prompt or "").strip()
    prompt_lower = prompt.lower()
    ontology = [str(lbl).strip() for lbl in (project_ontology or []) if str(lbl).strip()]

    if str(modality or "").lower() in {"text", "document"}:
        from app.agent.capability_registry import ModelCapabilityRegistry

        registry = ModelCapabilityRegistry()
        task_candidate = str(configured_task or "").strip()
        if task_candidate.lower().replace("_", " ") in {"", "object detection", "detection", "segmentation", "classification"}:
            task_candidate = prompt
        resolved_task, capability = registry.resolve_text_task(task_candidate)
        metadata = registry.text_capabilities().get(capability, {})
        geometry = str((metadata.get("geometry_types") or ["text_span"])[0])
        return ParsedIntent(
            user_request=prompt,
            task_type=resolved_task,
            requested_labels=list(ontology),
            geometry_type=geometry,
            open_vocabulary_required=True,
            reasoning=f"Resolved text modality through capability '{capability}'.",
            spatial_labels=list(ontology),
        )

    # 1. Determine task & geometry type
    if any(k in prompt_lower for k in ["segment", "mask", "outline", "contour", "polygon"]):
        task_type = "segmentation"
        geometry_type = "polygon"
    elif any(k in prompt_lower for k in ["classify", "attribute", "type"]):
        task_type = "classification"
        geometry_type = "classification"
    else:
        task_type = "detection"
        geometry_type = "box"

    # 2. Precision & Small Object flags
    high_precision = any(k in prompt_lower for k in ["precise", "accurat", "exact", "high precision"])
    small_object_focus = any(k in prompt_lower for k in ["small", "distant", "tiny", "far"])

    # 3. Resolve requested labels
    requested: set[str] = set()

    # Check category expansions (e.g. 'vehicles', 'traffic objects')
    for keyword, expanded in CATEGORY_EXPANSIONS.items():
        if keyword in prompt_lower:
            # Intersect expansion with ontology if ontology is available, else use expanded
            for exp_item in expanded:
                if not ontology or any(o.lower() == exp_item.lower() for o in ontology):
                    # Pick original casing from ontology
                    matched_onto = next((o for o in ontology if o.lower() == exp_item.lower()), exp_item)
                    requested.add(matched_onto)

    # Check direct ontology label matches
    for label in ontology:
        l_lower = label.lower()
        # Single or plural match
        if l_lower in prompt_lower or (l_lower + "s") in prompt_lower or l_lower.rstrip("s") in prompt_lower:
            requested.add(label)

    # Fallback to full ontology if no specific labels extracted
    if not requested:
        requested = set(ontology) if ontology else ({"object"} if allow_generic_object_fallback else set())

    all_sorted = sorted(requested)
    spatial_labels: list[str] = []
    activity_labels: list[str] = []
    event_labels: list[str] = []

    for lbl in all_sorted:
        if _EVENT_PATTERNS.search(lbl):
            event_labels.append(lbl)
        elif _ACTIVITY_PATTERNS.search(lbl):
            activity_labels.append(lbl)
        else:
            spatial_labels.append(lbl)

    # If spatial labels exist, spatial_labels is used for object detection
    detection_labels = spatial_labels if spatial_labels else all_sorted

    # An explicit multi-object requirement is authoritative for this request.
    # Ordinary prose still remains project-scoped, preventing goals such as
    # "traffic monitoring with cars and buses" from changing the ontology.
    explicit_labels = extract_explicit_object_labels(prompt, ontology)
    if explicit_labels:
        detection_labels = explicit_labels
        spatial_labels = list(explicit_labels)
        all_sorted = list(explicit_labels)
        activity_labels = []
        event_labels = []

    # Determine reasoning
    reasoning = (
        f"Interpreted intent for task '{task_type}' with geometry '{geometry_type}'. "
        f"Extracted {len(spatial_labels)} spatial object labels, {len(activity_labels)} activity labels, "
        f"and {len(event_labels)} event labels."
    )

    return ParsedIntent(
        user_request=prompt,
        task_type=task_type,
        requested_labels=detection_labels,
        geometry_type=geometry_type,
        high_precision=high_precision,
        small_object_focus=small_object_focus,
        open_vocabulary_required=False,
        reasoning=reasoning,
        spatial_labels=spatial_labels,
        activity_labels=activity_labels,
        event_labels=event_labels,
    )
