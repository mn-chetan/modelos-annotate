from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    google_cloud_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="us-central1", alias="GOOGLE_CLOUD_LOCATION")
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    mongodb_database: str = Field(default="text_annotation", alias="MONGODB_DATABASE")
    max_upload_size_mb: int = Field(default=20, alias="MAX_UPLOAD_SIZE_MB")
    fuzzy_match_threshold: int = Field(default=85, alias="FUZZY_MATCH_THRESHOLD")
    semantic_match_threshold: int = Field(default=70, alias="SEMANTIC_MATCH_THRESHOLD")
    chunk_max_chars: int = Field(default=4000, alias="CHUNK_MAX_CHARS")
    chunk_max_tokens_approx: int = Field(default=1200, alias="CHUNK_MAX_TOKENS_APPROX")
    gemini_timeout_seconds: int = Field(default=30, alias="GEMINI_TIMEOUT_SECONDS")
    gemini_max_retries: int = Field(default=2, alias="GEMINI_MAX_RETRIES")
    app_name: str = "text-annotation-backend"
    app_version: str = "1.0.0"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


AnalysisType = Literal["ENTITY_EXTRACTION", "SENTIMENT_ANALYSIS", "TEXT_CLASSIFICATION", "RELATION_EXTRACTION"]
SentimentLabel = Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]
MatchType = Literal["EXACT", "NORMALIZED", "FUZZY", "SEMANTIC", "NOT_FOUND"]
SourceType = Literal["TEXT", "PDF", "DOCX", "TXT", "IMAGE"]
