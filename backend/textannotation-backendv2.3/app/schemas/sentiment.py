from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import SentimentLabel


class SentimentAnalysisResult(BaseModel):
    analysis_type: Literal["SENTIMENT_ANALYSIS"] = "SENTIMENT_ANALYSIS"
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


class GeminiSentimentResponse(BaseModel):
    analysis_type: Literal["SENTIMENT_ANALYSIS"] = "SENTIMENT_ANALYSIS"
    sentiment: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
