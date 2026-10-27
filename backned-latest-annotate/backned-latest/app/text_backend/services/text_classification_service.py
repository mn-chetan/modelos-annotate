from __future__ import annotations

import asyncio
import math
import re

from app.text_backend.core.config import get_settings
from app.text_backend.core.exceptions import AppError
from app.text_backend.prompts.text_classification_prompt import build_text_classification_prompt
from app.text_backend.schemas.analysis import (
    GeminiTextClassificationResponse,
    TextClassificationAnalysisResult,
    TextClassificationChunkResult,
)
from app.text_backend.schemas.source import PageText, SourceDocument
from app.text_backend.services.gemini_service import GeminiService


class TextClassificationService:
    def __init__(self, gemini_service: GeminiService):
        self.settings = get_settings()
        self.gemini_service = gemini_service
        self._item_marker_pattern = re.compile(r"(?:\d+[\.)]|[-â€¢*â€£â—¦âƒâ—â–ª])")

    @staticmethod
    def _split_list_items(text: str) -> list[str]:
        normalized = re.sub(r"[\u200b\ufeff]", "", text).strip()
        if not normalized:
            return []

        matches = list(re.finditer(r"(?:(?<=^)|(?<=[\s\n]))(?:\d+[\.)]|[-â€¢*â€£â—¦âƒâ—â–ª])\s*", normalized))
        if len(matches) < 2:
            return []

        items: list[str] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            item = normalized[start:end].strip(" \t\r\n-â€¢*")
            if item:
                items.append(item)

        return items

    def _split_sentence_like_text(self, text: str) -> list[str]:
        normalized = re.sub(r"[\u200b\ufeff]", "", text).strip()
        if not normalized:
            return []

        if len(normalized) <= self.settings.chunk_max_chars:
            sentence_boundaries = list(re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9\"'â€˜â€œ(])", normalized))
            if sentence_boundaries:
                parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'â€˜â€œ(])", normalized) if part.strip()]
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

    def _granular_segments(self, source: SourceDocument, level: str) -> list[dict]:
        pages = source.pages or [PageText(page=1, text=source.extracted_text or source.text or "")]
        full_text = source.extracted_text or source.text or ""
        search_cursor = 0
        segments: list[dict] = []
        for page in pages:
            page_text = page.text or ""
            if not page_text.strip():
                continue
            page_base = full_text.find(page_text, search_cursor)
            if page_base < 0:
                page_base = search_cursor
            search_cursor = page_base + len(page_text)
            if level == "page":
                segments.append({"text": page_text.strip(), "page": page.page, "start": page_base, "end": page_base + len(page_text), "paragraph_index": None, "sentence_index": None})
                continue
            paragraphs = list(re.finditer(r"[^\r\n]+(?:\r?\n(?!\r?\n)[^\r\n]+)*", page_text))
            paragraph_index = 0
            for paragraph_match in paragraphs:
                paragraph_text = paragraph_match.group(0).strip()
                if not paragraph_text:
                    continue
                paragraph_start = paragraph_match.start() + len(paragraph_match.group(0)) - len(paragraph_match.group(0).lstrip())
                if level == "paragraph":
                    segments.append({"text": paragraph_text, "page": page.page, "start": page_base + paragraph_start, "end": page_base + paragraph_start + len(paragraph_text), "paragraph_index": paragraph_index, "sentence_index": None})
                else:
                    # Do not split on decimal points or abbreviations inside a sentence.
                    for sentence_index, sentence_match in enumerate(re.finditer(r".+?(?:[.!?]+(?=\s|$)|$)", paragraph_text)):
                        sentence_text = sentence_match.group(0).strip()
                        if sentence_text:
                            sentence_start = paragraph_start + sentence_match.start() + len(sentence_match.group(0)) - len(sentence_match.group(0).lstrip())
                            segments.append({"text": sentence_text, "page": page.page, "start": page_base + sentence_start, "end": page_base + sentence_start + len(sentence_text), "paragraph_index": paragraph_index, "sentence_index": sentence_index})
                paragraph_index += 1
        return segments

    async def analyze(self, source: SourceDocument, analysis_level: str = "document", categories: list[str] | None = None) -> TextClassificationAnalysisResult:
        level = analysis_level if analysis_level in {"document", "page", "paragraph", "sentence"} else "document"
        if level == "document":
            segments = [{"text": chunk, "page": None, "start": None, "end": None, "paragraph_index": None, "sentence_index": None} for chunk in self._build_chunks(source)]
        else:
            segments = self._granular_segments(source, level)
        if not segments:
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        # A document-level label does not require one request per bullet or
        # sentence. Group large PDFs into at most 12 sections to keep request
        # volume bounded while retaining representative text coverage.
        if level == "document" and len(segments) > 12:
            group_size = math.ceil(len(segments) / 12)
            segments = [
                {"text": "\n\n".join(item["text"] for item in segments[start:start + group_size]), "page": None, "start": None, "end": None, "paragraph_index": None, "sentence_index": None}
                for start in range(0, len(segments), group_size)
            ]

        async def classify_segment(index: int, segment: dict) -> TextClassificationChunkResult:
            prompt = build_text_classification_prompt(segment["text"], categories)
            response = await self.gemini_service.generate_structured(prompt, GeminiTextClassificationResponse)
            if not response.results:
                raise AppError("GEMINI_RESPONSE_INVALID", "Gemini returned no classification results.", status_code=502)

            classification = max(response.results, key=lambda item: item.confidence)
            return TextClassificationChunkResult(
                chunk_index=index,
                chunk_text=segment["text"],
                label=classification.category,
                confidence=classification.confidence,
                reason=classification.reasoning,
                level=level,
                page=segment["page"],
                paragraph_index=segment["paragraph_index"],
                sentence_index=segment["sentence_index"],
                start=segment["start"],
                end=segment["end"],
            )

        # A PDF can contain dozens of list items. Sequential Gemini calls
        # made one document take several minutes. Keep concurrency bounded so
        # multiple uploaded PDFs remain responsive without exhausting quotas.
        max_concurrency = max(1, min(4, int(getattr(self.settings, "gemini_concurrency", 4))))
        semaphore = asyncio.Semaphore(max_concurrency)

        async def bounded_classify(index: int, segment: dict) -> TextClassificationChunkResult:
            async with semaphore:
                return await classify_segment(index, segment)

        chunk_results = list(await asyncio.gather(
            *(bounded_classify(index, segment) for index, segment in enumerate(segments))
        ))

        final_label, confidence, reason = self._aggregate(chunk_results)
        return TextClassificationAnalysisResult(
            analysis_level=level,
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
