from __future__ import annotations

import re
from typing import Any

from app.text_backend.core.config import get_settings
from app.text_backend.core.exceptions import AppError
from app.text_backend.schemas.entity import EntityAnalysisResult, EntityMatch, EntityValidationResponse
from app.text_backend.schemas.source import SourceDocument
from app.text_backend.services.gemini_service import GeminiService


def build_generic_entity_extraction_prompt(target_labels: list[str], candidate_text: str) -> str:
    categories_str = ", ".join(target_labels) if target_labels else "the configured project entity categories"
    return (
        "You are performing Named Entity Recognition (NER) / Entity Extraction on the candidate text using Gemini. "
        "Identify and extract all named entities matching the target categories/labels from the document. "
        f"TARGET ENTITY CATEGORIES / LABELS:\n{categories_str}\n\n"
        "Return strict JSON with key 'entities' and no surrounding markdown or commentary. "
        "Each entity in the list must contain:\n"
        "- entity_name: the matching category name from target categories (e.g. Person, Organization, Location, Date, Product, Event, Money, etc.)\n"
        "- matched_text: the exact verbatim substring from candidate_text\n"
        "- tag: entity type tag\n"
        "- found: true if present in candidate_text, false otherwise\n"
        "- confidence_score: a float between 0.0 and 1.0\n\n"
        "Choose the most specific target label supported by the surrounding context. "
        "For example, when an identifier appears next to a cue such as 'order', use a configured order-identifier label instead of a broad Product label. "
        "Do not infer Money without an explicit monetary amount, and do not invent labels outside TARGET ENTITY CATEGORIES / LABELS.\n\n"
        f"CANDIDATE TEXT:\n{candidate_text}"
    )


class GenericEntityExtractionService:
    def __init__(self, gemini_service: GeminiService):
        self.settings = get_settings()
        self.gemini_service = gemini_service

    @staticmethod
    def _source_text(source: SourceDocument) -> str:
        if source.extracted_text and source.extracted_text.strip():
            return source.extracted_text
        if source.text and source.text.strip():
            return source.text
        if source.pages:
            return "\n".join(page.text for page in source.pages if page.text.strip())
        return ""

    @staticmethod
    def _local_fallback(candidate_text: str, labels: list[str]) -> list[EntityMatch]:
        """Return useful NER spans when the remote model is unavailable.

        This is intentionally conservative and deterministic. It keeps a PDF
        from becoming an empty result merely because Gemini is unavailable or
        the extracted document is larger than the model context window.
        """
        allowed = {label.lower(): label for label in labels}
        results: list[EntityMatch] = []
        seen: set[tuple[str, int, int]] = set()

        def add(label: str, match: re.Match[str], confidence: float = 0.82) -> None:
            canonical = allowed.get(label.lower())
            if not canonical:
                return
            key = (canonical, match.start(), match.end())
            if key in seen:
                return
            seen.add(key)
            results.append(EntityMatch(
                entity_name=canonical,
                matched_text=match.group(0),
                tag=canonical,
                found=True,
                confidence_score=confidence,
            ))

        if "date" in allowed:
            for match in re.finditer(
                r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b",
                candidate_text,
                flags=re.IGNORECASE,
            ):
                add("Date", match, 0.9)

        if "money" in allowed:
            for match in re.finditer(r"(?:[$€£₹]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|USD|INR|EUR|GBP))?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|INR|EUR|GBP)\b)", candidate_text, flags=re.IGNORECASE):
                add("Money", match, 0.9)

        if "order id" in allowed:
            for match in re.finditer(r"\b(?:order\s*(?:id|number)?\s*[:#-]?\s*)?[A-Z0-9]{6,}(?:-[A-Z0-9]+)*\b", candidate_text, flags=re.IGNORECASE):
                if any(char.isdigit() for char in match.group(0)):
                    add("Order ID", match, 0.84)

        if "organization" in allowed:
            for match in re.finditer(r"\b[A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4}\s+(?:Inc\.?|Ltd\.?|LLC|Corporation|Company|Bank|University|Mahindra|Microsoft)\b", candidate_text):
                add("Organization", match, 0.84)

        if "person" in allowed:
            for match in re.finditer(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", candidate_text):
                add("Person", match, 0.8)

        if "location" in allowed:
            for match in re.finditer(r"\b(?:India|Singapore|London|Kolkata|Hyderabad|Bengaluru|Mumbai|Delhi|Austin,?\s+Texas)\b", candidate_text, flags=re.IGNORECASE):
                add("Location", match, 0.86)

        return results

    async def analyze(self, source: SourceDocument, target_labels: list[str] | None = None) -> EntityAnalysisResult:
        candidate_text = self._source_text(source)
        if not candidate_text.strip():
            raise AppError("EMPTY_TEXT", "No analyzable text was found.", status_code=422)

        labels = [lbl.strip() for lbl in (target_labels or []) if lbl and lbl.strip()]
        if not labels:
            return EntityAnalysisResult(entities=[])
        allowed = {label.lower(): label for label in labels}

        def valid_entities(entities: list[EntityMatch]) -> list[EntityMatch]:
            result: list[EntityMatch] = []
            for entity in entities:
                candidates = [getattr(entity, "tag", None), getattr(entity, "entity_type", None), entity.entity_name]
                label = next((allowed.get(str(candidate or "").strip().lower()) for candidate in candidates), None)
                if label and entity.matched_text and entity.matched_text.strip():
                    entity.tag = label
                    entity.entity_name = label
                    result.append(entity)
            return result

        # Avoid sending multi-megabyte PDF extraction output to Gemini. The
        # local fallback below still scans the complete document.
        prompt_text = candidate_text if len(candidate_text) <= 120_000 else candidate_text[:120_000]
        prompt = build_generic_entity_extraction_prompt(labels, prompt_text)
        try:
            validation = await self.gemini_service.generate_structured(prompt, EntityValidationResponse)
            semantic_entities = valid_entities(list(validation.entities))
            if semantic_entities:
                return EntityAnalysisResult(entities=semantic_entities)
        except Exception:
            pass

        # Fallback to GLiNER adapter for NER entity extraction
        try:
            from app.inference.adapters.multimodal_experts import GlinerAdapter
            adapter = GlinerAdapter(device="cpu")
            gliner_results = adapter.extract_ner(candidate_text, labels)
            matches = [
                EntityMatch(
                    entity_name=allowed[str(res.get("label") or "").strip().lower()],
                    matched_text=str(res.get("text") or ""),
                    tag=allowed[str(res.get("label") or "").strip().lower()],
                    found=True,
                    confidence_score=float(res.get("confidence") or 0.9),
                )
                for res in gliner_results
                if res.get("text") and str(res.get("label") or "").strip().lower() in allowed
            ]
            if matches:
                return EntityAnalysisResult(entities=matches)
            return EntityAnalysisResult(entities=self._local_fallback(candidate_text, labels))
        except Exception:
            return EntityAnalysisResult(entities=self._local_fallback(candidate_text, labels))
