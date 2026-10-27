from __future__ import annotations


def build_relation_extraction_prompt(text: str) -> str:
    return (
        "You are performing relation extraction only. "
        "Identify meaningful relationships between entities explicitly supported by the text, including contract-style relationships in business documents. "
        "Do not invent entities or relations. "
        "Return strict JSON with keys: analysis_type, confidence, reason, relations. "
        "analysis_type must be RELATION_EXTRACTION. "
        "confidence must be a number between 0 and 1 summarizing the overall quality of the extracted relations. "
        "reason must briefly explain the overall extraction. "
        "Each relation item must contain source, relation, target, confidence, and reasoning. "
        "Use concise relation labels such as WORKS_FOR, HAS_ROLE, REPORTS_TO, EMPLOYS, CONTRACTED_WITH, SIGNED_WITH, PROVIDES_SERVICE_TO, OWNS, PARTNERS_WITH, LOCATED_IN, or OTHER. "
        "Only include relations that are clearly supported by the text. "
        "If no explicit relation is present, return an empty relations array and explain that no relation could be confirmed.\n\n"
        f"TEXT:\n{text}"
    )