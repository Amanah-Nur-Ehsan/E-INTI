"""Admin session auth: login/logout, the public/admin split on the
library router, and CSRF rejection. Uses `anon_client` (no pre-login)
throughout -- `client` is pre-authenticated by conftest.py for every
other test file's convenience, which is exactly what must NOT be true
here.
"""

import pytest

from app.core.config import get_settings
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_admin_redis_state():
    """clean_db only truncates Postgres -- the login-lockout counter and
    any session keys live in Redis and would otherwise leak between
    tests (e.g. the lockout test tripping the counter for every test
    that runs after it in the same session).
    """
    import redis

    client = redis.Redis.from_url(get_settings().redis_url)
    client.delete("admin_login_fail")
    for key in client.scan_iter("admin_session:*"):
        client.delete(key)
    yield
    client.delete("admin_login_fail")
    for key in client.scan_iter("admin_session:*"):
        client.delete(key)


async def test_unauthenticated_import_is_rejected(anon_client):
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    resp = await anon_client.post(
        "/api/v1/library/import", files={"file": ("sample_dataset.xlsx", data)}
    )
    assert resp.status_code == 401


async def test_unauthenticated_refresh_is_rejected(anon_client):
    resp = await anon_client.post("/api/v1/library/refresh")
    assert resp.status_code == 401


async def test_unauthenticated_list_references_is_rejected(anon_client):
    resp = await anon_client.get("/api/v1/library")
    assert resp.status_code == 401


async def test_status_stays_public_without_login(anon_client):
    """The main page polls this without ever logging in -- it must never
    require the admin gate, unlike every other /library/* route.
    """
    resp = await anon_client.get("/api/v1/library/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body and "embed_pending" in body


async def test_login_with_wrong_password_is_rejected(anon_client):
    resp = await anon_client.post("/api/v1/admin/login", json={"password": "not-the-password"})
    assert resp.status_code == 401
    assert "cin_admin" not in resp.cookies


async def test_login_with_correct_password_sets_cookie(anon_client):
    settings = get_settings()
    resp = await anon_client.post(
        "/api/v1/admin/login", json={"password": settings.admin_password_or_default}
    )
    assert resp.status_code == 204
    assert "cin_admin" in anon_client.cookies
    set_cookie = resp.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


async def test_authenticated_import_succeeds(client):
    """`client` is the pre-logged-in fixture -- confirms the happy path
    actually works end to end, not just that the gate rejects anonymous
    requests.
    """
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    resp = await client.post(
        "/api/v1/library/import", files={"file": ("sample_dataset.xlsx", data)}
    )
    assert resp.status_code == 201


async def test_logout_then_request_is_rejected(client):
    resp = await client.post("/api/v1/admin/logout")
    assert resp.status_code == 204

    resp = await client.post("/api/v1/library/refresh")
    assert resp.status_code == 401


async def test_session_endpoint_reports_authenticated(client):
    resp = await client.get("/api/v1/admin/session")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True}


async def test_session_endpoint_401s_when_not_logged_in(anon_client):
    resp = await anon_client.get("/api/v1/admin/session")
    assert resp.status_code == 401


async def test_wrong_password_lockout_after_repeated_failures(anon_client):
    for _ in range(20):
        resp = await anon_client.post("/api/v1/admin/login", json={"password": "wrong"})
        assert resp.status_code == 401

    locked = await anon_client.post("/api/v1/admin/login", json={"password": "wrong"})
    assert locked.status_code == 429

    # Even the correct password is locked out for the rest of the window.
    settings = get_settings()
    still_locked = await anon_client.post(
        "/api/v1/admin/login", json={"password": settings.admin_password_or_default}
    )
    assert still_locked.status_code == 429


async def test_cross_site_post_with_valid_cookie_is_rejected(client):
    """A valid session cookie alone isn't enough for a state-changing
    request that looks like it came from another origin -- the
    Sec-Fetch-Site/Origin check in require_admin is what catches a
    forged cross-site POST that SameSite=Lax's browser-side enforcement
    wouldn't even let happen in practice; this proves the server-side
    defence-in-depth layer works independently of the browser.
    """
    resp = await client.post(
        "/api/v1/library/refresh",
        headers={"sec-fetch-site": "cross-site"},
    )
    assert resp.status_code == 403


async def test_cross_site_get_is_still_allowed(client):
    """Safe methods are never subject to the Origin check -- a top-level
    GET navigation (e.g. the missing-abstracts-template download link)
    must keep working regardless of Sec-Fetch-Site.
    """
    resp = await client.get(
        "/api/v1/library/missing-abstracts-by-year",
        headers={"sec-fetch-site": "cross-site"},
    )
    assert resp.status_code == 200


def test_production_without_admin_password_fails_fast(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("USE_MOCK_PROVIDERS", "true")
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        Settings(environment="production", admin_password="")


def test_production_with_short_admin_password_fails_fast(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("USE_MOCK_PROVIDERS", "true")
    with pytest.raises(ValueError, match="at least 12 characters"):
        Settings(environment="production", admin_password="short")
