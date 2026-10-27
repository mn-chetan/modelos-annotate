from __future__ import annotations

import asyncio
import re
import math
from collections import Counter

from app.text_backend.core.config import get_settings
from app.text_backend.core.exceptions import AppError
from app.text_backend.prompts.sentiment_prompt import build_sentiment_prompt
from app.text_backend.schemas.sentiment import GeminiSentimentResponse, SentimentAnalysisResult, SentimentChunkResult
from app.text_backend.schemas.source import PageText, SourceDocument
from app.text_backend.services.gemini_service import GeminiService


class SentimentService:
    def __init__(self, gemini_service: GeminiService):
        self.settings = get_settings()
        self.gemini_service = gemini_service

    def _split_by_boundaries(self, text: str) -> list[str]:
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
                    # A period is a sentence boundary only when followed by whitespace/end.
                    # This keeps decimals such as "$4.2 million" inside the same sentence.
                    sentence_matches = list(re.finditer(r".+?(?:[.!?]+(?=\s|$)|$)", paragraph_text))
                    for sentence_index, sentence_match in enumerate(sentence_matches):
                        sentence_text = sentence_match.group(0).strip()
                        if sentence_text:
                            sentence_start = paragraph_start + sentence_match.start() + len(sentence_match.group(0)) - len(sentence_match.group(0).lstrip())
                            segments.append({"text": sentence_text, "page": page.page, "start": page_base + sentence_start, "end": page_base + sentence_start + len(sentence_text), "paragraph_index": paragraph_index, "sentence_index": sentence_index})
                paragraph_index += 1
        return segments

    async def analyze(self, source: SourceDocument, analysis_level: str = "document") -> SentimentAnalysisResult:
        level = analysis_level if analysis_level in {"document", "page", "paragraph", "sentence"} else "document"
        if level == "document":
            segments = [{"text": chunk, "page": None, "start": None, "end": None, "paragraph_index": None, "sentence_index": None} for chunk in self._build_chunks(source)]
        else:
            segments = self._granular_segments(source, level)
        if not segments:
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        # Document-level sentiment needs one representative result per
        # grouped section, not one Gemini request per PDF bullet/sentence.
        # This prevents a long PDF from generating hundreds of requests.
        if level == "document" and len(segments) > 12:
            group_size = math.ceil(len(segments) / 12)
            segments = [
                {"text": "\n\n".join(item["text"] for item in segments[start:start + group_size]), "page": None, "start": None, "end": None, "paragraph_index": None, "sentence_index": None}
                for start in range(0, len(segments), group_size)
            ]

        async def analyze_segment(index: int, segment: dict) -> SentimentChunkResult:
            prompt = build_sentiment_prompt(segment["text"])
            response = await self.gemini_service.generate_structured(prompt, GeminiSentimentResponse)
            return SentimentChunkResult(
                chunk_index=index,
                chunk_text=segment["text"],
                sentiment=response.sentiment,
                confidence=response.confidence,
                reason=response.reason,
                level=level,
                page=segment["page"],
                paragraph_index=segment["paragraph_index"],
                sentence_index=segment["sentence_index"],
                start=segment["start"],
                end=segment["end"],
            )

        semaphore = asyncio.Semaphore(4)

        async def bounded_analyze(index: int, segment: dict) -> SentimentChunkResult:
            async with semaphore:
                return await analyze_segment(index, segment)

        chunk_results = list(await asyncio.gather(
            *(bounded_analyze(index, segment) for index, segment in enumerate(segments))
        ))

        final_sentiment, confidence, reason = self._aggregate(chunk_results)
        return SentimentAnalysisResult(
            analysis_level=level,
            sentiment=final_sentiment,
            confidence=confidence,
            reason=reason,
            chunk_results=chunk_results,
        )

    def _aggregate(self, chunk_results: list[SentimentChunkResult]) -> tuple[str, float, str]:
        weights = Counter()
        reason_by_label: dict[str, str] = {}
        for chunk in chunk_results:
            weights[chunk.sentiment] += chunk.confidence
            reason_by_label.setdefault(chunk.sentiment, chunk.reason)

        positive = weights.get("POSITIVE", 0.0)
        negative = weights.get("NEGATIVE", 0.0)
        neutral = weights.get("NEUTRAL", 0.0)
        mixed = weights.get("MIXED", 0.0)
        total = positive + negative + neutral + mixed or 1.0

        if positive > 0 and negative > 0:
            sentiment = "MIXED"
        elif mixed > 0 and positive == 0 and negative == 0:
            sentiment = "MIXED"
        elif positive >= negative and positive > 0:
            sentiment = "POSITIVE"
        elif negative > positive and negative > 0:
            sentiment = "NEGATIVE"
        else:
            sentiment = "NEUTRAL"

        confidence = round(min(0.99, max(weights.get(sentiment, 0.0), 0.5) / total if total else 0.5), 2)
        reason = reason_by_label.get(sentiment) or chunk_results[0].reason
        return sentiment, confidence, reason

