"""User auth: registration (env-gated), email activation, login/logout/session,
password reset, roles, and the login gate over the whole main app. Uses
`anon_client` and a stubbed email sender -- no real SMTP anywhere.
"""

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.db.models import User, UserToken
from app.db.models.enums import UserRole, UserTokenKind
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration

USER_EMAIL = "user@example.com"
ADMIN_EMAIL = "admin@example.com"
PASSWORD = "password123"


class EmailStub:
    def __init__(self):
        self.messages: list[tuple[str, str, str]] = []  # (to, subject, text)

    def send(self, to: str, subject: str, text: str, html: str) -> None:
        self.messages.append((to, subject, text))


def _token_from_email(text: str) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", text)
    assert match, f"no token in email: {text[:200]}"
    return match.group(1)


@pytest.fixture(autouse=True)
def _clean_user_redis_state():
    """clean_db truncates Postgres only -- user sessions and the per-email
    lockout counter live in Redis and would leak between tests otherwise."""
    import redis

    client = redis.Redis.from_url(get_settings().redis_url)
    for key in client.scan_iter("user_session:*"):
        client.delete(key)
    for key in client.scan_iter("user_login_fail:*"):
        client.delete(key)
    yield
    for key in client.scan_iter("user_session:*"):
        client.delete(key)
    for key in client.scan_iter("user_login_fail:*"):
        client.delete(key)


@pytest.fixture
async def email_stub(anon_client):
    from app.main import app
    from app.services.email_client import get_email_sender

    stub = EmailStub()
    app.dependency_overrides[get_email_sender] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_email_sender, None)


async def _register(client, email: str, settings, *, password: str = PASSWORD) -> str:
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert resp.status_code == 201, resp.text
    return email


async def _activate_from_email(client, stub) -> None:
    text = stub.messages[-1][2]
    resp = await client.post("/api/v1/auth/activate", json={"token": _token_from_email(text)})
    assert resp.status_code == 204, resp.text


@pytest.fixture
async def user_client(anon_client, email_stub, settings, monkeypatch):
    """A registered + activated + logged-in regular user."""
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    return anon_client


@pytest.fixture
async def admin_user_client(anon_client, email_stub, settings, monkeypatch):
    """A registered + activated + logged-in role=admin user."""
    monkeypatch.setattr(settings, "registration_enabled", True)
    monkeypatch.setattr(settings, "admin_emails", [ADMIN_EMAIL])
    await _register(anon_client, ADMIN_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    return anon_client


# -- Registration ----------------------------------------------------------


async def test_register_is_disabled_by_default(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/register", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"]


async def test_register_creates_inactive_user_and_sends_email(
    anon_client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    assert len(email_stub.messages) == 1
    to, subject, text = email_stub.messages[0]
    assert to == USER_EMAIL
    assert "activate" in subject.lower()
    assert "/activate?token=" in text

    user = db_session.query(User).filter(User.email == USER_EMAIL).one()
    assert user.is_active is False
    assert user.role == UserRole.USER


async def test_register_duplicate_email_is_409(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    resp = await anon_client.post(
        "/api/v1/auth/register", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert resp.status_code == 409


async def test_register_email_in_admin_list_becomes_admin(
    anon_client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    monkeypatch.setattr(settings, "admin_emails", [ADMIN_EMAIL])
    await _register(anon_client, ADMIN_EMAIL, settings)
    user = db_session.query(User).filter(User.email == ADMIN_EMAIL).one()
    assert user.role == UserRole.ADMIN


async def test_register_failed_email_send_rolls_back_account(
    anon_client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    email_stub.send = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
    resp = await anon_client.post(
        "/api/v1/auth/register", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert resp.status_code == 502
    assert db_session.query(User).filter(User.email == USER_EMAIL).count() == 0


# -- Activation ------------------------------------------------------------


async def test_activate_activates_and_auto_logs_in(
    anon_client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    assert "cin_user" in anon_client.cookies
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()
    assert user.is_active is True
    assert user.email_verified_at is not None
    assert db_session.query(UserToken).filter(UserToken.kind == UserTokenKind.ACTIVATION).count() == 0


async def test_activate_with_bad_token_is_401(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    resp = await anon_client.post("/api/v1/auth/activate", json={"token": "not-a-real-token"})
    assert resp.status_code == 401


async def test_activate_with_expired_token_is_401(
    anon_client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()
    raw = "expired-token"
    db_session.add(
        UserToken(
            user_id=user.id,
            kind=UserTokenKind.ACTIVATION,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    db_session.commit()
    resp = await anon_client.post("/api/v1/auth/activate", json={"token": raw})
    assert resp.status_code == 401


async def test_resend_activation_sends_new_link(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await anon_client.post(
        "/api/v1/auth/register", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    email_stub.messages.clear()
    resp = await anon_client.post("/api/v1/auth/resend-activation", json={"email": USER_EMAIL})
    assert resp.status_code == 204
    assert len(email_stub.messages) == 1
    assert "/activate?token=" in email_stub.messages[0][2]


async def test_resend_activation_ignores_unknown_email(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/resend-activation", json={"email": "nobody@example.com"}
    )
    assert resp.status_code == 204


async def test_resend_activation_skips_already_active_user(
    anon_client, email_stub, settings, monkeypatch
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await anon_client.post(
        "/api/v1/auth/register", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    await _activate_from_email(anon_client, email_stub)
    email_stub.messages.clear()
    resp = await anon_client.post("/api/v1/auth/resend-activation", json={"email": USER_EMAIL})
    assert resp.status_code == 204
    assert len(email_stub.messages) == 0


# -- Login / logout / session ---------------------------------------------


async def test_login_sets_cookie_and_session_reports_user(
    anon_client, email_stub, settings, monkeypatch
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    await anon_client.post("/api/v1/auth/logout")

    resp = await anon_client.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert resp.status_code == 204
    assert "cin_user" in anon_client.cookies

    session = (await anon_client.get("/api/v1/auth/session")).json()
    assert session == {
        "authenticated": True,
        "email": USER_EMAIL,
        "role": "user",
        "full_name": None,
        "phone": None,
        "address": None,
        "affiliation": None,
        "bio": None,
    }


async def test_login_wrong_password_is_401(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    await anon_client.post("/api/v1/auth/logout")  # clear the activation auto-login cookie
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": "wrong-password"}
    )
    assert resp.status_code == 401
    assert "cin_user" not in anon_client.cookies


async def test_login_unactivated_account_is_403(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert resp.status_code == 403


async def test_login_lockout_after_repeated_failures(anon_client, email_stub, settings, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    for _ in range(10):
        resp = await anon_client.post(
            "/api/v1/auth/login", json={"email": USER_EMAIL, "password": "wrong"}
        )
        assert resp.status_code == 401
    locked = await anon_client.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert locked.status_code == 429


async def test_session_unauthenticated_for_anon(anon_client):
    resp = await anon_client.get("/api/v1/auth/session")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False


async def test_logout_clears_session(user_client):
    resp = await user_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    assert (await user_client.get("/api/v1/auth/session")).json()["authenticated"] is False


# -- Profile ---------------------------------------------------------------


async def test_register_accepts_full_name(anon_client, email_stub, settings, monkeypatch, db_session):
    monkeypatch.setattr(settings, "registration_enabled", True)
    resp = await anon_client.post(
        "/api/v1/auth/register",
        json={"email": USER_EMAIL, "password": PASSWORD, "full_name": "Budi"},
    )
    assert resp.status_code == 201
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()
    assert user.full_name == "Budi"


async def test_update_profile_sets_full_name(user_client, db_session):
    resp = await user_client.patch("/api/v1/auth/me", json={"full_name": "Budi Santoso"})
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Budi Santoso"

    session = (await user_client.get("/api/v1/auth/session")).json()
    assert session["full_name"] == "Budi Santoso"
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()
    assert user.full_name == "Budi Santoso"


async def test_update_profile_clears_whitespace_name(user_client):
    resp = await user_client.patch("/api/v1/auth/me", json={"full_name": "   "})
    assert resp.status_code == 200
    assert resp.json()["full_name"] is None


async def test_update_profile_requires_login(anon_client):
    resp = await anon_client.patch("/api/v1/auth/me", json={"full_name": "Hacker"})
    assert resp.status_code == 401


async def test_register_accepts_profile_fields(
    anon_client, email_stub, settings, monkeypatch, db_session
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    resp = await anon_client.post(
        "/api/v1/auth/register",
        json={
            "email": USER_EMAIL,
            "password": PASSWORD,
            "full_name": "Budi",
            "phone": "0812",
            "address": "Jl. Sudirman",
            "affiliation": "Universitas Indonesia",
            "bio": "Researcher",
        },
    )
    assert resp.status_code == 201
    user = db_session.query(User).filter(User.email == USER_EMAIL).one()
    assert user.phone == "0812"
    assert user.address == "Jl. Sudirman"
    assert user.affiliation == "Universitas Indonesia"
    assert user.bio == "Researcher"


async def test_update_profile_sets_all_fields(user_client):
    resp = await user_client.patch(
        "/api/v1/auth/me",
        json={
            "full_name": "Budi",
            "phone": "0812",
            "address": "Jl. Sudirman",
            "affiliation": "UI",
            "bio": "Researcher",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["phone"] == "0812"
    assert body["affiliation"] == "UI"
    assert body["bio"] == "Researcher"
    assert body["address"] == "Jl. Sudirman"


# -- Password reset --------------------------------------------------------


async def test_forgot_password_sends_link_only_for_active_users(
    anon_client, email_stub, settings, monkeypatch
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    resp = await anon_client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert resp.status_code == 204  # always 204, no enumeration
    assert len(email_stub.messages) == 0

    await _register(anon_client, USER_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    email_stub.messages.clear()
    resp = await anon_client.post(
        "/api/v1/auth/forgot-password", json={"email": USER_EMAIL}
    )
    assert resp.status_code == 204
    assert len(email_stub.messages) == 1
    assert "reset" in email_stub.messages[0][1].lower()
    assert "/reset-password?token=" in email_stub.messages[0][2]


async def test_reset_password_changes_password(
    anon_client, email_stub, settings, monkeypatch
):
    monkeypatch.setattr(settings, "registration_enabled", True)
    await _register(anon_client, USER_EMAIL, settings)
    await _activate_from_email(anon_client, email_stub)
    await anon_client.post("/api/v1/auth/logout")

    await anon_client.post("/api/v1/auth/forgot-password", json={"email": USER_EMAIL})
    reset_text = email_stub.messages[-1][2]
    new_password = "new-password-456"
    resp = await anon_client.post(
        "/api/v1/auth/reset-password",
        json={"token": _token_from_email(reset_text), "new_password": new_password},
    )
    assert resp.status_code == 204

    ok = await anon_client.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": new_password}
    )
    assert ok.status_code == 204
    old = await anon_client.post(
        "/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD}
    )
    assert old.status_code == 401


async def test_reset_password_with_bad_token_is_401(anon_client):
    resp = await anon_client.post(
        "/api/v1/auth/reset-password",
        json={"token": "bogus", "new_password": "new-password-456"},
    )
    assert resp.status_code == 401


# -- Gating: the whole main app requires login -----------------------------


async def test_main_app_endpoints_require_login(anon_client):
    for method, url in [
        ("get", "/api/v1/drafts"),
        ("post", "/api/v1/drafts/upload"),
        ("get", f"/api/v1/exports/{uuid.uuid4()}/download"),
    ]:
        resp = await getattr(anon_client, method)(url)
        assert resp.status_code == 401, (method, url, resp.status_code)


async def test_user_can_access_main_app(user_client):
    resp = await user_client.get("/api/v1/drafts")
    assert resp.status_code == 200


async def test_regular_user_cannot_import_library(user_client):
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    resp = await user_client.post(
        "/api/v1/library/import", files={"file": ("sample_dataset.xlsx", data)}
    )
    assert resp.status_code == 401


async def test_admin_user_can_import_library(admin_user_client):
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    resp = await admin_user_client.post(
        "/api/v1/library/import", files={"file": ("sample_dataset.xlsx", data)}
    )
    assert resp.status_code == 201


async def test_cross_site_post_with_valid_user_cookie_is_rejected(user_client):
    resp = await user_client.post(
        "/api/v1/drafts/upload", headers={"sec-fetch-site": "cross-site"}
    )
    assert resp.status_code == 403


# -- Config fail-fast ------------------------------------------------------


def test_registration_requires_smtp_host(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("USE_MOCK_PROVIDERS", "true")
    with pytest.raises(ValueError, match="SMTP_HOST"):
        Settings(registration_enabled=True, smtp_host="")


def test_production_requires_non_localhost_public_url(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("USE_MOCK_PROVIDERS", "true")
    with pytest.raises(ValueError, match="APP_PUBLIC_URL"):
        Settings(
            environment="production",
            registration_enabled=True,
            smtp_host="smtp.x.com",
        )
