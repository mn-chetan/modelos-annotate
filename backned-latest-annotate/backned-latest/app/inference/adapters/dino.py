"""Grounding DINO open-vocabulary detection adapter (Hugging Face)."""

from __future__ import annotations

import time
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

from app.errors import ModelUnavailableError
from app.inference.contracts import ModelCapability, ModelKey, NormalizedDetection
from app.inference.device import clamp_box, resolve_device
from app.logging import get_logger

logger = get_logger(__name__)


def _semantic_target(raw: str) -> str:
    text = (raw or "").strip().lstrip("#")
    text = text.split(".", 1)[0].strip()
    text = text.replace("_", " ").casefold()
    text = re.sub(r"\s*-\s*", "-", text)
    # Strip instruction prefixes
    text = re.sub(
        r"^(?:please\s+)?(?:precisely|accurately|carefully)?\s*(?:segment|detect|identify|annotate|find|track|locate|extract|label|classify|recognize)\s+(?:and\s+(?:annotate|segment|detect|label)\s+)?(?:all\s+)?(?:the\s+)?",
        "",
        text,
    )
    # Strip trailing instruction / verb clauses like "should be identified"
    text = re.sub(
        r"\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be|will\s+be|are\s+to\s+be|ought\s+to\s+be)\s*(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located).*$",
        "",
        text,
    )
    text = re.sub(
        r"\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be)$",
        "",
        text,
    )
    text = re.sub(
        r"\s+(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located)$",
        "",
        text,
    )
    text = re.sub(r"\s+(?:in|from|within)\s+(?:the\s+)?(?:traffic\s+)?images?.*$", "", text)
    text = re.sub(r"\s+(?:objects?|targets?|instances?|items?|classes?|categories?)$", "", text)
    aliases = {
        "traffic signal": "traffic lights",
        "signal light": "traffic lights",
        "traffic light": "traffic lights",
        "traffic lights": "traffic lights",
        "traffic sign": "traffic signs",
        "traffic signs": "traffic signs",
        "road sign": "traffic signs",
        "roadside barrier": "road barriers",
        "road barrier": "road barriers",
        "barrier": "road barriers",
        "auto": "auto-rickshaws",
        "rickshaw": "auto-rickshaws",
        "auto rickshaw": "auto-rickshaws",
        "auto rickshaws": "auto-rickshaws",
        "auto-rickshaw": "auto-rickshaws",
        "auto-rickshaws": "auto-rickshaws",
        "autorickshaw": "auto-rickshaws",
        "three wheelers": "auto-rickshaws",
        "three-wheeler": "auto-rickshaws",
        "tuk tuk": "auto-rickshaws",
        "tuktuk": "auto-rickshaws",
        # Use the singular COCO/ground-truth ontology label consistently.
        # Project-facing aliases such as pedestrians are accepted as input,
        # but persisted detections should be labelled `person`.
        "pedestrian": "person",
        "pedestrians": "person",
        "people": "person",
        "person": "person",
        "car": "cars",
        "cars": "cars",
        "bus": "buses",
        "buses": "buses",
        "truck": "trucks",
        "trucks": "trucks",
        "motorcycle": "motorcycles",
        "motorcycles": "motorcycles",
        "bicycle": "bicycles",
        "bicycles": "bicycles",
    }
    return aliases.get(text.strip(), text.strip())


def canonicalize_dino_label(raw: str, prompt_labels: list[str]) -> str | None:
    """Map noisy Grounding DINO token spans back onto prompted ontology phrases.

    Returns None if the raw token does not map to any requested ontology label.
    """
    text_raw = (raw or "").strip().lstrip("#")
    prompt_lower = [_semantic_target(p) for p in prompt_labels if p and p.strip()]
    unusable_label = not text_raw or text_raw.casefold() in {
        ".", "[pad]", "[cls]", "[sep]", "unmapped", "unknown", "none", "null", "n/a"
    }
    if unusable_label:
        return prompt_lower[0] if len(prompt_lower) == 1 else None
    if not prompt_lower:
        return text_raw.lower()
    low = _semantic_target(text_raw)
    for phrase in prompt_lower:
        if low == phrase or phrase in low or low in phrase:
            return phrase
    tokens = {t for t in low.replace("_", " ").split() if t}
    best, best_overlap = None, 0
    for phrase in prompt_lower:
        p_tokens = {t for t in phrase.replace("_", " ").split() if t}
        overlap = len(tokens & p_tokens)
        if overlap > best_overlap:
            best, best_overlap = phrase, overlap
    if best is not None and best_overlap > 0:
        return best
    return None


def normalize_dino_text_label(value: Any) -> str:
    """Normalize text labels from transformers versions without losing phrases."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return " ".join(str(token).strip() for token in value if str(token).strip()).strip()
    return str(value).strip() if value is not None else ""



class GroundingDinoAdapter:
    key = ModelKey.DINO.value
    capabilities = [ModelCapability.OPEN_VOCAB_DETECTION]

    def __init__(
        self,
        *,
        model_id: str = "IDEA-Research/grounding-dino-tiny",
        device_preference: str = "auto",
        confidence_threshold: float = 0.18,
        box_threshold: float = 0.18,
        text_threshold: float = 0.18,
        nms_threshold: float = 0.75,
        cache_dir: Path | None = None,
    ) -> None:
        self.model_id = model_id
        self.confidence_threshold = confidence_threshold
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.nms_threshold = nms_threshold
        self.device = resolve_device(device_preference)
        self.cache_dir = cache_dir
        self._model: Any | None = None
        self._processor: Any | None = None
        self.load_duration_ms: int | None = None
        self._loaded: bool = False

    def load(self) -> None:
        if getattr(self, "_loaded", False):
            return
        start = time.perf_counter()
        logger.info(
            "model_load_start",
            model_key=self.key,
            model_id=self.model_id,
            device=self.device,
        )
        try:
            import torch
            from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        except ImportError as exc:
            raise ModelUnavailableError(
                "transformers is required for Grounding DINO",
                details={"hint": "uv pip install transformers timm"},
            ) from exc

        try:
            kwargs: dict[str, Any] = {}
            if self.cache_dir is not None:
                kwargs["cache_dir"] = str(self.cache_dir)
            try:
                self._processor = AutoProcessor.from_pretrained(
                    self.model_id, local_files_only=True, **kwargs
                )
                self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
                    self.model_id, local_files_only=True, **kwargs
                )
            except Exception:
                self._processor = AutoProcessor.from_pretrained(self.model_id, **kwargs)
                self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
                    self.model_id, **kwargs
                )
            self._model.to(self.device)
            self._model.eval()
            del torch
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(
                f"Failed to load Grounding DINO {self.model_id}: {exc}",
                details={
                    "model_id": self.model_id,
                    "device": self.device,
                    "next_step": "Ensure network access to Hugging Face or mount weights locally",
                },
            ) from exc

        self.load_duration_ms = int((time.perf_counter() - start) * 1000)
        self._loaded = True
        logger.info(
            "model_load_complete",
            model_key=self.key,
            model_id=self.model_id,
            device=str(self.device),
            duration_ms=self.load_duration_ms,
        )
        logger.info(
            "dino_model_loaded",
            model_key=self.key,
            model_id=self.model_id,
            device=str(self.device),
            duration_ms=self.load_duration_ms,
        )

    def predict(
        self,
        image_path: Path | str,
        *,
        asset_id: str,
        labels: list[str] | None = None,
        confidence_threshold: float | None = None,
        box_threshold: float | None = None,
        text_threshold: float | None = None,
        **kwargs: Any,
    ) -> list[NormalizedDetection]:
        image_path = Path(image_path)
        predict_start = time.perf_counter()
        if getattr(self, "_loaded", False):
            logger.info(
                "model_reuse",
                model_key=self.key,
                registry_id=getattr(self, "registry_id", "unknown"),
            )
        else:
            self.load()
        if self._model is None or self._processor is None:
            raise ModelUnavailableError(
                f"DINO model {self.model_id} is not loaded or is unavailable.",
                details={
                    "model_id": self.model_id,
                    "device": str(self.device),
                },
            )

        import torch

        raw_inputs = [l for l in (labels or []) if l and l.strip()]

        from app.inference.ontology_map import clean_canonical_label, is_invalid_workflow_label

        ontology_label_by_target: dict[str, str] = {}
        for raw in raw_inputs:
            if not raw or not raw.strip():
                continue
            if is_invalid_workflow_label(raw):
                continue
            cleaned = clean_canonical_label(raw.strip())
            if not cleaned or is_invalid_workflow_label(cleaned):
                continue
            target = _semantic_target(cleaned)
            if target and not is_invalid_workflow_label(target):
                ontology_label_by_target.setdefault(target, cleaned)

        prompt_labels = list(ontology_label_by_target) if ontology_label_by_target else (raw_inputs or ["object"])
        # Grounding DINO expects a period-separated lowercase phrase string
        text = " . ".join([p.lower() for p in prompt_labels]) + " ."

        logger.info(
            "dino_inference_start",
            model_key=self.key,
            prompt=text,
            asset_id=asset_id,
            image_name=image_path.name,
            requested_classes=list(ontology_label_by_target.values()) if ontology_label_by_target else prompt_labels,
        )

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        inputs = self._processor(images=image, text=text, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        pixel_values = inputs.get("pixel_values")
        model_input_height = int(pixel_values.shape[-2]) if pixel_values is not None else None
        model_input_width = int(pixel_values.shape[-1]) if pixel_values is not None else None
        logger.info(
            "dino_resolution_diagnostic",
            asset_id=asset_id,
            image_name=image_path.name,
            source_width=width,
            source_height=height,
            dino_input_width=model_input_width,
            dino_input_height=model_input_height,
            scale=(model_input_width / width) if model_input_width and width else None,
            padding_x=None,
            padding_y=None,
            tile_count=1,
        )

        with torch.no_grad():
            outputs = self._model(**inputs)

        effective_box_thresh = box_threshold if box_threshold is not None else (
            confidence_threshold if confidence_threshold is not None else self.box_threshold
        )
        effective_text_thresh = text_threshold if text_threshold is not None else self.text_threshold

        results = self._processor.post_process_grounded_object_detection(
            outputs,
            inputs["input_ids"],
            threshold=effective_box_thresh,
            text_threshold=effective_text_thresh,
            target_sizes=[(height, width)],
        )[0]

        now = datetime.now(UTC)
        detections: list[NormalizedDetection] = []
        boxes = results.get("boxes")
        scores = results.get("scores")
        text_labels = results.get("text_labels") or results.get("labels") or []
        if boxes is None:
            duration_ms = int((time.perf_counter() - predict_start) * 1000)
            logger.info(
                "dino_inference_complete",
                model_key=self.key,
                prompt=text,
                detection_count=0,
                duration_ms=duration_ms,
            )
            logger.info(
                "dino_detection_count",
                model_key=self.key,
                prompt=text,
                detection_count=0,
            )
            return detections

        raw_box_count = len(boxes) if boxes is not None else 0
        thresholded_count = 0
        mapped_count = 0
        unmapped_count = 0
        persisted_count = 0
        logger.info(
            "dino_diagnostic_raw",
            DINO_RAW_COUNT=raw_box_count,
            prompt=text,
            box_threshold=effective_box_thresh,
            text_threshold=effective_text_thresh,
        )

        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = [float(v) for v in box.tolist()]
            score = float(scores[i]) if scores is not None else 0.0
            if score < effective_box_thresh:
                continue
            thresholded_count += 1
            raw_label = normalize_dino_text_label(
                text_labels[i] if i < len(text_labels) else prompt_labels[0]
            )
            label = canonicalize_dino_label(raw_label, prompt_labels)
            normalized_raw_label = _semantic_target(raw_label)
            requested_label = ontology_label_by_target.get(
                label or (prompt_labels[0] if prompt_labels else ""),
                raw_inputs[0] if raw_inputs else "",
            )
            if label is None:
                unmapped_count += 1
                logger.warning(
                    "dino_unmapped_detection",
                    asset_id=asset_id,
                    image_name=image_path.name,
                    raw_label=raw_label,
                    normalized_raw_label=normalized_raw_label,
                    requested_label=requested_label,
                    canonical_label=None,
                    mapping_status="UNMAPPED_DETECTION",
                    mapping_reason="raw label did not match a requested canonical DINO target",
                    confidence=score,
                    bounding_box=[x1, y1, x2, y2],
                    reason_for_unmapped="raw label did not match a requested canonical DINO target",
                )
                # Preserve valid model evidence for the existing quality/HITL
                # path. It is deliberately not an ontology label and merge
                # will not persist it as an annotation.
                bbox = clamp_box(
                    (x1 / width) * 100.0,
                    (y1 / height) * 100.0,
                    ((x2 - x1) / width) * 100.0,
                    ((y2 - y1) / height) * 100.0,
                )
                if bbox.w >= 0.05 and bbox.h >= 0.05:
                    detections.append(
                        NormalizedDetection(
                            id=str(uuid4()),
                            asset_id=asset_id,
                            label=raw_label or "Unmapped",
                            class_id=None,
                            bbox=bbox,
                            confidence=score,
                            model_id=self.model_id,
                            model_key=self.key,
                            inferred_at=now,
                            provenance={
                                "engine": "transformers-grounding-dino",
                                "prompt": text,
                                "raw_label": raw_label,
                                "normalized_raw_label": normalized_raw_label,
                                "requested_label": requested_label,
                                "canonical_label": None,
                                "mapping_status": "UNMAPPED_DETECTION",
                                "mapping_reason": "raw label did not match a requested canonical DINO target",
                                "uncertainty": "UNCERTAIN",
                                "confidence": score,
                                "image_width": width,
                                "image_height": height,
                                "raw_xyxy": [x1, y1, x2, y2],
                            },
                        )
                    )
                continue
            mapped_count += 1
            persisted_label = ontology_label_by_target.get(label, label)
            logger.info(
                "dino_detection_mapping",
                asset_id=asset_id,
                raw_label=raw_label,
                normalized_raw_label=normalized_raw_label,
                requested_label=requested_label,
                canonical_label=persisted_label,
                mapping_status="MAPPED",
                mapping_reason="semantic alias matched requested DINO target",
            )
            bbox = clamp_box(
                (x1 / width) * 100.0,
                (y1 / height) * 100.0,
                ((x2 - x1) / width) * 100.0,
                ((y2 - y1) / height) * 100.0,
            )
            if bbox.w < 0.05 or bbox.h < 0.05:
                continue
            persisted_count += 1
            detections.append(
                NormalizedDetection(
                    id=str(uuid4()),
                    asset_id=asset_id,
                    label=persisted_label,
                    class_id=None,
                    bbox=bbox,
                    confidence=score,
                    model_id=self.model_id,
                    model_key=self.key,
                    inferred_at=now,
                    provenance={
                        "engine": "transformers-grounding-dino",
                        "prompt": text,
                        "raw_label": raw_label,
                        "normalized_raw_label": normalized_raw_label,
                        "requested_label": requested_label,
                        "normalized_label": label,
                        "canonical_label": persisted_label,
                        "mapping_status": "MAPPED",
                        "mapping_reason": "semantic alias matched requested DINO target",
                        "ontology_match": persisted_label,
                        "confidence": score,
                        "canonical_target": label,
                        "ontology_label": persisted_label,
                        "image_width": width,
                        "image_height": height,
                        "raw_xyxy": [x1, y1, x2, y2],
                    },
                )
            )

        duration_ms = int((time.perf_counter() - predict_start) * 1000)
        logger.info(
            "dino_diagnostic_after_threshold",
            DINO_AFTER_THRESHOLD_COUNT=thresholded_count,
            raw_count=raw_box_count,
            thresholded_count=thresholded_count,
            mapped_count=mapped_count,
            unmapped_count=unmapped_count,
            persisted_count=persisted_count,
            prompt=text,
        )
        logger.info(
            "dino_inference_complete",
            model_key=self.key,
            prompt=text,
            detection_count=len(detections),
            duration_ms=duration_ms,
        )
        logger.info(
            "dino_detection_count",
            model_key=self.key,
            prompt=text,
            detection_count=len(detections),
        )
        return detections
