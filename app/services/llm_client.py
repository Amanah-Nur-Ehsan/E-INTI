"""Provider-agnostic structured-output LLM client.

Two tiers, per the locked routing decision:

* Tier.CLASSIFY — high volume, trivial JSON: Groq llama-3.1-8b-instant.
* Tier.VERIFY   — reasoning-heavy: Groq llama-3.3-70b-versatile, falling
  back to Gemini 2.5 Flash (native response_schema) when Groq errors or
  keeps returning unparseable JSON.

Every call is validated against a Pydantic schema with exactly one repair
retry before the caller is told it failed. Callers must degrade gracefully
rather than inventing a result — an unavailable verifier yields the SKIPPED
verdict, never a fabricated SUPPORTED.
"""

import json
from enum import StrEnum
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class Tier(StrEnum):
    CLASSIFY = "classify"
    VERIFY = "verify"


class LLMOutputError(RuntimeError):
    """The model never produced output matching the requested schema."""


class LLMClient(Protocol):
    def complete_structured(
        self, *, tier: Tier, system: str, user: str, schema: type[T]
    ) -> T: ...


def _extract_json(text: str) -> str:
    """Salvage a JSON object from a response that wrapped it in prose or fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


class GroqGeminiClient:
    """Groq primary with a Gemini fallback for the verification tier."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._groq = None
        self._gemini = None

    def _groq_client(self):
        if self._groq is None:
            from openai import OpenAI

            self._groq = OpenAI(
                api_key=self.settings.groq_api_key, base_url=self.settings.groq_base_url
            )
        return self._groq

    def _gemini_client(self):
        if self._gemini is None:
            from google import genai

            self._gemini = genai.Client(api_key=self.settings.gemini_api_key)
        return self._gemini

    def _model_for(self, tier: Tier) -> str:
        return self.settings.tier1_model if tier is Tier.CLASSIFY else self.settings.tier2_model

    def _call_groq(self, tier: Tier, system: str, user: str) -> str:
        response = self._groq_client().chat.completions.create(
            model=self._model_for(tier),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    def _call_gemini(self, system: str, user: str, schema: type[T]) -> T:
        response = self._gemini_client().models.generate_content(
            model=self.settings.gemini_fallback_model,
            contents=f"{system}\n\n{user}",
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
                "temperature": 0.0,
            },
        )
        return schema.model_validate_json(_extract_json(response.text))

    def complete_structured(self, *, tier: Tier, system: str, user: str, schema: type[T]) -> T:
        last_error: Exception | None = None
        prompt = user

        for attempt in (1, 2):
            try:
                raw = self._call_groq(tier, system, prompt)
                return schema.model_validate_json(_extract_json(raw))
            except ValidationError as exc:
                last_error = exc
                log.warning("llm_schema_violation", tier=str(tier), attempt=attempt)
                if attempt == 1:
                    # One repair retry, showing the model exactly what broke.
                    prompt = (
                        f"{user}\n\nYour previous response did not match the required schema:\n"
                        f"{exc}\n\nReturn only valid JSON matching the schema."
                    )
            except Exception as exc:
                last_error = exc
                log.warning("llm_call_failed", tier=str(tier), attempt=attempt, error=str(exc))
                break

        if tier is Tier.VERIFY and self.settings.gemini_api_key:
            try:
                log.info("llm_falling_back_to_gemini")
                return self._call_gemini(system, user, schema)
            except Exception as exc:
                last_error = exc
                log.warning("gemini_fallback_failed", error=str(exc))

        raise LLMOutputError(f"{tier} call failed: {last_error}") from last_error


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_mocked:
        from app.services.mocks.mock_llm import MockLLMClient

        return MockLLMClient()
    return GroqGeminiClient()


def json_schema_hint(schema: type[BaseModel]) -> str:
    """Compact schema description to embed in prompts."""
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))
