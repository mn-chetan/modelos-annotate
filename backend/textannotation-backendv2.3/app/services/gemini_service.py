from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

import httpx
import google.auth
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiService:
    def __init__(
        self,
        model: str | None = None,
        project_id: str | None = None,
        location: str | None = None,
    ):
        settings = get_settings()
        self.model = model or settings.gemini_model
        self.project_id = project_id or settings.google_cloud_project
        self.location = location or settings.google_cloud_location
        self.timeout_seconds = settings.gemini_timeout_seconds
        self.max_retries = settings.gemini_max_retries
        self._credentials = None

    def _endpoint(self) -> str:
        project_id = self.project_id
        if not project_id and self._credentials is not None:
            project_id = getattr(self._credentials, "project_id", None) or ""

        if not project_id:
            raise AppError(
                "GEMINI_AUTH_MISSING",
                "Configure Google Cloud Application Default Credentials with GOOGLE_CLOUD_PROJECT.",
                status_code=500,
            )

        return (
            f"https://{self.location}-aiplatform.googleapis.com/v1/projects/"
            f"{project_id}/locations/{self.location}/publishers/google/models/{self.model}:generateContent"
        )

    async def _load_credentials(self) -> None:
        if self._credentials is not None:
            return

        try:
            credentials, project_id = await asyncio.to_thread(
                google.auth.default,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        except Exception as exc:
            raise AppError(
                "GOOGLE_CLOUD_AUTH_MISSING",
                "Google Cloud Application Default Credentials were not found.",
                status_code=500,
            ) from exc

        if credentials.expired and credentials.refresh_token is None:
            raise AppError(
                "GOOGLE_CLOUD_AUTH_INVALID",
                "Google Cloud credentials are invalid or expired.",
                status_code=500,
            )

        self._credentials = credentials
        if not self.project_id:
            self.project_id = project_id or getattr(credentials, "project_id", None) or self.project_id

    async def _refresh_headers(self) -> dict[str, str]:
        await self._load_credentials()
        assert self._credentials is not None
        try:
            await asyncio.to_thread(self._credentials.refresh, GoogleAuthRequest())
        except RefreshError as exc:
            raise AppError(
                "GOOGLE_CLOUD_AUTH_REAUTH_REQUIRED",
                "Google Cloud Application Default Credentials need reauthentication. Run `gcloud auth application-default login`.",
                status_code=500,
            ) from exc
        return {"Authorization": f"Bearer {self._credentials.token}"}

    async def _call_api(self, prompt: str) -> str:
        headers = await self._refresh_headers()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self._endpoint(), json=payload, headers=headers)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AppError("GEMINI_TIMEOUT", "Gemini request timed out.", status_code=504) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 404:
                raise AppError(
                    "GEMINI_MODEL_UNAVAILABLE",
                    f"Gemini model '{self.model}' is not available for the configured endpoint or credentials.",
                    status_code=502,
                ) from exc
            raise AppError("GEMINI_FAILURE", f"Gemini request failed: {exc.response.text}", status_code=502) from exc
        except httpx.HTTPError as exc:
            raise AppError("GEMINI_FAILURE", f"Gemini request failed: {exc}", status_code=502) from exc

        try:
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned")
            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
            raw_text = "".join(text_parts).strip()
            return self._strip_code_fences(raw_text)
        except Exception as exc:
            raise AppError("GEMINI_RESPONSE_INVALID", "Gemini returned an invalid response body.", status_code=502) from exc

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1]
            if stripped.endswith("```"):
                stripped = stripped[:-3]
        return stripped.strip()

    async def generate_structured(self, prompt: str, response_model: type[T]) -> T:
        last_error: Exception | None = None
        for _ in range(self.max_retries + 1):
            try:
                raw_text = await self._call_api(prompt)
                return response_model.model_validate_json(raw_text)
            except (ValidationError, json.JSONDecodeError, AppError) as exc:
                last_error = exc
                if isinstance(exc, AppError):
                    raise
            except Exception as exc:  # pragma: no cover - defensive
                last_error = exc
        raise AppError("GEMINI_VALIDATION_FAILED", f"Gemini output validation failed: {last_error}", status_code=502)