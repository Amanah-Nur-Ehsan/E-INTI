import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.security import require_api_key


async def test_disabled_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "")
    await require_api_key(x_api_key=None)  # must not raise


async def test_rejects_missing_key_when_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "secret123")
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key=None)
    assert exc.value.status_code == 401


async def test_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "secret123")
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key="wrong")
    assert exc.value.status_code == 401


async def test_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "secret123")
    await require_api_key(x_api_key="secret123")  # must not raise
