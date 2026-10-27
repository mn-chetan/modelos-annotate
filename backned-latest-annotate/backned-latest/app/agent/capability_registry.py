"""Model Capability Registry — discovery and technical capability information only.

This registry answers: "What can this model technically do?"
The AGENT answers: "Which model should I use?"

CRITICAL: This registry must NOT:
  - assign models to labels
  - inject SAM2 because geometry is segmentation
  - inject YOLO as a default when no label matches
  - make any routing decision

It provides capability descriptors so the agent can make an informed decision.
"""

from __future__ import annotations

from typing import Any
from app.domain.enums import GeometryType
from app.inference.contracts import ModelKey
from app.logging import get_logger

logger = get_logger(__name__)


# COCO 80 class labels supported by yolo26 / closed-set detectors
COCO_80_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
    "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop",
    "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
}

# Standard ontology mapping normalization synonyms
LABEL_SYNONYMS: dict[str, str] = {
    "cars": "car",
    "car": "car",
    "buses": "bus",
    "bus": "bus",
    "trucks": "truck",
    "truck": "truck",
    "motorcycles": "motorcycle",
    "motorcycle": "motorcycle",
    "bicycles": "bicycle",
    "bicycle": "bicycle",
    "pedestrians": "person",
    "pedestrian": "person",
    "person": "person",
    "traffic lights": "traffic light",
    "traffic light": "traffic light",
    "traffic signs": "stop sign",
    "traffic sign": "stop sign",
    "stop sign": "stop sign",
}


class ModelCapabilityRegistry:
    """Central registry of model capabilities, supported classes, and geometry constraints."""

    def __init__(self, available_models: dict[str, bool] | None = None) -> None:
        self.available_models = available_models or {
            ModelKey.YOLO26.value: True,
            ModelKey.FASTER_RCNN.value: True,
            ModelKey.DINO.value: True,
            ModelKey.SAM2.value: True,
            ModelKey.CLIP.value: True,
            ModelKey.FLORENCE.value: True,
        }

        self.capabilities: dict[str, dict[str, Any]] = {
            ModelKey.YOLO26.value: {
                "task_types": ["object_detection"],
                "geometry_types": [GeometryType.BOX.value],
                "open_vocabulary": False,
                "supported_classes": list(COCO_80_CLASSES),
                "precision": "high",
                "speed": "fast",
            },
            ModelKey.FASTER_RCNN.value: {
                "task_types": ["object_detection"],
                "geometry_types": [GeometryType.BOX.value],
                "open_vocabulary": False,
                "supported_classes": list(COCO_80_CLASSES),
                "precision": "very_high",
                "speed": "medium",
            },
            ModelKey.DINO.value: {
                "task_types": ["object_detection", "open_vocabulary_detection"],
                "geometry_types": [GeometryType.BOX.value],
                "open_vocabulary": True,
                "supported_classes": "*",  # Supports any text prompt
                "precision": "high",
                "speed": "medium",
            },
            ModelKey.SAM2.value: {
                "task_types": ["instance_segmentation"],
                "geometry_types": [GeometryType.POLYGON.value, "mask"],
                "open_vocabulary": True,
                "supported_classes": "*",
                "precision": "very_high",
                "speed": "medium",
            },
            ModelKey.CLIP.value: {
                "task_types": ["classification", "attribute_classification"],
                "geometry_types": [GeometryType.CLASSIFICATION.value],
                "open_vocabulary": True,
                "supported_classes": "*",
                "precision": "high",
                "speed": "fast",
            },
            ModelKey.FLORENCE.value: {
                "task_types": ["captioning", "region_description"],
                "geometry_types": [GeometryType.BOX.value],
                "open_vocabulary": True,
                "supported_classes": "*",
                "precision": "medium",
                "speed": "slow",
            },
            "text_entity_extraction": {"modality": "text", "capability": "text_entity_extraction", "canonical_task": "ENTITY_EXTRACTION", "task_types": ["entity_extraction", "ner"], "geometry_types": ["text_span"], "open_vocabulary": True, "supported_classes": "*", "precision": "deterministic", "speed": "fast", "implementation": "GenericEntityExtractionService"},
            "text_sentiment_analysis": {"modality": "text", "capability": "text_sentiment_analysis", "canonical_task": "SENTIMENT_ANALYSIS", "task_types": ["sentiment_analysis", "sentiment"], "geometry_types": ["text_classification"], "open_vocabulary": True, "supported_classes": "*", "precision": "model_validated", "speed": "medium", "implementation": "SentimentService"},
            "text_classification": {"modality": "text", "capability": "text_classification", "canonical_task": "TEXT_CLASSIFICATION", "task_types": ["text_classification", "classification"], "geometry_types": ["text_classification"], "open_vocabulary": True, "supported_classes": "*", "precision": "model_validated", "speed": "medium", "implementation": "TextClassificationService"},
            "text_relation_extraction": {"modality": "text", "capability": "text_relation_extraction", "canonical_task": "RELATION_EXTRACTION", "task_types": ["relation_extraction", "relation"], "geometry_types": ["text_relation"], "open_vocabulary": True, "supported_classes": "*", "precision": "model_validated", "speed": "medium", "implementation": "RelationExtractionService"},
            "text_drug_matching": {"modality": "text", "capability": "text_drug_matching", "canonical_task": "DRUG_MATCHING", "task_types": ["drug_matching", "drug"], "geometry_types": ["text_span"], "open_vocabulary": False, "supported_classes": "*", "precision": "domain_validated", "speed": "medium", "implementation": "DrugMatchingService"},
            "all_text_features": {"modality": "text", "capability": "all_text_features", "canonical_task": "ALL_TEXT_FEATURES", "task_types": ["all_text_features", "all text features", "all_features", "all features"], "geometry_types": ["text_span", "text_classification", "text_relation"], "open_vocabulary": True, "supported_classes": "*", "precision": "model_validated", "speed": "slow", "implementation": "TextCapabilityService"},
        }

    def text_capabilities(self) -> dict[str, dict[str, Any]]:
        return {key: value for key, value in self.capabilities.items() if value.get("modality") == "text"}

    def resolve_text_task(self, raw_task: str | None) -> tuple[str, str]:
        """Resolve a text task through registered capability metadata."""
        value = str(raw_task or "").strip().lower().replace("_", " ")
        if "pii" in value or "personally identifiable" in value:
            return "UNSUPPORTED_TEXT_TASK", ""
        if "all text features" in value or "all features" in value or value == "all":
            return "ALL_TEXT_FEATURES", "all_text_features"
        for key, metadata in self.text_capabilities().items():
            aliases = set(metadata.get("task_types", [])) | {key, metadata.get("capability", key)}
            if any(alias.replace("_", " ").lower() in value for alias in aliases):
                return str(metadata["canonical_task"]), str(metadata.get("capability", key))
        entity = self.capabilities["text_entity_extraction"]
        return str(entity["canonical_task"]), str(entity["capability"])

    def check_class_capability(self, label: str) -> dict[str, Any]:
        """Check which models support a given class label.

        Detects capability gaps (e.g., 'Autos' / 'Auto-rickshaw' not in COCO_80).
        """
        raw = str(label).strip()
        norm = LABEL_SYNONYMS.get(raw.lower(), raw.lower())

        closed_set_candidates = []
        open_set_candidates = []

        for model_key, meta in self.capabilities.items():
            if not self.available_models.get(model_key, False):
                continue

            if meta["open_vocabulary"]:
                open_set_candidates.append(model_key)
            elif meta["supported_classes"] != "*" and norm in meta["supported_classes"]:
                closed_set_candidates.append(model_key)

        if closed_set_candidates:
            return {
                "requested_class": label,
                "capability_available": True,
                "support_type": "closed_vocabulary",
                "candidate_models": closed_set_candidates + open_set_candidates,
            }

        if open_set_candidates and ModelKey.DINO.value in open_set_candidates:
            return {
                "requested_class": label,
                "capability_available": True,
                "support_type": "open_vocabulary",
                "candidate_models": open_set_candidates,
            }

        # Capability gap! Class not supported by any active model.
        logger.warning("capability_gap_detected", requested_class=label)
        return {
            "requested_class": label,
            "capability_available": False,
            "reason": f"No configured model supports '{label}'",
            "recommended_action": f"Configure an Auto-capable or open-vocabulary model for '{label}'",
            "candidate_models": [],
        }

    def select_models_for_request(
        self,
        requested_labels: list[str],
        requested_geometry: str = "box",
        require_open_vocab: bool = False,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Return candidate models technically capable of servicing the request.

        IMPORTANT — CANDIDATES ONLY.
        This method identifies which models are capable of handling the labels
        and geometry. It does NOT select, assign, or inject models.
        The agent receives this candidate list and decides which models to use.

        Previously this method forced SAM2 for segmentation geometry and
        YOLO as a default fallback. Both have been removed — those are
        routing decisions that belong exclusively to the agent.
        """
        models_to_use: set[str] = set()
        gaps: list[dict[str, Any]] = []

        for label in requested_labels:
            cap = self.check_class_capability(label)
            if not cap["capability_available"]:
                gaps.append(cap)
            else:
                for m in cap["candidate_models"]:
                    # Segmentation is a separate tool capability. Keeping it
                    # out of detector candidates prevents this helper from
                    # becoming a semantic model selector.
                    if m == ModelKey.SAM2.value:
                        continue
                    if require_open_vocab:
                        if self.capabilities.get(m, {}).get("open_vocabulary"):
                            models_to_use.add(m)
                    else:
                        models_to_use.add(m)

        # NOTE: YOLO is NOT automatically added as a default.
        # The agent decides which candidate models to use in its plan.

        logger.info(
            "capabilities_discovered",
            requested_labels=requested_labels,
            requested_geometry=requested_geometry,
            candidate_models=sorted(models_to_use),
            capability_gaps=len(gaps),
        )

        return sorted(models_to_use), gaps
