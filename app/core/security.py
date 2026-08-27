"""Admin authentication: one shared password, exchanged for a server-side
session held in Redis and represented to the browser as an opaque,
HttpOnly cookie.

There is no per-user model -- "admin" means anyone who knows the one
password (`Settings.admin_password`), which is deliberate: this app has
exactly one operator role (upload the INTI dataset, fill abstracts), and
the main app (upload a paper, run analysis, download the result) stays
fully open to everyone regardless of this gate. See
`app/api/routes/admin.py` for the login/logout/session endpoints and
`app/api/routes/references.py` for which library routes this protects.

Session storage is Redis (already in the stack), not a signed cookie:
that gives real logout and revocation, and storing the SHA-256 of the
token rather than the token itself means a Redis dump is not a set of
live credentials.

CSRF: the cookie is `SameSite=Lax`, which already stops it being sent on
a cross-site POST/PUT/DELETE in every current browser -- the Origin/
Sec-Fetch-Site check below is defence in depth, not the primary
mechanism. Lax still attaches the cookie to a top-level GET navigation,
which is exactly what the "download the missing-abstracts template"
`<a href download>` link needs; that is why this is cookie auth and not
a header scheme (a bare href cannot carry a custom header at all).
"""

import base64
import hashlib
import hmac
import secrets

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, Response, status

from app.core.config import get_settings

ADMIN_COOKIE_NAME = "cin_admin"
USER_COOKIE_NAME = "cin_user"

_SESSION_KEY_PREFIX = "admin_session:"
_LOGIN_FAIL_KEY = "admin_login_fail"
#: Global, not per-IP: behind a reverse proxy request.client.host is
#: usually the proxy's own address unless uvicorn is run with
#: --proxy-headers and a trusted --forwarded-allow-ips, so a per-IP limit
#: would either be wrong (one shared bucket for every real client) or
#: require deployment-specific trust configuration this app doesn't need.
#: One admin, one shared password: a global lockout is the right shape.
_LOGIN_FAIL_WINDOW_SECONDS = 900
_LOGIN_FAIL_MAX_ATTEMPTS = 20

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url)
    return _redis


def _session_key(token: str) -> str:
    return _SESSION_KEY_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


def check_password(candidate: str) -> bool:
    expected = get_settings().admin_password_or_default
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


async def is_login_locked_out() -> bool:
    count = await _client().get(_LOGIN_FAIL_KEY)
    return count is not None and int(count) >= _LOGIN_FAIL_MAX_ATTEMPTS


async def record_login_failure() -> None:
    client = _client()
    count = await client.incr(_LOGIN_FAIL_KEY)
    if count == 1:
        await client.expire(_LOGIN_FAIL_KEY, _LOGIN_FAIL_WINDOW_SECONDS)


async def reset_login_failures() -> None:
    await _client().delete(_LOGIN_FAIL_KEY)


async def create_admin_session(response: Response) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    await _client().set(_session_key(token), "1", ex=settings.admin_session_ttl_seconds)
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        max_age=settings.admin_session_ttl_seconds,
        httponly=True,
        secure=settings.resolved_admin_cookie_secure,
        samesite="lax",
        path="/",
    )


async def destroy_admin_session(request: Request, response: Response) -> None:
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if token:
        await _client().delete(_session_key(token))
    response.delete_cookie(ADMIN_COOKIE_NAME, path="/")


async def _session_exists(token: str) -> bool:
    return await _client().exists(_session_key(token)) > 0


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SAFE_FETCH_SITES = frozenset({"same-origin", "none"})


def _same_origin_request(request: Request) -> bool:
    """Defence-in-depth CSRF check for state-changing requests.

    `Sec-Fetch-Site` is sent by every current browser and is authoritative
    when present. It's absent only for old browsers or non-fetch clients
    (e.g. curl), so fall back to comparing the `Origin` header's host
    against `Host` -- still correct, just not tamper-proof against a
    client that fabricates both headers, which a CSRF attack (a *browser*
    following a cross-site link/form) cannot do.
    """
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None:
        return fetch_site in _SAFE_FETCH_SITES

    origin = request.headers.get("origin")
    if origin is None:
        # No Origin and no Sec-Fetch-Site: same-origin browser requests
        # for simple methods sometimes omit Origin, but state-changing
        # cross-site requests from a browser always carry one. Missing
        # entirely is ambiguous enough to just allow -- SameSite=Lax is
        # still the primary defence and already blocks the real attack.
        return True

    from urllib.parse import urlparse

    origin_host = urlparse(origin).netloc
    return origin_host == request.headers.get("host")


# --- User password hashing (stdlib PBKDF2-HMAC-SHA256; no new deps) -------

_PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash a password, storing scheme$iterations$salt_b64$hash_b64 so the
    hash can be re-derived without any external secret."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return (
        f"pbkdf2_sha256${_PBKDF2_ITERATIONS}"
        f"${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check against a hash_password() output. Fails closed on
    any malformed stored value."""
    try:
        scheme, iterations, salt_b64, hash_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(dk, expected)


# --- User sessions (same Redis opaque-cookie pattern as admin) ------------

_USER_SESSION_KEY_PREFIX = "user_session:"
_USER_LOGIN_FAIL_PREFIX = "user_login_fail:"
_USER_LOGIN_FAIL_MAX_ATTEMPTS = 10
_USER_LOGIN_FAIL_WINDOW_SECONDS = 900


def _user_session_key(token: str) -> str:
    return _USER_SESSION_KEY_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_user_session(response: Response, user_id: str) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    await _client().set(_user_session_key(token), user_id, ex=settings.user_session_ttl_seconds)
    response.set_cookie(
        USER_COOKIE_NAME,
        token,
        max_age=settings.user_session_ttl_seconds,
        httponly=True,
        secure=settings.resolved_admin_cookie_secure,
        samesite="lax",
        path="/",
    )


async def destroy_user_session(request: Request, response: Response) -> None:
    token = request.cookies.get(USER_COOKIE_NAME)
    if token:
        await _client().delete(_user_session_key(token))
    response.delete_cookie(USER_COOKIE_NAME, path="/")


async def _user_session_user_id(request: Request) -> str | None:
    """The user id held by a valid cin_user cookie, or None."""
    token = request.cookies.get(USER_COOKIE_NAME)
    if not token:
        return None
    value = await _client().get(_user_session_key(token))
    return value.decode("utf-8") if value else None


async def _legacy_admin_session_valid(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    return bool(token) and await _session_exists(token)


def _ensure_same_origin(request: Request) -> None:
    """Shared defence-in-depth CSRF gate for cookie-authenticated routes."""
    if request.method not in _SAFE_METHODS and not _same_origin_request(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request rejected")


# Per-email login lockout, mirroring the global admin one but keyed per
# address so one brute-forced account can't lock out every user.
async def user_is_login_locked_out(email: str) -> bool:
    count = await _client().get(_USER_LOGIN_FAIL_PREFIX + email)
    return count is not None and int(count) >= _USER_LOGIN_FAIL_MAX_ATTEMPTS


async def record_user_login_failure(email: str) -> None:
    client = _client()
    count = await client.incr(_USER_LOGIN_FAIL_PREFIX + email)
    if count == 1:
        await client.expire(_USER_LOGIN_FAIL_PREFIX + email, _USER_LOGIN_FAIL_WINDOW_SECONDS)


async def reset_user_login_failures(email: str) -> None:
    await _client().delete(_USER_LOGIN_FAIL_PREFIX + email)
