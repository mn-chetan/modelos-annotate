from __future__ import annotations


def build_sentiment_prompt(text: str) -> str:
    return (
        "You are performing document and text sentiment analysis.\n"
        "Classify the supplied text into one of four sentiments: POSITIVE, NEGATIVE, NEUTRAL, or MIXED.\n\n"
        "Sentiment Classification Rules:\n"
        "- POSITIVE: The text explicitly expresses a positive opinion, satisfaction, happiness, appreciation, praise, or favorable evaluation.\n"
        "- NEGATIVE: The text explicitly expresses a negative opinion, dissatisfaction, anger, disappointment, criticism, or an unfavorable evaluation.\n"
        "- NEUTRAL: The text is factual, descriptive, informational, or does not express a clear positive or negative sentiment.\n"
        "- MIXED: The text explicitly expresses significant positive and negative opinions/evaluations simultaneously.\n\n"
        "Crucial Guidelines for Medical Reports, Symptoms, and Factual Descriptions:\n"
        "1. Medical symptoms do not automatically indicate negative sentiment.\n"
        "2. Words such as 'complaint', 'pain', 'headache', 'dizziness', 'diagnosis', 'hospital', and 'disease' must NOT independently determine sentiment.\n"
        "3. A negative medical condition, injury, or illness is clinical/factual information, NOT negative sentiment.\n"
        "4. A hospital visit, medical report, or patient record must be classified based on expressed sentiment (e.g., patient satisfaction/dissatisfaction), NOT its subject matter.\n"
        "5. If a sentence describes pain, symptoms, or diagnoses without expressing dissatisfaction, anger, or criticism, classify it as NEUTRAL.\n"
        "6. If a sentence reports symptoms or pain but also explicitly praises medical care (e.g., 'reported severe pain but praised the doctor for excellent care'), determine the sentiment based on the expressed evaluation (praise/appreciation), not the symptoms alone.\n"
        "7. Do not assume that every sentence contains sentiment. When no clear sentiment is expressed, use NEUTRAL.\n\n"
        "Additional Instructions:\n"
        "- Preserve the meaning of the complete supplied segment; do not split or rewrite structured fields such as 'Order ID:', "
        "'Product:', 'Seller:', 'Order Date:', or 'Delivery Address:'.\n"
        "- Do not provide medical advice, treatment claims, or safety claims.\n"
        "- Return strict JSON with keys: analysis_type, sentiment, confidence, reason.\n"
        "- analysis_type must be SENTIMENT_ANALYSIS.\n"
        "- confidence must be a number between 0 and 1.\n"
        "- reason must provide a clear, concise justification based solely on the text.\n\n"
        f"TEXT:\n{text}"
    )
