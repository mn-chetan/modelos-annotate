from __future__ import annotations

from app.text_backend.core.config import get_settings
from app.text_backend.core.exceptions import AppError
from app.text_backend.prompts.drug_validation_prompt import build_entity_extraction_prompt
from app.text_backend.schemas.entity import EntityAnalysisResult, EntityMatch, EntityValidationResponse
from app.text_backend.schemas.source import PageText, SourceDocument
from app.text_backend.services.gemini_service import GeminiService


class DrugMatchingService:
    def __init__(self, gemini_service: GeminiService):
        self.settings = get_settings()
        self.gemini_service = gemini_service

    @staticmethod
    def _split_identification_names(raw_value: str) -> list[str]:
        parts = [part.strip() for part in raw_value.replace("\n", ",").split(",")]
        return [part for part in parts if part]

    @staticmethod
    def _source_text(source: SourceDocument) -> str:
        if source.extracted_text and source.extracted_text.strip():
            return source.extracted_text
        if source.text and source.text.strip():
            return source.text
        if source.pages:
            return "\n".join(page.text for page in source.pages if page.text.strip())
        return ""

    async def analyze(self, source: SourceDocument, identification_name: str) -> EntityAnalysisResult:
        requested_entities = self._split_identification_names(identification_name)
        if not requested_entities:
            raise AppError("IDENTIFICATION_NAME_REQUIRED", "identification_name is required for entity extraction.", status_code=422)

        candidate_text = self._source_text(source)
        if not candidate_text.strip():
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        prompt = build_entity_extraction_prompt(requested_entities, candidate_text)
        validation = await self.gemini_service.generate_structured(prompt, EntityValidationResponse)
        return EntityAnalysisResult(entities=validation.entities)

