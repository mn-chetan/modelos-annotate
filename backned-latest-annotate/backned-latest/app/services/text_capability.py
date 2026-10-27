"""Adapter from the existing text backend services to the common graph contract."""
from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path
from typing import Any

from app.text_backend.schemas.source import SourceDocument
from app.text_backend.schemas.entity import SemanticVerificationResponse
from app.text_backend.services.drug_matching_service import DrugMatchingService
from app.text_backend.services.entity_extraction_service import GenericEntityExtractionService
from app.text_backend.services.gemini_service import GeminiService
from app.text_backend.services.ocr_service import TesseractOCRService
from app.text_backend.services.relation_extraction_service import RelationExtractionService
from app.text_backend.services.sentiment_service import SentimentService
from app.text_backend.services.text_classification_service import TextClassificationService
from app.text_backend.services.text_extraction_service import TextExtractionService
from app.agent.capability_registry import ModelCapabilityRegistry


NER_DEFAULT_LABELS = [
    "Person",
    "Organization",
    "Location",
    "Date",
    "Product",
    "Event",
    "Money",
    "Order ID",
    "Customer Support",
    "Complaint",
]


def normalize_text_labels(raw_value: Any) -> list[str]:
    """Normalize saved text target objects without introducing image labels."""
    canonical_ner_labels = {label.casefold(): label for label in NER_DEFAULT_LABELS}

    def canonicalize(value: str) -> str:
        cleaned = value.strip()
        return canonical_ner_labels.get(cleaned.casefold(), cleaned)

    if isinstance(raw_value, str):
        return [canonicalize(part) for part in raw_value.replace("\n", ",").split(",") if part.strip()]
    if not isinstance(raw_value, (list, tuple)):
        return []
    labels: list[str] = []
    for item in raw_value:
        if isinstance(item, str) and item.strip():
            labels.append(canonicalize(item))
        elif isinstance(item, dict):
            value = item.get("name") or item.get("label") or item.get("value")
            if isinstance(value, str) and value.strip():
                labels.append(canonicalize(value))
    return labels


def resolve_text_target_labels(source: Any, task_type: str | None = None) -> list[str]:
    """Return text labels without inheriting the project's image ontology."""
    def read(name: str) -> Any:
        if isinstance(source, dict):
            return source.get(name)
        return getattr(source, name, None)

    normalized_task = str(task_type or read("task_type") or read("analysis_type") or "").strip().lower()
    if normalized_task in {"relation_extraction", "relation extraction", "relation"}:
        relation_fields = ("relation_types", "relation_ontology", "label_ontology", "labels")
        for field in relation_fields:
            labels = normalize_text_labels(read(field))
            if labels:
                return labels

    if normalized_task in {"ner", "entity_extraction", "entity extraction", "named_entity_recognition", "named entity recognition"}:
        # Merge explicit text targets with the canonical project ontology. A
        # project may store its labels in `label_ontology`/`labels` while the
        # legacy target-object field contains only a subset.
        labels: list[str] = []
        for field in (
            "target_objects",
            "text_labels",
            "targetObjectsText",
            "entities",
            "label_ontology",
            "labels",
        ):
            labels.extend(normalize_text_labels(read(field)))
        labels = list(dict.fromkeys(labels))
        return labels or list(NER_DEFAULT_LABELS)

    for field in ("target_objects", "text_labels", "targetObjectsText", "entities"):
        labels = normalize_text_labels(read(field))
        if labels:
            return labels
    return []


def resolve_text_entity_labels(source: Any) -> list[str]:
    """Read entity categories from project configuration for relation candidates."""
    def read(name: str) -> Any:
        if isinstance(source, dict):
            return source.get(name)
        return getattr(source, name, None)

    for field in ("entity_types", "entity_labels", "target_objects", "text_labels", "entities"):
        labels = normalize_text_labels(read(field))
        if labels:
            return labels

    ontology = read("label_ontology")
    if isinstance(ontology, (list, tuple)):
        labels: list[str] = []
        for item in ontology:
            if isinstance(item, dict):
                values = item.get("entity_types") or item.get("entity_labels")
                labels.extend(normalize_text_labels(values))
        return list(dict.fromkeys(labels))
    return []


async def verify_text_annotations(
    *,
    text: str,
    annotations: list[dict[str, Any]],
    ontology: list[str],
    capability: str,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Perform capability-aware semantic verification with contextual evidence."""
    if not annotations:
        return {"verifications": [], "available": True}

    from app.text_backend.services.gemini_service import GeminiService

    records = []
    for index, annotation in enumerate(annotations):
        span = annotation.get("text_span") or annotation.get("geometry") or {}
        relation_geometry = annotation.get("geometry") or {}
        start = max(0, int(span.get("start", 0) or 0))
        end = min(len(text), int(span.get("end", start) or start))
        window_start = max(0, start - 240)
        window_end = min(len(text), end + 240)
        record = {
            "annotation_id": str(annotation.get("id") or f"annotation-{index}"),
            "entity_text": text[start:end] or span.get("text", ""),
            "predicted_label": annotation.get("label", ""),
            "model_confidence": annotation.get("confidence"),
            "local_context": text[window_start:window_end],
            "span": {"start": start, "end": end},
            "provenance": annotation.get("provenance", {}),
        }
        if capability == "text_relation_extraction" or annotation.get("geometry_type") == "text_relation":
            record["subject"] = relation_geometry.get("source", "")
            record["relation"] = relation_geometry.get("relation", annotation.get("label", ""))
            record["object"] = relation_geometry.get("target", "")
            record["subject_type"] = relation_geometry.get("source_type")
            record["object_type"] = relation_geometry.get("target_type")
            record["evidence"] = relation_geometry.get("evidence")
        records.append(record)
    prompt = (
        "You are a semantic verification agent for an annotation pipeline. "
        "Verify each annotation using its exact text, local context, full document, "
        "configured ontology, task capability, provenance, and model confidence. "
        "Confidence alone is never proof. Do not use regex or memorized entity mappings. "
        "Return JSON only and use exactly this response contract: "
        "{\"verifications\":[{\"annotation_id\":\"string\","
        "\"semantic_validity\":true,\"ontology_validity\":true,"
        "\"contextual_validity\":true,\"conflict_detected\":false,"
        "\"alternative_label\":null,\"reason\":\"string\","
        "\"verification_confidence\":0.0,\"decision\":\"VALID\"}]}. "
        "Every verification object MUST include semantic_validity, ontology_validity, "
        "and contextual_validity as boolean values; do not omit or rename any of them. "
        "decision must be VALID, INVALID, or UNCERTAIN. An INVALID or UNCERTAIN result "
        "must not be auto-approved. "
        "For relation extraction records, validate that subject and object occur in the document and that the relation is explicitly supported; never approve a relation merely because its model confidence is high. "
        "For entity extraction, use the configured ontology exactly. Resolve labels from the entity text and its surrounding context, not from confidence alone. When the ontology contains a specific identifier label, a structured identifier must use that label when nearby cue words identify its meaning (for example, an order reference following 'order' should not be treated as a generic product). Prefer the most specific supported label over a broad label, and return an alternative_label when the predicted label is semantically wrong. Do not invent labels outside the ontology. "
        "For text_classification or text_sentiment_analysis tasks, predicted labels represent document-level categories, topics, or sentiments. Validate whether the predicted label is an accurate summary/category for the document content. If the configured ontology consists of entity-level types (such as Person, Organization, Location), mark valid document-level classification or sentiment labels as ontology_valid: true. "
        f"CAPABILITY: {capability}\nMODEL: {model_id or ''}\n"
        f"ONTOLOGY: {ontology}\nDOCUMENT:\n{text}\nANNOTATIONS:\n{records}"
    )
    try:
        result = await GeminiService().generate_structured(prompt, SemanticVerificationResponse)
        return {"verifications": [item.model_dump() for item in result.verifications], "available": True}
    except Exception as exc:
        return {"verifications": [], "available": False, "error": str(exc)}


class _AssetUpload:
    def __init__(self, path: Path, content: bytes):
        self.filename = path.name
        self.content_type = None
        self._content = content

    async def read(self) -> bytes:
        return self._content

    async def close(self) -> None:
        return None


def normalize_text_task(raw_task: str | None) -> tuple[str, str]:
    """Resolve a task through the central capability registry."""
    return ModelCapabilityRegistry().resolve_text_task(raw_task)


class TextCapabilityService:
    CAPABILITIES = {
        "ENTITY_EXTRACTION": "text_entity_extraction",
        "DRUG_MATCHING": "text_drug_matching",
        "SENTIMENT_ANALYSIS": "text_sentiment_analysis",
        "TEXT_CLASSIFICATION": "text_classification",
        "RELATION_EXTRACTION": "text_relation_extraction",
    }

    def __init__(self) -> None:
        gemini = GeminiService()
        self.extraction = TextExtractionService(TesseractOCRService())
        self.entity_extraction = GenericEntityExtractionService(gemini)
        self.drug_matching = DrugMatchingService(gemini)
        self.sentiment = SentimentService(gemini)
        self.classification = TextClassificationService(gemini)
        self.relations = RelationExtractionService(gemini)

    @staticmethod
    def _relation_annotation(asset_id: str, index: int, relation: Any, text: str, model_id: str) -> dict[str, Any]:
        evidence = relation.evidence or ""
        start = text.casefold().find(evidence.casefold()) if evidence else -1
        end = start + len(evidence) if start >= 0 else start
        geometry = {
            "source": relation.source, "target": relation.target, "relation": relation.relation,
            "source_type": relation.source_type, "target_type": relation.target_type,
            "evidence": evidence, "evidence_items": relation.evidence_items,
            "start": max(start, 0), "end": max(end, 0), "text": evidence,
            "review_status": relation.review_status,
        }
        if relation.page is not None:
            geometry["page"] = relation.page
        return {
            "id": f"{asset_id}:relation:{index}", "asset_id": asset_id,
            "label": relation.relation, "geometry_type": "text_relation", "geometry": geometry,
            "text_span": {"start": max(start, 0), "end": max(end, 0), "text": evidence},
            "confidence": relation.confidence, "model_id": model_id, "source": "ai",
            "review_status": relation.review_status,
            "provenance": {"capability": "text_relation_extraction", "raw_result": relation.model_dump()},
        }

    async def _source(self, path: Path) -> SourceDocument:
        content = path.read_bytes()
        return await self.extraction.extract_from_upload(_AssetUpload(path, content))

    @staticmethod
    def _span_annotations(source: SourceDocument, entities: list[Any], asset_id: str, model_id: str, allowed_labels: list[str] | None = None) -> list[dict[str, Any]]:
        text = source.extracted_text or source.text or ""
        canonical_labels = normalize_text_labels(allowed_labels or [])
        canonical_by_lower = {label.lower(): label for label in canonical_labels}
        result: list[dict[str, Any]] = []
        for entity in entities:
            read = entity.get if isinstance(entity, dict) else lambda key, default=None: getattr(entity, key, default)
            found = bool(read("found", False))
            value = read("matched_text") or read("entity_name", "")
            if not found or not value:
                continue
            match = re.search(re.escape(str(value)), text, flags=re.IGNORECASE)
            if not match:
                continue
            label_candidates = [read("tag"), read("entity_type"), read("category"), read("entity_name")]
            label = next(
                (canonical_by_lower[str(candidate).strip().lower()] for candidate in label_candidates if str(candidate or "").strip().lower() in canonical_by_lower),
                canonical_labels[0] if canonical_labels else "Entity",
            )
            result.append({
                "id": f"{asset_id}:span:{match.start()}:{match.end()}",
                "asset_id": asset_id,
                "label": label,
                "geometry_type": "text_span",
                "geometry": {"start": match.start(), "end": match.end(), "text": match.group(0)},
                "text_span": {"start": match.start(), "end": match.end(), "text": match.group(0)},
                "confidence": read("confidence_score") or 0.9,
                "model_id": model_id,
                "source": "ai",
                "provenance": {"capability": "text_entity_extraction", "model_id": model_id, "verified_candidate": True},
            })
        return result

    async def execute(
        self,
        *,
        path: Path,
        task_type: str,
        labels: list[str],
        asset_id: str,
        model_id: str,
        entity_labels: list[str] | None = None,
        analysis_level: str = "document",
    ) -> dict[str, Any]:
        source = await self._source(path)
        norm_task, canonical_cap = normalize_text_task(task_type)
        # The planner's selected capability is the service contract.  Keep the
        # canonical task as a fallback for direct legacy callers, but never
        # route an entity-extraction capability through drug matching.
        capability = model_id or canonical_cap
        if capability == "text_entity_extraction" or norm_task in {"ENTITY_EXTRACTION", "NER"}:
            text = source.extracted_text or source.text or ""
            result = await self.entity_extraction.analyze(source, labels)
            entities = list(result.entities)
            return {"annotations": self._span_annotations(source, entities, asset_id, model_id, labels), "text": text, "raw_result": result.model_dump(), "errors": []}
        if capability in {"drug_matching", "text_drug_matching"} or norm_task == "DRUG_MATCHING":
            text = source.extracted_text or source.text or ""
            result = await self.drug_matching.analyze(source, ",".join(labels))
            entities = list(result.entities)
            return {"annotations": self._span_annotations(source, entities, asset_id, model_id, labels), "text": text, "raw_result": result.model_dump(), "errors": []}
        if capability == "text_sentiment_analysis" or norm_task == "SENTIMENT_ANALYSIS":
            result = await self.sentiment.analyze(source, analysis_level=analysis_level)
            full_text = source.extracted_text or source.text or ""
            if result.analysis_level == "document":
                annotation = {
                    "id": f"{asset_id}:document",
                    "asset_id": asset_id,
                    "label": result.sentiment,
                    "geometry_type": "text_classification",
                    "geometry": {"start": 0, "end": len(full_text), "text": full_text, "level": "document"},
                    "text_span": {"start": 0, "end": len(full_text), "text": full_text},
                    "confidence": result.confidence,
                    "model_id": model_id,
                    "source": "ai",
                    "provenance": {"capability": model_id, "analysis_level": "document", "reason": result.reason},
                }
                return {"annotations": [annotation], "text": full_text, "raw_result": result.model_dump(), "overall_sentiment": result.sentiment, "errors": []}
            annotations = []
            for item in result.chunk_results:
                start = item.start if item.start is not None else 0
                end = item.end if item.end is not None else len(full_text)
                annotations.append({
                    "id": f"{asset_id}:sentiment:{item.chunk_index}",
                    "asset_id": asset_id,
                    "label": item.sentiment,
                    "geometry_type": "text_classification",
                    "geometry": {"start": start, "end": end, "text": item.chunk_text, "page": item.page, "level": item.level, "paragraph_index": item.paragraph_index, "sentence_index": item.sentence_index},
                    "text_span": {"start": start, "end": end, "text": item.chunk_text, "page": item.page},
                    "confidence": item.confidence,
                    "model_id": model_id,
                    "source": "ai",
                    "provenance": {"capability": model_id, "analysis_level": item.level, "reason": item.reason},
                })
            return {"annotations": annotations, "text": full_text, "raw_result": result.model_dump(), "overall_sentiment": result.sentiment, "errors": []}
        if capability == "text_classification" or norm_task == "TEXT_CLASSIFICATION":
            result = await self.classification.analyze(source, analysis_level=analysis_level, categories=labels)
            full_text = source.extracted_text or source.text or ""
            if result.analysis_level == "document":
                annotation = {
                    "id": f"{asset_id}:document",
                    "asset_id": asset_id,
                    "label": result.label,
                    "geometry_type": "text_classification",
                    "geometry": {"start": 0, "end": len(full_text), "text": full_text, "level": "document"},
                    "text_span": {"start": 0, "end": len(full_text), "text": full_text},
                    "confidence": result.confidence,
                    "model_id": model_id,
                    "source": "ai",
                    "provenance": {"capability": model_id, "analysis_level": "document", "reason": result.reason},
                }
                return {"annotations": [annotation], "text": full_text, "raw_result": result.model_dump(), "overall_label": result.label, "errors": []}
            annotations = []
            for item in result.chunk_results:
                start = item.start if item.start is not None else 0
                end = item.end if item.end is not None else len(full_text)
                annotations.append({
                    "id": f"{asset_id}:classification:{item.chunk_index}",
                    "asset_id": asset_id,
                    "label": item.label,
                    "geometry_type": "text_classification",
                    "geometry": {"start": start, "end": end, "text": item.chunk_text, "page": item.page, "level": item.level, "paragraph_index": item.paragraph_index, "sentence_index": item.sentence_index},
                    "text_span": {"start": start, "end": end, "text": item.chunk_text, "page": item.page},
                    "confidence": item.confidence,
                    "model_id": model_id,
                    "source": "ai",
                    "provenance": {"capability": model_id, "analysis_level": item.level, "reason": item.reason},
                })
            return {"annotations": annotations, "text": full_text, "raw_result": result.model_dump(), "overall_label": result.label, "errors": []}
        if capability == "text_relation_extraction" or norm_task == "RELATION_EXTRACTION":
            # Relation extraction discovers and types its own endpoints. The
            # generic NER service has a separate contract and must not be used
            # as a semantic gate because a broad NER span can become a false
            # relation endpoint.
            full_text = source.extracted_text or source.text or "\n".join(page.text for page in source.pages if page.text.strip())
            result = await self.relations.analyze(source, labels, None)
            annotations = [self._relation_annotation(asset_id, i, relation, full_text, model_id) for i, relation in enumerate(result.relations)]
            return {"annotations": annotations, "text": full_text, "raw_result": result.model_dump(), "errors": []}
        if capability in {"all_text_features", "all_features"} or norm_task in {"ALL_TEXT_FEATURES", "ALL", "ALL_FEATURES"}:
            text = source.extracted_text or source.text or ""
            ner_labels = normalize_text_labels(entity_labels or labels) or list(NER_DEFAULT_LABELS)
            rel_labels = labels or list(NER_DEFAULT_LABELS)
            
            # These models are independent. Run relation extraction in the
            # same batch as NER/sentiment/classification so ALL_TEXT_FEATURES
            # does not add another full model round-trip in deployment.
            ner_res_task = self.entity_extraction.analyze(source, ner_labels)
            sent_res_task = self.sentiment.analyze(source)
            cls_res_task = self.classification.analyze(source)
            rel_res_task = self.relations.analyze(source, rel_labels, None)

            ner_res, sent_res, cls_res, rel_res = await asyncio.gather(
                ner_res_task,
                sent_res_task,
                cls_res_task,
                rel_res_task,
                return_exceptions=True,
            )
            
            combined_annotations: list[dict[str, Any]] = []
            detected_entities: list[dict[str, Any]] = []
            
            if not isinstance(ner_res, Exception) and ner_res:
                combined_annotations.extend(self._span_annotations(source, list(ner_res.entities), asset_id, model_id, ner_labels))
                detected_entities = [{"text": e.matched_text or "", "type": e.tag} for e in ner_res.entities if e.matched_text]
            
            if not isinstance(sent_res, Exception) and sent_res:
                combined_annotations.append({
                    "id": f"{asset_id}:sentiment",
                    "asset_id": asset_id,
                    "label": sent_res.sentiment,
                    "geometry_type": "text_classification",
                    "geometry": {"start": 0, "end": len(text), "text": text},
                    "text_span": {"start": 0, "end": len(text), "text": text},
                    "confidence": sent_res.confidence,
                    "model_id": model_id,
                    "source": "ai",
                    "provenance": {"capability": "text_sentiment_analysis", "raw_result": sent_res.model_dump()},
                })
                
            if not isinstance(cls_res, Exception) and cls_res:
                combined_annotations.append({
                    "id": f"{asset_id}:classification",
                    "asset_id": asset_id,
                    "label": cls_res.label,
                    "geometry_type": "text_classification",
                    "geometry": {"start": 0, "end": len(text), "text": text},
                    "text_span": {"start": 0, "end": len(text), "text": text},
                    "confidence": cls_res.confidence,
                    "model_id": model_id,
                    "source": "ai",
                    "provenance": {"capability": "text_classification", "raw_result": cls_res.model_dump()},
                })
                
            if not isinstance(rel_res, Exception) and rel_res and rel_res.relations:
                rel_anns = [
                    self._relation_annotation(asset_id, i, r, text, model_id)
                    for i, r in enumerate(rel_res.relations)
                ]
                combined_annotations.extend(rel_anns)
                
            return {"annotations": combined_annotations, "text": text, "raw_result": {"analysis_type": "ALL_TEXT_FEATURES"}, "errors": []}
        return {"annotations": [], "text": source.extracted_text or "", "errors": [{"code": "UNSUPPORTED_TEXT_TASK", "message": task_type}]}
