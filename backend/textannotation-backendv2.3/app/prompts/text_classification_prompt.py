from __future__ import annotations


def build_text_classification_prompt(text: str) -> str:
    return (
        "You are performing text classification only. "
        "Classify the text into the most appropriate issue category based on its meaning. "
        "Use labels such as Login Issue, Performance Issue, Payment Issue, or another short business issue label when the text clearly supports it. "
        "Return strict JSON as an object with a results array. "
        "Each result item must contain text, category, confidence, and reasoning. "
        "confidence must be a number between 0 and 1. "
        "reasoning must explain the classification using only the text.\n\n"
        f"TEXT:\n{text}"
    )