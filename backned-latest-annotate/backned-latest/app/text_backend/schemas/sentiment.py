from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.text_backend.core.config import SentimentLabel


class SentimentAnalysisResult(BaseModel):
    analysis_type: Literal["SENTIMENT_ANALYSIS"] = "SENTIMENT_ANALYSIS"
    analysis_level: Literal["document", "page", "paragraph", "sentence"] = "document"
    sentiment: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    chunk_results: list["SentimentChunkResult"] = Field(default_factory=list)


class SentimentChunkResult(BaseModel):
    chunk_index: int
    chunk_text: str
    sentiment: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    level: Literal["document", "page", "paragraph", "sentence"] = "document"
    page: int | None = None
    paragraph_index: int | None = None
    sentence_index: int | None = None
    start: int | None = None
    end: int | None = None


class GeminiSentimentResponse(BaseModel):
    analysis_type: Literal["SENTIMENT_ANALYSIS"] = "SENTIMENT_ANALYSIS"
    sentiment: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

