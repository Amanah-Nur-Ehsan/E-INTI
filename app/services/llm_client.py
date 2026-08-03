"""Provider-agnostic structured-output LLM client.

Two tiers, per the locked routing decision:

* Tier.CLASSIFY — high volume, trivial JSON: DeepSeek deepseek-chat.
* Tier.VERIFY   — a bounded judgment call over one abstract: DeepSeek
  deepseek-chat, falling back to Gemini 2.5 Flash (native response_schema)
  when DeepSeek errors or keeps returning unparseable JSON.

(Originally Groq; swapped to DeepSeek because Groq's free-tier *token*-per-
minute ceiling -- not request volume, which had headroom throughout -- was
the actual bottleneck on real papers, forcing 45-60s stalls multiple times
per run. DeepSeek's OpenAI-compatible API meant this was a config +
naming change, not a rewrite.)

Every call is validated against a Pydantic schema with exactly one repair
retry before the caller is told it failed. Callers must degrade gracefully
rather than inventing a result — an unavailable verifier yields the SKIPPED
verdict, never a fabricated SUPPORTED.

Transport concerns (429s, timeouts, transient 5xx) are handled one layer
below `complete_structured`, in `_call_primary_with_retry`, so a rate limit
can never consume the JSON-repair retry above it -- those are two
independent kinds of failure and mixing them was the original bug: a 429
landed in a bare `except Exception` that `break`s after one HTTP attempt.
"""

import json
import re
import time
from enum import StrEnum
from functools import lru_cache
from typing import Protocol, TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

#: Status codes worth retrying. Anything else (400/401/404/422...) is our
#: bug, not a transient condition, and burning attempts on it just delays
#: the real error.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class Tier(StrEnum):
    CLASSIFY = "classify"
    VERIFY = "verify"


class LLMOutputError(RuntimeError):
    """The model never produced output matching the requested schema."""


class LLMRateLimited(RuntimeError):
    """The primary provider kept failing (429 or transient 5xx/timeout)
    after every retry."""


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


_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")
_DURATION_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def _parse_duration_string(value: str | None) -> float | None:
    """Some providers (Groq was the original case) send rate-limit-reset
    headers as duration strings like '7.66s', '2m59.56s', or '120ms'
    rather than plain seconds. Sum every (number, unit) pair found; kept
    as a fallback parser for _retry_after_seconds regardless of which
    provider is primary.
    """
    if not value:
        return None
    parts = _DURATION_RE.findall(value)
    if not parts:
        return None
    return sum(float(n) * _DURATION_UNITS[u] for n, u in parts)


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _retry_after_seconds(exc: APIStatusError) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return _parse_duration_string(raw)


class DeepSeekGeminiClient:
    """DeepSeek primary with a Gemini fallback for both tiers."""

    #: Below this many requests or tokens remaining, sleep until the
    #: window resets rather than wait to be told via a 429. DeepSeek does
    #: not send the rate-limit-remaining headers Groq did, so in practice
    #: this never triggers for DeepSeek today -- it's provider-agnostic
    #: and activates automatically if DeepSeek (or a future primary) ever
    #: starts sending them.
    _RATE_LIMIT_FLOOR_REQUESTS = 2
    _RATE_LIMIT_FLOOR_TOKENS = 2000

    def __init__(self) -> None:
        self.settings = get_settings()
        self._primary = None
        self._gemini = None
        #: When the next request is allowed to *start*. Scheduling on starts
        #: rather than completions is what makes the pacing floor mean what
        #: it says -- see _pace().
        self._next_request_at = 0.0

    def _primary_client(self):
        if self._primary is None:
            from openai import OpenAI

            self._primary = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                max_retries=0,  # we own retries -- the SDK default would fight our loop
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._primary

    def _gemini_client(self):
        if self._gemini is None:
            from google import genai

            self._gemini = genai.Client(api_key=self.settings.gemini_api_key)
        return self._gemini

    def _model_for(self, tier: Tier) -> str:
        return self.settings.tier1_model if tier is Tier.CLASSIFY else self.settings.tier2_model

    def _pace(self) -> None:
        """Block until this request's scheduled start, then book the next.

        Start-to-start, not end-to-start: stamping the clock after a
        response makes the real gap `latency + floor`, which quietly
        halves effective throughput once any real model latency is added
        on top. Scheduling from the start means the floor is the floor
        regardless of how slow any one call is.
        """
        now = time.monotonic()
        if now < self._next_request_at:
            time.sleep(self._next_request_at - now)
            now = self._next_request_at
        self._next_request_at = now + self.settings.llm_min_seconds_between_requests

    def _observe_rate_limit(self, headers) -> None:
        """Mirrors scopus_service._observe_rate_limit: sleep proactively
        when the provider's own quota headers say we're close to the edge,
        rather than waiting for the 429 that would otherwise arrive next
        call. A no-op whenever those headers are absent.
        """
        requests_left = _to_int(headers.get("x-ratelimit-remaining-requests"))
        tokens_left = _to_int(headers.get("x-ratelimit-remaining-tokens"))

        wait: float | None = None
        if requests_left is not None and requests_left <= self._RATE_LIMIT_FLOOR_REQUESTS:
            wait = _parse_duration_string(headers.get("x-ratelimit-reset-requests"))
        elif tokens_left is not None and tokens_left <= self._RATE_LIMIT_FLOOR_TOKENS:
            wait = _parse_duration_string(headers.get("x-ratelimit-reset-tokens"))

        if wait:
            wait = min(wait, self.settings.llm_max_backoff_seconds)
            log.warning(
                "llm_quota_low",
                requests_left=requests_left,
                tokens_left=tokens_left,
                sleeping_for=round(wait, 1),
            )
            time.sleep(wait)

    def _call_primary(self, tier: Tier, system: str, user: str) -> str:
        self._pace()
        raw = self._primary_client().chat.completions.with_raw_response.create(
            model=self._model_for(tier),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        self._observe_rate_limit(raw.headers)
        return raw.parse().choices[0].message.content or ""

    def _call_primary_with_retry(self, tier: Tier, system: str, user: str) -> str:
        """The transport retry loop: 429s, timeouts, and transient 5xx are
        all handled here, honoring Retry-After where the provider sends one
        and backing off exponentially otherwise. A 4xx that isn't 429 is
        our bug -- it's re-raised immediately rather than retried.
        """
        delay = self.settings.llm_retry_base_seconds
        last: Exception | None = None

        for attempt in range(1, self.settings.llm_max_attempts + 1):
            try:
                return self._call_primary(tier, system, user)
            except RateLimitError as exc:
                wait = _retry_after_seconds(exc) or delay
                wait = min(wait, self.settings.llm_max_backoff_seconds)
                log.warning(
                    "llm_rate_limited", tier=str(tier), attempt=attempt, sleeping_for=round(wait, 1)
                )
                time.sleep(wait)
                delay = min(delay * 2, self.settings.llm_max_backoff_seconds)
                last = exc
            except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
                log.warning("llm_transport_error", tier=str(tier), attempt=attempt, error=str(exc))
                time.sleep(delay)
                delay = min(delay * 2, self.settings.llm_max_backoff_seconds)
                last = exc
            except APIStatusError as exc:
                if exc.status_code not in _RETRYABLE_STATUS:
                    raise
                log.warning(
                    "llm_retryable_status",
                    tier=str(tier),
                    attempt=attempt,
                    status=exc.status_code,
                )
                time.sleep(delay)
                delay = min(delay * 2, self.settings.llm_max_backoff_seconds)
                last = exc

        raise LLMRateLimited(
            f"Primary LLM exhausted {self.settings.llm_max_attempts} attempts for {tier}"
        ) from last

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
                raw = self._call_primary_with_retry(tier, system, prompt)
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
            except LLMRateLimited as exc:
                # A rate limit cannot be fixed by re-prompting -- go straight
                # to the fallback rather than spending the repair attempt.
                last_error = exc
                break
            except Exception as exc:
                last_error = exc
                log.warning("llm_call_failed", tier=str(tier), attempt=attempt, error=str(exc))
                break

        if self.settings.gemini_api_key:
            try:
                log.info("llm_falling_back_to_gemini", tier=str(tier))
                return self._call_gemini(system, user, schema)
            except Exception as exc:
                last_error = exc
                log.warning("gemini_fallback_failed", tier=str(tier), error=str(exc))

        raise LLMOutputError(f"{tier} call failed: {last_error}") from last_error


@lru_cache
def get_llm_client() -> LLMClient:
    """Cached so `_next_request_at` (the pacing state) persists across the
    many calls one analysis run makes -- a fresh client per call would
    reset pacing every time and make it a no-op. Tests that toggle
    settings must call `get_llm_client.cache_clear()` alongside
    `get_settings.cache_clear()`.
    """
    settings = get_settings()
    if settings.llm_mocked:
        from app.services.mocks.mock_llm import MockLLMClient

        return MockLLMClient()
    return DeepSeekGeminiClient()


def json_schema_hint(schema: type[BaseModel]) -> str:
    """Compact schema description to embed in prompts."""
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))
