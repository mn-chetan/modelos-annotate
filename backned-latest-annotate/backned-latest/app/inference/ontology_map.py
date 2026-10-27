"""Deterministic raw-model-label -> project ontology mapping.

The ontology mapper is intentionally deterministic.

Responsibilities:
    - Accept only labels supported by the project ontology.
    - Preserve the original model label and confidence.
    - Apply only explicit, safe ontology mappings.
    - Never infer a fine-grained class from geometry.
    - Never convert a generic label such as ``vehicle`` into ``car``.
    - Never modify model confidence.

Agentic planning belongs to the routing/orchestration layer.
This module is the deterministic semantic safety boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.inference.contracts import NormalizedDetection

MAPPING_VERSION = "ontology_map_v2"

# Human-created incomplete annotations may use this explicit class.
UNLABELED = "Unlabeled"


MapMethod = Literal[
    "exact",
    "alias",
    "includes_synonym",
    "closed_vocab",
    "suppress",
]


# ---------------------------------------------------------------------------
# SAFE CLOSED-VOCABULARY MAPPINGS
# ---------------------------------------------------------------------------
#
# IMPORTANT:
#
# These mappings are used ONLY when the destination parent/class explicitly
# exists in the project's ontology.
#
# Do NOT put semantic guesses here.
#
# Examples of intentionally REMOVED mappings:
#
#     van -> truck
#     scooter -> motorcycle
#     vehicle -> car
#
# Those are not universally equivalent classes.
#
# If the project ontology explicitly contains "van", the model can map
# "van" to "van" through exact matching.
#
# If the project ontology contains only "truck", a raw "van" prediction
# must NOT silently become "truck".
#
SAFE_CLOSED_VOCAB_PARENTS: dict[str, str] = {
    # COCO / common exact semantic classes
    "person": "person",
    "bicycle": "bicycle",
    "car": "car",
    "motorcycle": "motorcycle",
    "airplane": "airplane",
    "bus": "bus",
    "train": "train",
    "truck": "truck",
    "boat": "boat",
    "fire hydrant": "fire hydrant",
    "stop sign": "stop_sign",
    "stop_sign": "stop_sign",
    "parking meter": "parking meter",
    "bench": "bench",
    "bird": "bird",
    "cat": "cat",
    "dog": "dog",
    "horse": "horse",
    "sheep": "sheep",
    "cow": "cow",
    "elephant": "elephant",
    "bear": "bear",
    "zebra": "zebra",
    "giraffe": "giraffe",
    "backpack": "backpack",
    "umbrella": "umbrella",
    "handbag": "handbag",
    "tie": "tie",
    "suitcase": "suitcase",
    "frisbee": "sports equipment",
    "skis": "sports equipment",
    "snowboard": "sports equipment",
    "sports ball": "sports equipment",
    "kite": "sports equipment",
    "baseball bat": "sports equipment",
    "baseball glove": "sports equipment",
    "skateboard": "sports equipment",
    "surfboard": "sports equipment",
    "tennis racket": "sports equipment",
    "bottle": "glassware",
    "wine glass": "glassware",
    "cup": "glassware",
    "fork": "utensil",
    "knife": "utensil",
    "spoon": "utensil",
    "bowl": "glassware",
    "banana": "food",
    "apple": "food",
    "sandwich": "food",
    "orange": "food",
    "broccoli": "food",
    "carrot": "food",
    "hot dog": "food",
    "pizza": "food",
    "donut": "food",
    "cake": "food",
    "chair": "furniture",
    "couch": "furniture",
    "potted plant": "plant",
    "bed": "furniture",
    "dining table": "furniture",
    "toilet": "furniture",
    "tv": "electronics",
    "laptop": "electronics",
    "mouse": "electronics",
    "remote": "electronics",
    "keyboard": "electronics",
    "cell phone": "electronics",
    "microwave": "appliance",
    "oven": "appliance",
    "toaster": "appliance",
    "sink": "appliance",
    "refrigerator": "appliance",
    "book": "book",
    "clock": "clock",
    "vase": "glassware",
    "scissors": "tool",
    "teddy bear": "toy",
    "hair drier": "appliance",
    "toothbrush": "tool",
}

CLOSED_VOCAB_PARENTS = SAFE_CLOSED_VOCAB_PARENTS


# ---------------------------------------------------------------------------
# SAFE ALIASES
# ---------------------------------------------------------------------------
#
# Aliases are spelling/lexical equivalents, NOT semantic conversions.
#
# Examples:
#     motorbike -> motorcycle
#     bike -> bicycle
#
# These are safe because they are common lexical variants of the same
# concept.
#
# Intentionally NOT included:
#     van -> truck
#     scooter -> motorcycle
#     vehicle -> car
#
SAFE_ALIASES: dict[str, str] = {
    "motorbike": "motorcycle",
    "bike": "bicycle",
    "aeroplane": "airplane",
    "automobile": "car",
    "traffic signal": "traffic light",
    "traffic_signal": "traffic light",
    "cars": "car",
    "buses": "bus",
    "trucks": "truck",
    "motorcycles": "motorcycle",
    "pedestrians": "person",
    "pedestrian": "person",
    "traffic lights": "traffic light",
    "people": "person",
    "bicycles": "bicycle",
    "airplanes": "airplane",
    "trains": "train",
    "boats": "boat",
    "birds": "bird",
    "cats": "cat",
    "dogs": "dog",
    "horses": "horse",
    "autos": "auto",
    "auto rickshaw": "auto",
    "auto rickshaws": "auto",
    "auto-rickshaw": "auto",
    "auto-rickshaws": "auto",
    "autorickshaw": "auto",
    "rickshaw": "auto",
    "three wheeler": "auto",
    "three wheelers": "auto",
    "traffic sign": "traffic sign",
    "traffic signs": "traffic sign",
    "road barrier": "road barrier",
    "road barriers": "road barrier",
}

# Model vocabularies commonly use a lowercase singular class name while a
# project ontology may deliberately use a title-cased plural label. These are
# semantic equivalents, not a replacement for the project's canonical name.
MODEL_LABEL_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "car": ("car", "cars"),
    "cars": ("cars", "car"),
    "bus": ("bus", "buses"),
    "buses": ("buses", "bus"),
    "truck": ("truck", "trucks"),
    "trucks": ("trucks", "truck"),
    "motorcycle": ("motorcycle", "motorcycles"),
    "motorcycles": ("motorcycles", "motorcycle"),
    "bicycle": ("bicycle", "bicycles"),
    "bicycles": ("bicycles", "bicycle"),
    "person": ("person", "people", "pedestrian", "pedestrians"),
    "people": ("people", "person", "pedestrian", "pedestrians"),
    "pedestrian": ("pedestrian", "pedestrians", "person", "people"),
    "pedestrians": ("pedestrians", "pedestrian", "person", "people"),
    "traffic light": ("traffic light", "traffic lights"),
    "traffic lights": ("traffic lights", "traffic light"),
    "traffic_light": ("traffic_light", "traffic light", "traffic lights"),
    "stop sign": ("stop sign", "traffic signs", "traffic sign", "stop_sign"),
    "stop_sign": ("stop_sign", "stop sign", "traffic signs", "traffic sign"),
    "traffic sign": ("traffic sign", "traffic signs", "stop sign", "stop_sign"),
    "traffic signs": ("traffic signs", "traffic sign", "stop sign", "stop_sign"),
    "road barrier": ("road barrier", "road barriers", "barrier"),
    "road barriers": ("road barriers", "road barrier", "barrier"),
    "barrier": ("barrier", "road barrier", "road barriers"),
    "auto": ("auto", "autos"),
    "autos": ("autos", "auto"),
    "auto rickshaw": ("auto", "auto rickshaw", "auto rickshaws", "autorickshaw", "rickshaw", "three wheeler", "three wheelers"),
    "auto rickshaws": ("auto", "auto rickshaw", "auto rickshaws", "autorickshaw", "rickshaw", "three wheeler", "three wheelers"),
    "autorickshaw": ("auto", "auto rickshaw", "auto rickshaws", "autorickshaw", "rickshaw", "three wheeler", "three wheelers"),
    "rickshaw": ("auto", "auto rickshaw", "auto rickshaws", "autorickshaw", "rickshaw", "three wheeler", "three wheelers"),
    "three wheeler": ("auto", "auto rickshaw", "auto rickshaws", "autorickshaw", "rickshaw", "three wheeler", "three wheelers"),
    "three wheelers": ("auto", "auto rickshaw", "auto rickshaws", "autorickshaw", "rickshaw", "three wheeler", "three wheelers"),
}

def clean_canonical_label(raw: str) -> str:
    """Normalize raw prompt/goal text into a clean canonical object class name.

    Strips instruction prefixes (e.g. 'Precisely segment', 'Identify and annotate')
    and trailing clauses (e.g. 'should be identified', 'using accurate object boundaries').
    """
    if not raw or not isinstance(raw, str):
        return ""
    text = raw.strip()

    # Strip leading instruction verbs/phrases
    text = re.sub(
        r"^(?:please\s+)?(?:precisely|accurately|carefully)?\s*(?:segment|detect|identify|annotate|find|track|locate|extract|label|classify|recognize)\s+(?:and\s+(?:annotate|segment|detect|label)\s+)?(?:all\s+)?(?:the\s+)?",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Strip trailing instruction / verb clauses like "should be identified"
    text = re.sub(
        r"\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be|will\s+be|are\s+to\s+be|ought\s+to\s+be)\s*(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be)$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s+(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located)$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Strip trailing scene context like "in the traffic images"
    text = re.sub(
        r"\s+(?:in|from|within)\s+(?:the\s+)?(?:traffic\s+)?(?:images?|photos?|pictures?|video|frame|scene).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Strip trailing clause phrases like "using accurate object boundaries"
    text = re.sub(
        r"\s+(?:using|with|for)\s+(?:accurate|precise|instance|pixel)?\s*(?:object\s+)?(?:boundaries|masks|boxes|polygons).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Strip generic suffix tokens like objects, targets
    text = re.sub(
        r"\s+(?:objects?|targets?|instances?|items?|classes?|categories?)$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Strip trailing punctuation
    text = text.strip(" .,;:-")

    # Safe alias normalization (e.g. "cars" -> "car", "pedestrians" -> "person")
    key = text.strip().lower()
    if key in SAFE_ALIASES:
        return SAFE_ALIASES[key]

    return text or raw.strip()



# ---------------------------------------------------------------------------
# SAFE SPECIFIC-TO-GENERAL MAPPINGS (GENERALIZATIONS)
# ---------------------------------------------------------------------------
#
# These are used to resolve specific detected classes into generic ontology classes.
# Mapping specific -> general is semantically valid (e.g., a car is a vehicle).
#
CATEGORY_GENERALIZATIONS: dict[str, str] = {
    "car": "vehicle",
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "vehicle",
    "bicycle": "vehicle",
    "van": "vehicle",
    "pickup": "vehicle",
    "suv": "vehicle",
    "airplane": "vehicle",
    "train": "vehicle",
    "boat": "vehicle",
    "person": "pedestrian",
    "pedestrian": "person",
}


# ---------------------------------------------------------------------------
# GENERIC / AMBIGUOUS LABELS
# ---------------------------------------------------------------------------
#
# These labels are not automatically converted to a fine-grained class.
#
# If the project ontology explicitly contains "vehicle", exact matching
# can still accept "vehicle".
#
# But if the ontology contains:
#
#     car
#     truck
#     bus
#     motorcycle
#
# and the model outputs:
#
#     vehicle
#
# then "vehicle" is suppressed rather than guessed into one of them.
#
GENERIC_AMBIGUOUS_LABELS = {
    "vehicle",
    "object",
    "item",
    "thing",
    "thing object",
}

# These are workflow/action strings or generic project titles, never ontology categories. Keep this
# guard independent of ontology availability so UI/title text cannot enter storage.
INVALID_WORKFLOW_LABELS = {
    "automatically identify",
    "auto identify",
    "identify automatically",
    "select all",
    "start annotation",
    "autonomous traffic detection",
    "traffic detection",
    "autonomous traffic",
    "traffic objects",
    "identify all objects",
    "identify all relevant objects",
    "identify all relevant objects in the image",
}


def is_invalid_workflow_label(value: str | None) -> bool:
    return _norm(value or "") in {_norm(label) for label in INVALID_WORKFLOW_LABELS}


def _norm(value: str) -> str:
    """Normalize text for deterministic comparison."""

    return re.sub(
        r"[\s_\-]+",
        " ",
        (value or "").strip().casefold(),
    )


def _tokenize_includes(includes: str) -> list[str]:
    """Split ontology includes prose into explicit synonym candidates.

    Includes are treated as ontology-provided evidence.

    The mapper does NOT invent additional synonyms.
    """

    if not includes or not includes.strip():
        return []

    text = includes

    parts = re.split(
        r"[,;/]| \band\b | \bor\b ",
        text,
        flags=re.IGNORECASE,
    )

    output: list[str] = []

    for part in parts:
        cleaned = re.sub(
            r"[^a-zA-Z0-9 \-]",
            " ",
            part,
        )

        cleaned = _norm(cleaned)

        if not cleaned or len(cleaned) < 2:
            continue

        cleaned = re.sub(
            r"^(?:a|an|the|partial|fully|visible|when|treated|as)\s+",
            "",
            cleaned,
        )

        cleaned = _norm(cleaned)

        if not cleaned or len(cleaned) < 2:
            continue

        output.append(cleaned)

        # For a phrase such as:
        #
        #     "road vehicle"
        #
        # we retain the phrase itself but do NOT automatically convert
        # "road" or "vehicle" into another ontology class.
        #
        # Therefore we intentionally do NOT add the first token here.

    return output


@dataclass(frozen=True)
class OntologyLabelSpec:
    """Approved project ontology label."""

    name: str
    aliases: tuple[str, ...] = ()
    includes: str = ""


@dataclass
class OntologyIndex:
    """Lookup index for a project's approved ontology."""

    canonical_by_norm: dict[str, str] = field(default_factory=dict)
    specs: list[OntologyLabelSpec] = field(default_factory=list)

    @property
    def canonical_names(self) -> list[str]:
        seen: list[str] = []

        for spec in self.specs:
            if spec.name not in seen:
                seen.append(spec.name)

        return seen

    def has(self, name: str) -> bool:
        return _norm(name) in self.canonical_by_norm

    def resolve_exact(self, raw: str) -> str | None:
        """Resolve canonical name, explicit alias, or explicit include."""

        return self.canonical_by_norm.get(_norm(raw))

    def resolve_canonical_name(self, raw: str) -> str | None:
        """Match ONLY an approved canonical ontology name."""

        key = _norm(raw)

        for spec in self.specs:
            if _norm(spec.name) == key:
                return spec.name

        return None

    def resolve_model_label(self, raw: str) -> str | None:
        """Resolve a model label to the exact project ontology spelling."""
        normalized = _norm(raw)
        candidates = list(MODEL_LABEL_EQUIVALENTS.get(normalized, (normalized,)))
        if normalized.endswith("s") and len(normalized) > 2:
            candidates.append(normalized[:-1])
        else:
            candidates.append(f"{normalized}s")
        for candidate in dict.fromkeys(candidates):
            resolved = self.resolve_exact(candidate)
            if resolved is not None:
                return resolved
        return None


def build_ontology_index(
    labels: list[str] | list[dict[str, Any]] | None,
    *,
    ontology: list[dict[str, Any]] | None = None,
) -> OntologyIndex:
    """Build a deterministic project ontology index.

    Priority:

        canonical label
            ↓
        explicit alias
            ↓
        explicit ontology include/synonym
            ↓
        safe closed-vocabulary mapping

    No fuzzy matching is performed.
    """

    index = OntologyIndex()

    rich = list(ontology or [])
    flat = list(labels or [])

    entries: list[OntologyLabelSpec] = []

    if rich:
        for item in rich:
            if isinstance(item, str):
                name = item.strip()
                cleaned = clean_canonical_label(name)
                if cleaned and name:
                    aliases = (name,) if cleaned != name else ()
                    entries.append(OntologyLabelSpec(name=cleaned, aliases=aliases))
                continue

            if not isinstance(item, dict):
                continue

            name = str(item.get("name") or "").strip()
            if not name:
                continue

            cleaned = clean_canonical_label(name)
            raw_aliases = [
                str(alias).strip()
                for alias in (item.get("aliases") or [])
                if str(alias).strip()
            ]
            if cleaned != name and name not in raw_aliases:
                raw_aliases.append(name)
            aliases = tuple(raw_aliases)
            includes = str(item.get("includes") or "")

            entries.append(
                OntologyLabelSpec(
                    name=cleaned or name,
                    aliases=aliases,
                    includes=includes,
                )
            )

    else:
        for name in flat:
            normalized_name = str(name).strip()
            if normalized_name:
                cleaned = clean_canonical_label(normalized_name)
                aliases = (normalized_name,) if cleaned != normalized_name else ()
                entries.append(
                    OntologyLabelSpec(
                        name=cleaned or normalized_name,
                        aliases=aliases,
                    )
                )

    # Ensure flat labels also appear when a rich ontology is supplied.
    known = {
        _norm(entry.name)
        for entry in entries
    }

    for name in flat:
        normalized_name = str(name).strip()

        if (
            normalized_name
            and _norm(normalized_name) not in known
        ):
            entries.append(
                OntologyLabelSpec(
                    name=normalized_name
                )
            )

            known.add(
                _norm(normalized_name)
            )

    # Build canonical + explicit alias/include lookup.
    for spec in entries:
        index.specs.append(spec)

        # Canonical label.
        index.canonical_by_norm[
            _norm(spec.name)
        ] = spec.name

        # Explicit aliases.
        for alias in spec.aliases:
            key = _norm(alias)

            if (
                key
                and key not in index.canonical_by_norm
            ):
                index.canonical_by_norm[key] = spec.name

        # Explicit ontology-provided synonyms.
        for synonym in _tokenize_includes(
            spec.includes
        ):
            if synonym not in index.canonical_by_norm:
                index.canonical_by_norm[
                    synonym
                ] = spec.name

    return index


@dataclass(frozen=True)
class MapResult:
    """Complete semantic mapping decision."""

    accepted: bool
    canonical_label: str | None
    raw_model_label: str
    mapping_method: MapMethod

    mapping_version: str = MAPPING_VERSION

    # Original model confidence.
    raw_model_confidence: float | None = None

    # Explicit reason for audit/debugging.
    suppression_reason: str | None = None

    def provenance(self) -> dict[str, Any]:
        normalized_raw = _norm(self.raw_model_label)
        mapping_status = "MAPPED" if self.accepted and self.canonical_label else "UNMAPPED_DETECTION"
        mapping_reason = (
            "canonical ontology match"
            if self.accepted and self.canonical_label
            else self.suppression_reason or "label_not_in_project_ontology"
        )
        return {
            "raw_model_label": self.raw_model_label,
            "normalized_raw_label": normalized_raw,
            "canonical_label": self.canonical_label,
            "mapping_method": self.mapping_method,
            "mapping_status": mapping_status,
            "mapping_reason": mapping_reason,
            "mapping_version": self.mapping_version,
            "raw_model_confidence": self.raw_model_confidence,
            "ontology_suppression_reason": self.suppression_reason,
        }


def map_raw_label(
    raw_label: str,
    index: OntologyIndex,
    *,
    confidence: float | None = None,
) -> MapResult:
    """Map a raw model label onto the approved project ontology.

    Decision order:

        1. Empty label -> suppress.
        2. No ontology -> explicit pass-through for intake/testing.
        3. Exact canonical label.
        4. Explicit ontology alias.
        5. Explicit ontology include/synonym.
        6. Safe closed-vocabulary mapping.
        7. Suppress.

    IMPORTANT:

    A generic model label such as ``vehicle`` is NEVER converted into
    ``car``, ``truck``, ``bus`` or ``motorcycle`` based on confidence,
    bounding-box overlap, model agreement, or scene assumptions.
    """

    raw = (raw_label or "").strip()

    if is_invalid_workflow_label(raw):
        return MapResult(
            accepted=False,
            canonical_label=None,
            raw_model_label=raw,
            mapping_method="suppress",
            raw_model_confidence=confidence,
            suppression_reason="workflow_or_ui_label",
        )

    if not raw:
        return MapResult(
            accepted=False,
            canonical_label=None,
            raw_model_label=raw,
            mapping_method="suppress",
            raw_model_confidence=confidence,
            suppression_reason="empty_model_label",
        )

    # ---------------------------------------------------------------
    # No ontology available.
    #
    # Preserve existing intake/test behavior, but explicitly mark the
    # result as pass-through rather than pretending it was verified
    # against a project ontology.
    # ---------------------------------------------------------------
    if not index.canonical_names:
        return MapResult(
            accepted=True,
            canonical_label=raw,
            raw_model_label=raw,
            mapping_method="exact",
            raw_model_confidence=confidence,
        )

    normalized_raw = _norm(raw)

    # ---------------------------------------------------------------
    # 1. Exact canonical match
    # ---------------------------------------------------------------
    canonical = index.resolve_canonical_name(raw)

    if canonical is not None:
        return MapResult(
            accepted=True,
            canonical_label=canonical,
            raw_model_label=raw,
            mapping_method="exact",
            raw_model_confidence=confidence,
        )

    # ---------------------------------------------------------------
    # 2. Explicit project alias / include synonym
    # ---------------------------------------------------------------
    hit = index.resolve_exact(raw)

    if hit is not None:
        mapping_method: MapMethod = "alias"

        for spec in index.specs:
            if spec.name != hit:
                continue

            if any(
                _norm(alias) == normalized_raw
                for alias in spec.aliases
            ):
                mapping_method = "alias"
                break

            if normalized_raw in {
                _norm(synonym)
                for synonym in _tokenize_includes(
                    spec.includes
                )
            }:
                mapping_method = "includes_synonym"
                break

        return MapResult(
            accepted=True,
            canonical_label=hit,
            raw_model_label=raw,
            mapping_method=mapping_method,
            raw_model_confidence=confidence,
        )

    # Resolve model singular/plural and common model-vocabulary variants
    # against the current project's canonical ontology before global aliases.
    model_hit = index.resolve_model_label(raw)
    if model_hit is not None:
        return MapResult(
            accepted=True,
            canonical_label=model_hit,
            raw_model_label=raw,
            mapping_method="alias",
            raw_model_confidence=confidence,
        )

    # ---------------------------------------------------------------
    # 2b. Safe global aliases mapping
    # ---------------------------------------------------------------
    global_alias = SAFE_ALIASES.get(normalized_raw)
    if global_alias:
        target = index.resolve_exact(global_alias)
        if target is not None:
            return MapResult(
                accepted=True,
                canonical_label=target,
                raw_model_label=raw,
                mapping_method="alias",
                raw_model_confidence=confidence,
            )

    # ---------------------------------------------------------------
    # 3. Safe closed-vocabulary mapping
    # ---------------------------------------------------------------
    #
    # Only map if the destination is explicitly a canonical ontology
    # member.
    #
    # Example:
    #
    #     raw = "car"
    #     ontology = ["car", "person"]
    #
    # exact match already handles it.
    #
    # This section mainly supports safe model vocabulary aliases that
    # correspond to a known canonical class.
    # ---------------------------------------------------------------
    parent = SAFE_CLOSED_VOCAB_PARENTS.get(
        normalized_raw
    )

    if parent:
        target = index.resolve_canonical_name(parent)

        if target is not None:
            return MapResult(
                accepted=True,
                canonical_label=target,
                raw_model_label=raw,
                mapping_method="closed_vocab",
                raw_model_confidence=confidence,
            )

    # Specific-to-general category mapping fallback
    general_parent = CATEGORY_GENERALIZATIONS.get(normalized_raw)
    if general_parent:
        target = index.resolve_canonical_name(general_parent)

        if target is not None:
            return MapResult(
                accepted=True,
                canonical_label=target,
                raw_model_label=raw,
                mapping_method="closed_vocab",
                raw_model_confidence=confidence,
            )

    # ---------------------------------------------------------------
    # 4. Explicitly reject ambiguous generic labels.
    # ---------------------------------------------------------------
    if normalized_raw in GENERIC_AMBIGUOUS_LABELS:
        return MapResult(
            accepted=False,
            canonical_label=None,
            raw_model_label=raw,
            mapping_method="suppress",
            raw_model_confidence=confidence,
            suppression_reason=(
                "generic_ambiguous_label_requires_explicit_"
                "ontology_support_or_verification"
            ),
        )

    # ---------------------------------------------------------------
    # 5. Unknown label.
    # ---------------------------------------------------------------
    return MapResult(
        accepted=False,
        canonical_label=None,
        raw_model_label=raw,
        mapping_method="suppress",
        raw_model_confidence=confidence,
        suppression_reason="label_not_in_project_ontology",
    )


def is_allowed_annotation_label(
    label: str,
    index: OntologyIndex,
) -> bool:
    """Return True only for an approved ontology label.

    ``Unlabeled`` is retained as an explicit human annotation state.
    """

    name = (label or "").strip()

    if not name:
        return False

    if _norm(name) == _norm(UNLABELED):
        return True

    return index.resolve_canonical_name(name) is not None


def apply_mapping_to_detection(
    det: NormalizedDetection,
    index: OntologyIndex,
) -> tuple[
    NormalizedDetection | None,
    MapResult,
]:
    """Map one detection while preserving model evidence."""

    provenance = det.provenance or {}

    # DINO can return an unusable text token even though its requested prompt
    # yielded a valid detection. Prefer its explicit mapped label, then use the
    # explicit requested prompt as a semantic fallback. The fallback is still
    # validated against this project's ontology below; it does not change the
    # model confidence or skip any quality/verification stage.
    mapped_label = (
        provenance.get("canonical_label")
        if det.model_key == "dino" and provenance.get("mapping_status") == "MAPPED"
        else None
    )
    raw_model_label = str(
        provenance.get("raw_label")
        or provenance.get("raw_model_label")
        or det.label
        or ""
    ).strip()
    raw = str(mapped_label or raw_model_label).strip()

    dino_unusable_label = raw.casefold() in {
        "",
        ".",
        "unmapped",
        "unknown",
        "none",
        "null",
        "n/a",
        "[pad]",
        "[cls]",
        "[sep]",
    }
    if det.model_key == "dino" and dino_unusable_label:
        requested = provenance.get("requested_label")
        if isinstance(requested, (list, tuple)):
            requested = requested[0] if requested else ""
        requested = str(requested or "").strip()
        if requested and not is_invalid_workflow_label(requested):
            raw = requested
            provenance = {
                **provenance,
                "mapping_fallback": "requested_dino_prompt",
                "mapping_fallback_raw_label": raw_model_label,
            }

    result = map_raw_label(
        raw,
        index,
        confidence=det.confidence,
    )

    mapped_provenance = {
        **provenance,
        **result.provenance(),

        "model_key": det.model_key,
        "model_id": det.model_id,

        # Explicit semantic contract.
        "confidence_semantics": "original_model_confidence_only",
    }

    if not result.accepted or not result.canonical_label:
        return None, result

    mapped = NormalizedDetection(
        id=det.id,
        asset_id=det.asset_id,

        # Only ontology-approved label.
        label=result.canonical_label,

        class_id=det.class_id,
        bbox=det.bbox,

        # CRITICAL:
        # Never replace model confidence with mapping score,
        # ontology confidence, agreement, IoU, or quality.
        confidence=det.confidence,

        model_id=det.model_id,
        model_key=det.model_key,
        inferred_at=det.inferred_at,
        provenance=mapped_provenance,
    )

    return mapped, result


def map_detections(
    detections: list[NormalizedDetection],
    index: OntologyIndex,
) -> tuple[
    list[NormalizedDetection],
    list[MapResult],
]:
    """Map detections and retain every mapping decision for audit."""

    kept: list[NormalizedDetection] = []
    results: list[MapResult] = []

    for det in detections:
        mapped, result = apply_mapping_to_detection(
            det,
            index,
        )

        results.append(result)

        if mapped is not None:
            kept.append(mapped)

    return kept, results
