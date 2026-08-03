"""The transport-retry layer added to fix the Groq 429: pacing, backoff,
Retry-After handling, and -- the actual bug fix -- that a rate limit can
no longer consume the JSON-repair retry above it.
"""

import httpx
import pytest
from openai import APIStatusError, RateLimitError
from pydantic import BaseModel

from app.services.llm_client import (
    GroqGeminiClient,
    LLMOutputError,
    LLMRateLimited,
    Tier,
    _parse_groq_duration,
    _retry_after_seconds,
)


class _Schema(BaseModel):
    value: str


def _rate_limit_error(headers: dict | None = None) -> RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, headers=headers or {}, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def _status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return APIStatusError("status error", response=response, body=None)


class _FakeClient(GroqGeminiClient):
    """Overrides only the transport call, so the retry/pacing logic runs for real."""

    def __init__(self, settings, responses):
        self.settings = settings
        self._groq = None
        self._gemini = None
        self._next_request_at = 0.0
        self._responses = list(responses)
        self.calls = 0
        self.sleeps: list[float] = []

    def _call_groq(self, tier, system, user):  # noqa: ARG002
        self.calls += 1
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _pace(self):  # skip real sleeping for the pacing floor in tests
        return


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("7.66s", pytest.approx(7.66)),
        ("2m59.56s", pytest.approx(179.56)),
        ("120ms", pytest.approx(0.12)),
        ("1h", pytest.approx(3600.0)),
        (None, None),
        ("", None),
        ("garbage", None),
    ],
)
def test_parse_groq_duration(raw, expected):
    assert _parse_groq_duration(raw) == expected


def test_retry_after_seconds_reads_numeric_header():
    exc = _rate_limit_error(headers={"retry-after": "12"})
    assert _retry_after_seconds(exc) == 12.0


def test_retry_after_seconds_falls_back_to_duration_format():
    exc = _rate_limit_error(headers={"retry-after": "2m59.56s"})
    assert _retry_after_seconds(exc) == pytest.approx(179.56)


def test_retry_after_seconds_none_when_absent():
    exc = _rate_limit_error(headers={})
    assert _retry_after_seconds(exc) is None


def test_transport_retry_recovers_after_two_rate_limits(monkeypatch, settings):
    monkeypatch.setattr(settings, "llm_max_attempts", 5)
    monkeypatch.setattr(settings, "llm_retry_base_seconds", 0.01)
    monkeypatch.setattr(settings, "llm_max_backoff_seconds", 0.01)

    sleeps: list[float] = []
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda s: sleeps.append(s))

    client = _FakeClient(
        settings,
        [_rate_limit_error(), _rate_limit_error(), '{"value": "ok"}'],
    )
    result = client._call_groq_with_retry(Tier.VERIFY, "sys", "user")

    assert result == '{"value": "ok"}'
    assert client.calls == 3
    assert len(sleeps) == 2


def test_transport_retry_raises_llm_rate_limited_after_exhausting_attempts(monkeypatch, settings):
    monkeypatch.setattr(settings, "llm_max_attempts", 3)
    monkeypatch.setattr(settings, "llm_retry_base_seconds", 0.01)
    monkeypatch.setattr(settings, "llm_max_backoff_seconds", 0.01)
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda s: None)

    client = _FakeClient(settings, [_rate_limit_error()] * 3)
    with pytest.raises(LLMRateLimited):
        client._call_groq_with_retry(Tier.CLASSIFY, "sys", "user")
    assert client.calls == 3


def test_non_retryable_status_error_raised_immediately(monkeypatch, settings):
    monkeypatch.setattr(settings, "llm_max_attempts", 5)
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda s: None)

    client = _FakeClient(settings, [_status_error(401)])
    with pytest.raises(APIStatusError) as exc_info:
        client._call_groq_with_retry(Tier.CLASSIFY, "sys", "user")
    assert exc_info.value.status_code == 401
    assert client.calls == 1  # no retry burned on a 4xx that isn't 429


def test_a_rate_limit_does_not_consume_the_json_repair_attempt(monkeypatch, settings):
    """The actual bug: complete_structured's 2-iteration loop is a JSON-repair
    retry. Before the fix, a 429 landed in a bare `except Exception` that
    broke out after one HTTP attempt -- the repair loop never got a chance
    to run, and Gemini fallback was VERIFY-only so CLASSIFY calls just failed.
    After the fix, transport retries happen entirely inside
    _call_groq_with_retry, so complete_structured only ever sees a clean
    success or a exhausted-retries LLMRateLimited -- never a mid-repair 429.
    """
    monkeypatch.setattr(settings, "llm_max_attempts", 2)
    monkeypatch.setattr(settings, "llm_retry_base_seconds", 0.01)
    monkeypatch.setattr(settings, "llm_max_backoff_seconds", 0.01)
    monkeypatch.setattr(settings, "gemini_api_key", "")  # force the failure to surface, not fall back
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda s: None)

    # Both attempts inside _call_groq_with_retry 429 -- exhausted there,
    # never reaching complete_structured's JSON-repair prompt logic at all.
    client = _FakeClient(settings, [_rate_limit_error(), _rate_limit_error()])
    with pytest.raises(LLMOutputError):
        client.complete_structured(tier=Tier.CLASSIFY, system="sys", user="user", schema=_Schema)
    assert client.calls == 2  # both consumed by the transport loop, not a repair prompt


def test_classify_tier_now_falls_back_to_gemini_on_exhaustion(monkeypatch, settings):
    """Tier.CLASSIFY previously had no fallback at all; a 429 there silently
    dropped a whole batch of sentences. It must now use Gemini too.
    """
    monkeypatch.setattr(settings, "llm_max_attempts", 1)
    monkeypatch.setattr(settings, "gemini_api_key", "fake-key")
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda s: None)

    client = _FakeClient(settings, [_rate_limit_error()])
    monkeypatch.setattr(client, "_call_gemini", lambda system, user, schema: _Schema(value="from-gemini"))

    result = client.complete_structured(tier=Tier.CLASSIFY, system="sys", user="user", schema=_Schema)
    assert result.value == "from-gemini"


class _PacingClient(GroqGeminiClient):
    """Exercises _pace() alone against a fake clock."""

    def __init__(self, settings):
        self.settings = settings
        self._groq = None
        self._gemini = None
        self._next_request_at = 0.0


def test_pacing_is_start_to_start_not_end_to_start(monkeypatch, settings):
    """The original bug: the clock was stamped *after* the response, so the
    real gap between call starts was `latency + floor` rather than `floor`.
    With a 2.1s floor and 1.5s of model latency that yielded ~17 RPM from a
    setting chosen to deliver ~28.

    Here the first call starts at t=0 and takes 1.5s. The second call must
    then wait only the 0.6s remaining in its 2.1s window -- not a further
    full 2.1s.
    """
    monkeypatch.setattr(settings, "llm_min_seconds_between_requests", 2.1)

    now = 0.0
    sleeps: list[float] = []
    monkeypatch.setattr("app.services.llm_client.time.monotonic", lambda: now)
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda s: sleeps.append(s))

    client = _PacingClient(settings)

    client._pace()  # first call: nothing scheduled yet, so no wait
    assert sleeps == []
    assert client._next_request_at == pytest.approx(2.1)

    now = 1.5  # the call took 1.5s to come back
    client._pace()

    assert sleeps == [pytest.approx(0.6)]  # not 2.1 -- the window is measured from the start
    assert client._next_request_at == pytest.approx(4.2)


def test_pacing_does_not_sleep_when_the_window_already_elapsed(monkeypatch, settings):
    """A call slower than the floor should not then be penalised further."""
    monkeypatch.setattr(settings, "llm_min_seconds_between_requests", 2.1)

    now = 0.0
    sleeps: list[float] = []
    monkeypatch.setattr("app.services.llm_client.time.monotonic", lambda: now)
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda s: sleeps.append(s))

    client = _PacingClient(settings)
    client._pace()

    now = 9.0  # a very slow call, well past the 2.1s window
    client._pace()

    assert sleeps == []
    assert client._next_request_at == pytest.approx(11.1)
