from __future__ import annotations


def build_entity_extraction_prompt(identification_names: list[str], candidate_text: str) -> str:
    requested_entities = "\n".join(f"- {name}" for name in identification_names)
    return (
        "You are extracting requested entities from a single document using Gemini 2.5 Flash. "
        "This is document analysis only. Do not invent entities. "
        "Match entity names case-insensitively, using exact terms when present and close semantic variations only when appropriate. "
        "Return strict JSON with key: entities and no surrounding markdown or commentary. "
        "Each entity must contain entity_name, matched_text, tag, found, and confidence_score. "
        "confidence_score must be a number between 0 and 1 representing how confident you are that the tag and match are correct. "
        "For every requested entity, include one object in the same order. "
        "If the entity is present, set found=true and matched_text to the exact wording from the document. "
        "If the entity is not present, set found=false and matched_text to null. "
        "Use a concise tag such as PERSON, JOB_TITLE, TECHNOLOGY, FRAMEWORK, DATABASE, CLOUD_PLATFORM, AI_MODEL, SKILL, ORGANIZATION, LOCATION, PRODUCT, TOOL, or OTHER. "
        "Only confirm entities supported by the text.\n\n"
        f"REQUESTED ENTITIES:\n{requested_entities}\n\n"
        f"CANDIDATE TEXT:\n{candidate_text}"
    )
