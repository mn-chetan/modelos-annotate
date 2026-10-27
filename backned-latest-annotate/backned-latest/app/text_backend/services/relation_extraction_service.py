from __future__ import annotations

import asyncio
import math
import re

from app.text_backend.core.config import get_settings
from app.text_backend.core.exceptions import AppError
from app.text_backend.prompts.relation_extraction_prompt import build_relation_extraction_prompt
from app.text_backend.schemas.analysis import (
    GeminiRelationExtractionResponse,
    RelationExtractionAnalysisResult,
    RelationExtractionRelation,
)
from app.text_backend.schemas.source import SourceDocument
from app.text_backend.services.gemini_service import GeminiService


class RelationExtractionService:
    def __init__(self, gemini_service: GeminiService):
        self.settings = get_settings()
        self.gemini_service = gemini_service

    def _split_by_boundaries(self, text: str) -> list[str]:
        normalized = re.sub(r"[\u200b\ufeff]", "", text).strip()
        if not normalized:
            return []

        if len(normalized) <= self.settings.chunk_max_chars:
            sentence_boundaries = list(re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9\"'â€˜â€œ(])", normalized))
            if sentence_boundaries:
                parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'â€˜â€œ(])", normalized) if part.strip()]
                if len(parts) > 1:
                    return parts

        paragraphs = [part.strip() for part in re.split(r"(?:\r?\n){2,}|(?:\r?\n)+", text) if part.strip()]
        if not paragraphs:
            return []

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self.settings.chunk_max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", paragraph) if part.strip()]
                for sentence in sentences:
                    if len(sentence) > self.settings.chunk_max_chars:
                        words = sentence.split()
                        buffer = ""
                        for word in words:
                            tentative = f"{buffer} {word}".strip()
                            if len(tentative) > self.settings.chunk_max_chars and buffer:
                                chunks.append(buffer.strip())
                                buffer = word
                            else:
                                buffer = tentative
                        if buffer:
                            chunks.append(buffer.strip())
                    else:
                        if len((current + " " + sentence).strip()) > self.settings.chunk_max_chars and current:
                            chunks.append(current.strip())
                            current = sentence
                        else:
                            current = f"{current} {sentence}".strip()
                continue

            tentative = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(tentative) > self.settings.chunk_max_chars and current:
                chunks.append(current.strip())
                current = paragraph
            else:
                current = tentative

        if current:
            chunks.append(current.strip())
        return [chunk for chunk in chunks if chunk]

    def _build_chunks(self, source: SourceDocument) -> list[dict[str, object]]:
        if source.pages:
            chunks: list[dict[str, object]] = []
            for page in source.pages:
                page_chunks = self._split_by_boundaries(page.text) or [page.text]
                chunks.extend({"text": chunk, "page": page.page} for chunk in page_chunks if chunk.strip())
            return chunks

        text = source.extracted_text or source.text or "\n".join(page.text for page in source.pages if page.text.strip())
        chunks = self._split_by_boundaries(text) or ([text.strip()] if text.strip() else [])
        return [{"text": chunk, "page": None} for chunk in chunks if chunk.strip()]

    async def analyze(
        self,
        source: SourceDocument,
        relation_ontology: list[str] | None = None,
        detected_entities: list[dict[str, str]] | None = None,
    ) -> RelationExtractionAnalysisResult:
        chunks = self._build_chunks(source)
        if not chunks:
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        # Relation extraction is document-level by contract. Bound the number
        # of Gemini requests for long PDFs instead of sending one request per
        # sentence/list item.
        if len(chunks) > 12:
            group_size = math.ceil(len(chunks) / 12)
            chunks = [
                {"text": "\n\n".join(str(item["text"]) for item in chunks[start:start + group_size]), "page": None}
                for start in range(0, len(chunks), group_size)
            ]

        text = source.extracted_text or source.text or "\n".join(page.text for page in source.pages if page.text.strip())
        text_casefold = text.casefold()
        allowed = {str(item).strip().upper() for item in (relation_ontology or []) if str(item).strip()}
        entity_by_text = {
            str(item.get("text", "")).strip().casefold(): item
            for item in (detected_entities or [])
            if str(item.get("text", "")).strip()
        }
        rejected_reasons: list[str] = []
        relations: dict[tuple[str, str, str], RelationExtractionRelation] = {}
        async def analyze_chunk(chunk_record: dict[str, object]) -> tuple[object, object, object]:
            chunk = str(chunk_record["text"])
            page = chunk_record.get("page")
            prompt = build_relation_extraction_prompt(chunk, relation_ontology, detected_entities)
            response = await self.gemini_service.generate_structured(prompt, GeminiRelationExtractionResponse)
            return chunk_record, chunk, response

        semaphore = asyncio.Semaphore(4)

        async def bounded_analyze(chunk_record: dict[str, object]) -> tuple[object, object, object]:
            async with semaphore:
                return await analyze_chunk(chunk_record)

        chunk_results = await asyncio.gather(*(bounded_analyze(item) for item in chunks))
        for chunk_record, chunk, response in chunk_results:
            page = chunk_record.get("page")
            for item in response.relations:
                relation_name = re.sub(r"\s+", "_", item.relation.strip()).upper()
                source_name = item.source.strip()
                target_name = item.target.strip()
                if not source_name or not target_name:
                    rejected_reasons.append("relation missing subject or object")
                    continue
                source_entity = entity_by_text.get(source_name.casefold(), {})
                target_entity = entity_by_text.get(target_name.casefold(), {})
                if source_name.casefold() not in text_casefold or target_name.casefold() not in text_casefold:
                    rejected_reasons.append(f"relation evidence not found for {source_name} -> {target_name}")
                    continue
                if relation_name in {"OTHER", "UNKNOWN", "UNSPECIFIED"}:
                    rejected_reasons.append(f"unresolved relation rejected: {source_name} -> {target_name}")
                    continue
                if allowed and relation_name not in allowed:
                    rejected_reasons.append(f"unsupported relation label: {relation_name}")
                    continue
                evidence = (item.evidence or "").strip()
                if not evidence:
                    rejected_reasons.append(f"relation evidence missing: {source_name} -> {target_name}")
                    continue
                evidence_casefold = evidence.casefold()
                if source_name.casefold() not in evidence_casefold or target_name.casefold() not in evidence_casefold:
                    rejected_reasons.append(f"relation evidence does not contain both endpoints: {source_name} -> {target_name}")
                    continue
                if evidence_casefold not in text_casefold:
                    rejected_reasons.append(f"relation evidence is not copied from source text: {source_name} -> {target_name}")
                    continue
                source_type = item.source_type or source_entity.get("type")
                target_type = item.target_type or target_entity.get("type")
                relation = RelationExtractionRelation(
                    source=source_name,
                    relation=relation_name,
                    confidence=item.confidence,
                    reason=item.reasoning,
                    target=target_name,
                    source_type=str(source_type).strip().upper().replace(" ", "_") if source_type else None,
                    target_type=str(target_type).strip().upper().replace(" ", "_") if target_type else None,
                    evidence=evidence,
                    evidence_items=[evidence],
                    page=item.page if item.page is not None else (int(page) if page is not None else None),
                )
                key = (relation.source.lower(), relation.relation.lower(), relation.target.lower())
                existing = relations.get(key)
                if existing is None:
                    relations[key] = relation
                else:
                    evidence_items = list(dict.fromkeys([*(existing.evidence_items or [existing.evidence or ""]), *(relation.evidence_items or [relation.evidence or ""])]))
                    relation_score = relation.confidence if relation.confidence is not None else -1.0
                    existing_score = existing.confidence if existing.confidence is not None else -1.0
                    if relation_score > existing_score:
                        relation.evidence_items = evidence_items
                        relations[key] = relation
                    else:
                        existing.evidence_items = evidence_items

        extracted_relations = list(relations.values())
        available_confidences = [item.confidence for item in extracted_relations if item.confidence is not None]
        if extracted_relations:
            confidence = round(sum(available_confidences) / len(available_confidences), 2) if available_confidences else None
            reason = f"Extracted {len(extracted_relations)} relation(s) from the provided text."
        else:
            confidence = None
            reason = "No verified relations were identified in the provided text."
        if rejected_reasons:
            reason = f"{reason} Rejected {len(rejected_reasons)} unsupported or unevidenced candidate relation(s)."

        return RelationExtractionAnalysisResult(
            confidence=confidence,
            reason=reason,
            relations=extracted_relations,
        )
