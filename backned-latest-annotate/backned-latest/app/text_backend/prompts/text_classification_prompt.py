from __future__ import annotations


def build_text_classification_prompt(text: str, categories: list[str] | None = None) -> str:
    category_instruction = (
        f"Use only these configured categories: {', '.join(categories)}. Do not invent a new category. "
        if categories else
        "Use the categories supported by the configured project. Do not invent a new category when a configured category applies. "
    )
    return (
        "You are performing text classification only. "
        "Classify the text into the most appropriate configured category based on its meaning. "
        + category_instruction
        + "Return strict JSON as an object with a results array. "
        "Each result item must contain text, category, confidence, and reasoning. "
        "confidence must be a number between 0 and 1. "
        "reasoning must explain the classification using only the text.\n\n"
        f"TEXT:\n{text}"
    )
