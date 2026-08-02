"""Every Groq call goes through complete_structured with
response_format={"type": "json_object"} (llm_client.py::_call_groq),
unconditionally, regardless of tier. Groq rejects that with a 400 unless
the word "json" appears somewhere in the messages -- a constraint the
mock LLM client never enforces, so a missing "json" only surfaces
against the real API. This test is the guard the mock can't provide:
catches a system prompt missing the word before it ships, the way the
SDG classification prompt did.
"""

import pytest

from app.services.claim_detection_service import CLASSIFY_SYSTEM
from app.services.sdg_classification_service import SDG_SYSTEM
from app.services.verification_service import VERIFY_SYSTEM

pytestmark = pytest.mark.parametrize(
    "system_prompt",
    [CLASSIFY_SYSTEM, SDG_SYSTEM, VERIFY_SYSTEM],
    ids=["claim_detection", "sdg_classification", "verification"],
)


def test_system_prompt_mentions_json(system_prompt):
    assert "json" in system_prompt.lower()
