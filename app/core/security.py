"""User authentication: accounts (email + password) exchanged for
server-side sessions held in Redis and represented to the browser as an
opaque, HttpOnly cookie (`cin_user`). Passwords are hashed with stdlib
PBKDF2-HMAC-SHA256. See `app/api/routes/auth.py` for the register/login/
reset endpoints and `app/api/deps.py` for which routes they protect.

Session storage is Redis, not a signed cookie: that gives real logout and
revocation, and storing the SHA-256 of the token rather than the token
itself means a Redis dump is not a set of live credentials.

CSRF: the cookie is `SameSite=Lax`, which already stops it being sent on a
cross-site POST/PUT/DELETE in every current browser -- the Origin/
Sec-Fetch-Site check below is defence in depth, not the primary mechanism.
"""

import base64
import hashlib
import hmac
import secrets

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, Response, status

from app.core.config import get_settings

USER_COOKIE_NAME = "cin_user"

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url)
    return _redis


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


def _ensure_same_origin(request: Request) -> None:
    """Shared defence-in-depth CSRF gate for cookie-authenticated routes."""
    if request.method not in _SAFE_METHODS and not _same_origin_request(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request rejected")


# --- Password hashing (stdlib PBKDF2-HMAC-SHA256; no new deps) -------------

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


# --- User sessions (Redis opaque cookie) ----------------------------------

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
        secure=settings.resolved_cookie_secure,
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


# Per-email login lockout, so one brute-forced account can't lock out
# every user.
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


async def revoke_user_sessions(user_id: str) -> None:
    """Drop every live session for a user (deactivation, admin password
    reset, or deletion) so a revoked account can't keep acting."""
    client = _client()
    async for key in client.scan_iter(match=_USER_SESSION_KEY_PREFIX + "*"):
        value = await client.get(key)
        if value and value.decode("utf-8") == user_id:
            await client.delete(key)
