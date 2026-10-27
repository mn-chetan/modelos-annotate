from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.text_backend.core.config import SourceType


class PageText(BaseModel):
    page: int
    text: str


class SourceDocument(BaseModel):
    source_id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    original_filename: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    text: str | None = None
    extracted_text: str | None = None
    pages: list[PageText] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SourceCreateInput(BaseModel):
    source_type: SourceType
    original_filename: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    text: str | None = None
    extracted_text: str | None = None
    pages: list[PageText] = Field(default_factory=list)

