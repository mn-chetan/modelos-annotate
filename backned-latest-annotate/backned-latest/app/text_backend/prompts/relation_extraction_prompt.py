from __future__ import annotations


def build_relation_extraction_prompt(
    text: str,
    relation_ontology: list[str] | None = None,
    detected_entities: list[dict[str, str]] | None = None,
) -> str:
    configured = [str(item).strip() for item in (relation_ontology or []) if str(item).strip()]
    ontology_instruction = (
        f"The approved relation ontology is: {configured}. Use only these relation labels. "
        "Use OTHER only when OTHER is explicitly present in that ontology and the evidence cannot be mapped. "
        if configured
        else "No relation ontology was supplied. Infer a concise relation label from the explicit wording and context, and return only relations supported by the text. "
    )
    relation_examples = (
        "Use only the configured relation labels that are semantically supported by the source text. "
        if configured
        else ""
    )
    return (
        "You are performing relation extraction only. "
        "Identify meaningful relationships between entities explicitly supported by the text, including contract-style relationships in business documents. "
        "Do not invent entities or relations; every relation must have direct textual evidence. "
        "Return strict JSON with keys: analysis_type, confidence, reason, relations. "
        "analysis_type must be RELATION_EXTRACTION. "
        "confidence must be the model's genuine confidence when available, otherwise null; it is not annotation accuracy. "
        "reason must briefly explain the overall extraction. "
        "Each relation item must contain source, source_type, relation, target, target_type, evidence, confidence, and reasoning. confidence is REQUIRED for every extracted relation and must be a numeric model-estimated value from 0.0 to 1.0; do not omit it. "
        "source and target must be the shortest exact contiguous entity mentions from TEXT, not a sentence, clause, description, or role phrase. Keep titles, dates, amounts, and organizations as separate endpoints when the text expresses separate relationships. "
        "When detected entity spans are supplied, prefer their exact text and types, but treat them as hints rather than a closed list. Discover additional entity endpoints when the text clearly identifies them. Do not use pronouns, arbitrary nouns, or document-level placeholders as endpoints. "
        f"{ontology_instruction}"
        f"{relation_examples}"
        "evidence is mandatory and must be copied verbatim from TEXT, including both source and target mentions and the wording that expresses their relationship. Never substitute the whole chunk merely because evidence is unavailable. Only include relations that are clearly supported by the text. "
        "If no explicit relation is present, return an empty relations array and explain that no relation could be confirmed.\n\n"
        f"ENTITY HINTS (not exhaustive):\n{detected_entities or []}\n\nTEXT:\n{text}"
    )
