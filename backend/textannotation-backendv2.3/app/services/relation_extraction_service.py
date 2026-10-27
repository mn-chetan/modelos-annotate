from __future__ import annotations

import re

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.prompts.relation_extraction_prompt import build_relation_extraction_prompt
from app.schemas.analysis import (
    GeminiRelationExtractionResponse,
    RelationExtractionAnalysisResult,
    RelationExtractionRelation,
)
from app.schemas.source import SourceDocument
from app.services.gemini_service import GeminiService


class RelationExtractionService:
    def __init__(self, gemini_service: GeminiService):
        self.settings = get_settings()
        self.gemini_service = gemini_service

    def _split_by_boundaries(self, text: str) -> list[str]:
        normalized = re.sub(r"[\u200b\ufeff]", "", text).strip()
        if not normalized:
            return []

        if len(normalized) <= self.settings.chunk_max_chars:
            sentence_boundaries = list(re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9\"'‘“(])", normalized))
            if sentence_boundaries:
                parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'‘“(])", normalized) if part.strip()]
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

    def _build_chunks(self, source: SourceDocument) -> list[str]:
        if source.pages:
            chunks: list[str] = []
            for page in source.pages:
                page_chunks = self._split_by_boundaries(page.text) or [page.text]
                chunks.extend(page_chunks)
            return [chunk for chunk in chunks if chunk.strip()]

        text = source.extracted_text or source.text or ""
        return self._split_by_boundaries(text) or ([text.strip()] if text.strip() else [])

    async def analyze(self, source: SourceDocument) -> RelationExtractionAnalysisResult:
        chunks = self._build_chunks(source)
        if not chunks:
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        relations: dict[tuple[str, str, str], RelationExtractionRelation] = {}
        for chunk in chunks:
            prompt = build_relation_extraction_prompt(chunk)
            response = await self.gemini_service.generate_structured(prompt, GeminiRelationExtractionResponse)
            for item in response.relations:
                relation = RelationExtractionRelation(
                    source=item.source,
                    relation=item.relation,
                    target=item.target,
                    confidence=item.confidence,
                    reason=item.reasoning,
                )
                key = (relation.source.lower(), relation.relation.lower(), relation.target.lower())
                existing = relations.get(key)
                if existing is None or relation.confidence > existing.confidence:
                    relations[key] = relation

        extracted_relations = list(relations.values())
        if extracted_relations:
            confidence = round(sum(item.confidence for item in extracted_relations) / len(extracted_relations), 2)
            reason = f"Extracted {len(extracted_relations)} relation(s) from the provided text."
        else:
            confidence = 0.5
            reason = "No explicit relations were identified in the provided text."

        return RelationExtractionAnalysisResult(
            confidence=confidence,
            reason=reason,
            relations=extracted_relations,
        )