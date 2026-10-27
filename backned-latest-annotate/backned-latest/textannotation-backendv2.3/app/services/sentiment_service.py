from __future__ import annotations

import re
from collections import Counter

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.prompts.sentiment_prompt import build_sentiment_prompt
from app.schemas.sentiment import GeminiSentimentResponse, SentimentAnalysisResult, SentimentChunkResult
from app.schemas.source import PageText, SourceDocument
from app.services.gemini_service import GeminiService


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

    async def analyze(self, source: SourceDocument) -> SentimentAnalysisResult:
        chunks = self._build_chunks(source)
        if not chunks:
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        chunk_results: list[SentimentChunkResult] = []
        for index, chunk in enumerate(chunks):
            prompt = build_sentiment_prompt(chunk)
            response = await self.gemini_service.generate_structured(prompt, GeminiSentimentResponse)
            chunk_results.append(
                SentimentChunkResult(
                    chunk_index=index,
                    chunk_text=chunk,
                    sentiment=response.sentiment,
                    confidence=response.confidence,
                    reason=response.reason,
                )
            )

        final_sentiment, confidence, reason = self._aggregate(chunk_results)
        return SentimentAnalysisResult(
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
