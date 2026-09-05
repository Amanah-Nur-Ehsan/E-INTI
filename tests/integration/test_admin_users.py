"""Admin user management: list, promote/demote, activate/deactivate, reset
password, delete — plus the guardrails (no self-modification, no removing
the last active admin).

`client` is the legacy shared-password admin: its cin_admin cookie is
independent of the cin_user cookie, so a single client can hold both an
admin session and a separate regular-user session for the same test.
"""

import re
import uuid

import pytest

from app.core.config import get_settings
from app.db.models import User

pytestmark = pytest.mark.integration

ADMIN_EMAIL = "admin@example.com"
USER_EMAIL = "user@example.com"
PASSWORD = "password123"


class EmailStub:
    def __init__(self):
        self.messages: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str, html: str) -> None:
        self.messages.append((to, subject, text))


@pytest.fixture(autouse=True)
def _clean_user_redis_state():
    import redis

    client = redis.Redis.from_url(get_settings().redis_url)
    for key in client.scan_iter("user_session:*"):
        client.delete(key)
    for key in client.scan_iter("user_login_fail:*"):
        client.delete(key)
    yield
    for key in client.scan_iter("user_session:*"):
        client.delete(key)


@pytest.fixture
async def email_stub(anon_client):
    from app.main import app
    from app.services.email_client import get_email_sender

    stub = EmailStub()
    app.dependency_overrides[get_email_sender] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_email_sender, None)


async def _register(client, email: str, settings) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert resp.status_code == 201, resp.text


async def _activate(client, stub) -> None:
    text = stub.messages[-1][2]
    token = re.search(r"token=([A-Za-z0-9_\-]+)", text).group(1)
    resp = await client.post("/api/v1/auth/activate", json={"token": token})
    assert resp.status_code == 204


async def _make_user(client, email_stub, settings, email: str = USER_EMAIL) -> None:
    """Register + activate a user (auto-logs them in on the client)."""
    await _register(client, email, settings)
    await _activate(client, email_stub)


async def _fresh_client():
    """A clean client with its own cookie jar (no admin cookie)."""
    import httpx

    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def user_client(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _make_user(anon_client, email_stub, settings, USER_EMAIL)
    return anon_client


@pytest.fixture
async def admin_user_client(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    monkeypatch.setattr(settings, "admin_emails", ADMIN_EMAIL)
    await _make_user(anon_client, email_stub, settings, ADMIN_EMAIL)
    return anon_client


# -- Listing ---------------------------------------------------------------


async def test_list_users_requires_admin(user_client):
    resp = await user_client.get("/api/v1/admin/users")
    assert resp.status_code == 401


async def test_list_users_as_admin(admin_user_client):
    resp = await admin_user_client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    assert any(u["email"] == ADMIN_EMAIL for u in resp.json())


# -- Role / active state ---------------------------------------------------


async def test_admin_promotes_user(client, email_stub, settings, monkeypatch, db_session):
    monkeypatch.setattr(settings, "registration_enabled", True)
    user_http = await _fresh_client()
    await _make_user(user_http, email_stub, settings, USER_EMAIL)
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()

    resp = await client.patch(f"/api/v1/admin/users/{user.id}", json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
    await user_http.aclose()


async def test_admin_edits_user_name_and_email(
    client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    user_http = await _fresh_client()
    await _make_user(user_http, email_stub, settings, USER_EMAIL)
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()

    resp = await client.patch(
        f"/api/v1/admin/users/{user.id}",
        json={"full_name": "Rini", "email": "rini@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Rini"
    assert resp.json()["email"] == "rini@example.com"

    db_session.expire_all()
    renamed = db_session.query(User).filter(User.email == "rini@example.com").one()
    assert renamed.full_name == "Rini"
    await user_http.aclose()


async def test_admin_cannot_use_duplicate_email(
    client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    user1 = await _fresh_client()
    await _make_user(user1, email_stub, settings, USER_EMAIL)
    user2 = await _fresh_client()
    await _make_user(user2, email_stub, settings, "other@example.com")

    target = db_session.query(User).filter(User.email == USER_EMAIL).one()
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}", json={"email": "other@example.com"}
    )
    assert resp.status_code == 409
    await user1.aclose()
    await user2.aclose()


async def test_admin_cannot_change_own_role(admin_user_client, db_session):
    me = db_session.query(User).filter(User.email == ADMIN_EMAIL).one()
    resp = await admin_user_client.patch(f"/api/v1/admin/users/{me.id}", json={"role": "user"})
    assert resp.status_code == 400
    assert "own role" in resp.json()["detail"]


async def test_admin_cannot_deactivate_self(admin_user_client, db_session):
    me = db_session.query(User).filter(User.email == ADMIN_EMAIL).one()
    resp = await admin_user_client.patch(f"/api/v1/admin/users/{me.id}", json={"is_active": False})
    assert resp.status_code == 400


async def test_admin_cannot_delete_self(admin_user_client, db_session):
    me = db_session.query(User).filter(User.email == ADMIN_EMAIL).one()
    resp = await admin_user_client.delete(f"/api/v1/admin/users/{me.id}")
    assert resp.status_code == 400


async def test_admin_deactivate_revokes_user_sessions(
    client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    user_http = await _fresh_client()
    await _make_user(user_http, email_stub, settings, USER_EMAIL)
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()
    assert (await user_http.get("/api/v1/auth/session")).json()["authenticated"] is True

    resp = await client.patch(f"/api/v1/admin/users/{user.id}", json={"is_active": False})
    assert resp.status_code == 200

    # The deactivated user's session is gone (fresh client has no admin cookie).
    assert (await user_http.get("/api/v1/auth/session")).json()["authenticated"] is False
    await user_http.aclose()


# -- Password reset --------------------------------------------------------


async def test_admin_resets_user_password(
    client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    user_http = await _fresh_client()
    await _make_user(user_http, email_stub, settings, USER_EMAIL)
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()

    resp = await client.post(
        f"/api/v1/admin/users/{user.id}/reset-password", json={"new_password": "reset-pass-1"}
    )
    assert resp.status_code == 204

    old = await user_http.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert old.status_code == 401
    new = await user_http.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": "reset-pass-1"}
    )
    assert new.status_code == 204
    await user_http.aclose()


# -- Deletion --------------------------------------------------------------


async def test_admin_deletes_user(client, email_stub, settings, monkeypatch, db_session):
    monkeypatch.setattr(settings, "registration_enabled", True)
    user_http = await _fresh_client()
    await _make_user(user_http, email_stub, settings, USER_EMAIL)
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()

    resp = await client.delete(f"/api/v1/admin/users/{user.id}")
    assert resp.status_code == 204
    assert db_session.query(User).filter(User.email == USER_EMAIL).count() == 0

    login = await user_http.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert login.status_code == 401
    await user_http.aclose()


async def test_admin_patch_unknown_user_404(admin_user_client):
    resp = await admin_user_client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}", json={"is_active": False}
    )
    assert resp.status_code == 404


# -- Overview dashboard ----------------------------------------------------


async def test_admin_overview_requires_admin(user_client):
    resp = await user_client.get("/api/v1/admin/overview")
    assert resp.status_code == 401


async def test_admin_overview_counts(admin_user_client):
    resp = await admin_user_client.get("/api/v1/admin/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["users"] == {"total": 1, "active": 1, "admins": 1}
    assert "total" in body["library"]
    assert body["app"]["environment"] == "development"
    assert body["app"]["active_analyses"] == 0
