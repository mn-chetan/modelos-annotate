from __future__ import annotations

import re

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.prompts.text_classification_prompt import build_text_classification_prompt
from app.schemas.analysis import (
    GeminiTextClassificationResponse,
    TextClassificationAnalysisResult,
    TextClassificationChunkResult,
)
from app.schemas.source import SourceDocument
from app.services.gemini_service import GeminiService


class TextClassificationService:
    def __init__(self, gemini_service: GeminiService):
        self.settings = get_settings()
        self.gemini_service = gemini_service
        self._item_marker_pattern = re.compile(r"(?:\d+[\.)]|[-•*‣◦⁃●▪])")

    @staticmethod
    def _split_list_items(text: str) -> list[str]:
        normalized = re.sub(r"[\u200b\ufeff]", "", text).strip()
        if not normalized:
            return []

        matches = list(re.finditer(r"(?:(?<=^)|(?<=[\s\n]))(?:\d+[\.)]|[-•*‣◦⁃●▪])\s*", normalized))
        if len(matches) < 2:
            return []

        items: list[str] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            item = normalized[start:end].strip(" \t\r\n-•*")
            if item:
                items.append(item)

        return items

    def _split_sentence_like_text(self, text: str) -> list[str]:
        normalized = re.sub(r"[\u200b\ufeff]", "", text).strip()
        if not normalized:
            return []

        if len(normalized) <= self.settings.chunk_max_chars:
            sentence_boundaries = list(re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9\"'‘“(])", normalized))
            if sentence_boundaries:
                parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'‘“(])", normalized) if part.strip()]
                if len(parts) > 1:
                    return parts

        return []

    def _split_by_boundaries(self, text: str) -> list[str]:
        list_items = self._split_list_items(text)
        if list_items:
            return list_items

        sentence_items = self._split_sentence_like_text(text)
        if sentence_items:
            return sentence_items

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
                page_list_items = self._split_list_items(page.text)
                if page_list_items:
                    chunks.extend(page_list_items)
                    continue
                page_chunks = self._split_by_boundaries(page.text) or [page.text]
                chunks.extend(page_chunks)
            return [chunk for chunk in chunks if chunk.strip()]

        text = source.extracted_text or source.text or ""
        list_items = self._split_list_items(text)
        if list_items:
            return list_items

        sentence_items = self._split_sentence_like_text(text)
        if sentence_items:
            return sentence_items

        return self._split_by_boundaries(text) or ([text.strip()] if text.strip() else [])

    async def analyze(self, source: SourceDocument) -> TextClassificationAnalysisResult:
        chunks = self._build_chunks(source)
        if not chunks:
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        chunk_results: list[TextClassificationChunkResult] = []
        for index, chunk in enumerate(chunks):
            prompt = build_text_classification_prompt(chunk)
            response = await self.gemini_service.generate_structured(prompt, GeminiTextClassificationResponse)
            if not response.results:
                raise AppError("GEMINI_RESPONSE_INVALID", "Gemini returned no classification results.", status_code=502)

            classification = max(response.results, key=lambda item: item.confidence)
            chunk_results.append(
                TextClassificationChunkResult(
                    chunk_index=index,
                    chunk_text=chunk,
                    label=classification.category,
                    confidence=classification.confidence,
                    reason=classification.reasoning,
                )
            )

        final_label, confidence, reason = self._aggregate(chunk_results)
        return TextClassificationAnalysisResult(
            label=final_label,
            confidence=confidence,
            reason=reason,
            chunk_results=chunk_results,
        )

    def _aggregate(self, chunk_results: list[TextClassificationChunkResult]) -> tuple[str, float, str]:
        weights: dict[str, float] = {}
        reason_by_label: dict[str, str] = {}
        for chunk in chunk_results:
            weights[chunk.label] = weights.get(chunk.label, 0.0) + chunk.confidence
            reason_by_label.setdefault(chunk.label, chunk.reason)

        label = max(weights.items(), key=lambda item: item[1])[0]
        total = sum(weights.values()) or 1.0
        confidence = round(min(0.99, max(weights.get(label, 0.0), 0.5) / total if total else 0.5), 2)
        reason = reason_by_label.get(label) or chunk_results[0].reason
        return label, confidence, reason