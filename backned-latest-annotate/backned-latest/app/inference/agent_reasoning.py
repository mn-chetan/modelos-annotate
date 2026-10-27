"""Shared JSON-only reasoning helper for annotation agents."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Any

from app.logging import get_logger

vertex_agent_available: bool = True
logger = get_logger(__name__)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _response_text(response: Any) -> str:
    """Extract text from OpenAI-compatible and google-genai response shapes."""
    direct = getattr(response, "text", None)
    if isinstance(direct, str) and direct.strip():
        return direct
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content", "")
            if isinstance(content, list):
                return "".join(
                    str(part.get("text", "")) if isinstance(part, dict) else str(part)
                    for part in content
                )
            return str(content or "")
    parts: list[str] = []
    for candidate in (getattr(response, "candidates", None) or []):
        content = getattr(candidate, "content", None)
        for part in (getattr(content, "parts", None) or []):
            text = getattr(part, "text", None)
            if text:
                parts.append(str(text))
    return "".join(parts)


def call_json_agent(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    settings: Any | None = None,
    max_output_tokens: int = 1200,
) -> dict[str, Any] | None:
    """Call the configured reasoning model and return parsed JSON only."""
    if not vertex_agent_available:
        return None
    if settings is not None and not bool(getattr(settings, "agent_enabled", True)):
        return None

    azure_endpoint = getattr(settings, "azure_openai_endpoint", None) or os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = getattr(settings, "azure_openai_api_key", None) or os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = getattr(settings, "azure_openai_deployment", None) or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4-mini")

    payload_text = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))

    if azure_endpoint and azure_key:
        import httpx
        url = azure_endpoint.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        retry_delay = 0.5
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                r = httpx.post(
                    url,
                    headers={"api-key": azure_key.strip(), "Content-Type": "application/json"},
                    json={
                        "model": azure_deployment.strip(),
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"INPUT JSON:\n{payload_text}"},
                        ],
                        "temperature": 0.1,
                        "max_completion_tokens": max_output_tokens,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=30.0,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                resp_json = r.json()
                content = _response_text(resp_json)
                parsed = _extract_json(content)
                if parsed is not None:
                    return parsed
            except Exception as exc:
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2.0
                else:
                    logger.warning("agent_request_failed", transport="azure_openai", model=azure_deployment, error=str(exc))
                    return None
        return None

    model = (
        getattr(settings, "vertex_agent_model", None)
        or getattr(settings, "gemini_agent_model", None)
        or os.getenv("VERTEX_AGENT_MODEL")
        or "gemini-3.6-flash"
    )

    project = (
        getattr(settings, "google_cloud_project", None)
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or getattr(settings, "firebase_project_id", None)
        or "prod-y-in2300452"
    ).strip()
    location = (
        getattr(settings, "vertex_location", None)
        or os.getenv("VERTEX_LOCATION")
        or "global"
    ).strip()

    if not project:
        project = "prod-y-in2300452"

    try:
        from google import genai
        from google.genai import types

        # Vertex AI with Application Default Credentials (ADC) ONLY.
        client = genai.Client(vertexai=True, project=project, location=location)

        retry_delay = 0.5
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"INPUT JSON:\n{payload_text}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.1,
                        max_output_tokens=max_output_tokens,
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                content = _response_text(response)
                parsed = _extract_json(content)
                if parsed is None:
                    logger.warning(
                        "agent_json_empty",
                        transport="vertex",
                        model=model,
                        response_type=type(response).__name__,
                        content_length=len(content) if content else 0,
                        finish_reasons=[
                            str(getattr(candidate, "finish_reason", ""))
                            for candidate in (getattr(response, "candidates", None) or [])
                        ],
                    )
                return parsed
            except Exception as exc:  # noqa: BLE001
                if attempt < max_retries:
                    logger.warning(
                        "agent_request_retry",
                        transport="vertex",
                        model=model,
                        attempt=attempt + 1,
                        error=str(exc),
                        delay=retry_delay,
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2.0
                else:
                    logger.warning("agent_request_failed", transport="vertex", model=model, error=str(exc))
                    return None
        return None
    except Exception as exc:
        logger.warning("agent_request_failed", transport="vertex", model=model, error=str(exc))
        return None
