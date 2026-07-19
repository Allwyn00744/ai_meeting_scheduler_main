"""
GeminiService — thin wrapper around the official Google Gen AI Python SDK.

Responsibilities:
  - Lazily initialise and cache the Gemini client.
  - Check for a missing/blank API key before attempting client construction.
  - Make model calls requesting structured JSON output.
  - Parse and return raw dicts.
  - Translate provider errors into clean HTTP exceptions.

Must NOT:
  - Perform database operations.
  - Perform scheduling or business-logic decisions.
  - Log API keys, JWT tokens, OAuth tokens, raw provider error bodies,
    or prompt contents that may contain user data.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Lazy module-level references so the application starts even when
# google-genai is not installed or the API key is absent.
_genai: Any = None
_genai_types: Any = None


def _load_genai() -> tuple[Any, Any]:
    global _genai, _genai_types

    if _genai is None:
        try:
            from google import genai  # type: ignore[import-untyped]
            from google.genai import types  # type: ignore[import-untyped]

            _genai = genai
            _genai_types = types
        except ImportError:
            logger.error(
                "google-genai package is not installed. "
                "Run: pip install 'google-genai>=1.0.0'"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is unavailable (missing dependency).",
            )

    return _genai, _genai_types


class GeminiService:
    """
    Stateless Gemini client wrapper. The client is lazily initialised
    and cached at class level so it is created once per process.

    If GEMINI_API_KEY is absent or blank the application still starts
    normally; each AI call returns 503 immediately without touching the
    network.
    """

    _client: Any = None

    @classmethod
    def _get_client(cls) -> Any:
        # Import settings here to avoid circular imports at module load.
        from app.core.config import settings  # noqa: PLC0415

        # --- Key presence check (before any network call) ---
        if not settings.gemini_api_key_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not configured.",
            )

        if cls._client is None:
            genai, _ = _load_genai()
            try:
                # settings.GEMINI_API_KEY is intentionally not logged.
                cls._client = genai.Client(
                    api_key=settings.GEMINI_API_KEY
                )
            except Exception:
                logger.error("Failed to initialise Gemini client.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "AI service is unavailable. "
                        "Please try again later."
                    ),
                )

        return cls._client

    @classmethod
    def transcribe_audio(cls, audio_bytes: bytes, mime_type: str) -> str:
        """
        Transcribe spoken audio to plain text using Gemini's multimodal
        input. Used by voice scheduling (POST /ai/schedule-voice) as a
        preprocessing step before the existing text-scheduling pipeline
        — the transcript produced here is handed to the exact same code
        path as typed text.

        Raises:
            503 — API key absent/blank, or provider unreachable/timed out.
            502 — provider returned an empty transcript.

        audio_bytes may contain user-supplied audio; it is never
        written to logs.
        """
        client = cls._get_client()
        _, types = _load_genai()
        from app.core.config import settings  # noqa: PLC0415

        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type=mime_type,
                    ),
                    (
                        "Transcribe this audio exactly as spoken. "
                        "Return ONLY the transcript text, with no "
                        "commentary, labels, or markdown formatting."
                    ),
                ],
            )
            transcript = response.text

        except HTTPException:
            raise
        except Exception:
            # Intentionally NOT logging the exception body — it may
            # contain audio-derived content.
            logger.error(
                "Gemini audio transcription failed. model=%s",
                settings.GEMINI_MODEL,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "AI service is temporarily unavailable. "
                    "Please try again."
                ),
            )

        if not transcript or not transcript.strip():
            logger.error(
                "Gemini returned an empty transcript. model=%s",
                settings.GEMINI_MODEL,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Could not transcribe the audio. Please ensure "
                    "the recording contains clear speech and try again."
                ),
            )

        return transcript.strip()

    @classmethod
    def generate_json(cls, prompt: str) -> dict[str, Any]:
        """
        Call Gemini with JSON output mode and return a parsed dict.

        Raises:
            503  — API key absent/blank, or provider unreachable/timed out.
            502  — provider returned a non-JSON or empty response.

        The prompt parameter may contain user-supplied text; it is
        never written to logs.
        """
        from app.core.config import settings  # noqa: PLC0415

        client = cls._get_client()
        _, types = _load_genai()

        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            raw: str | None = response.text

        except HTTPException:
            raise
        except Exception:
            # Intentionally NOT logging the exception body — it may
            # contain prompt text, tokens, or raw provider details.
            logger.error(
                "Gemini API call failed. model=%s",
                settings.GEMINI_MODEL,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "AI service is temporarily unavailable. "
                    "Please try again."
                ),
            )

        if not raw:
            logger.error(
                "Gemini returned an empty response. model=%s",
                settings.GEMINI_MODEL,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service returned an unexpected empty response.",
            )

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Do NOT log `raw` — it may reproduce user-supplied text.
            logger.error(
                "Gemini returned non-JSON output. model=%s",
                settings.GEMINI_MODEL,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service returned malformed output.",
            )
