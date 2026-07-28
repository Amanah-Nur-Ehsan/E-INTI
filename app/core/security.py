"""API-key authentication seam.

There is no user model yet — this MVP is explicitly single-user per the
product spec. `require_api_key` is the dependency real per-user auth will
eventually replace or wrap; adding it now means every route that needs
protection already has the import in place, rather than retrofitting each
one later.

Disabled entirely when `API_KEY` is unset (local dev). Once set, every
request must carry a matching `X-API-Key` header.
"""

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency: no-op when API_KEY is unset, else enforces it.

    Add as a route or router dependency once the deployment needs it:

        router = APIRouter(dependencies=[Depends(require_api_key)])
    """
    configured = get_settings().api_key
    if not configured:
        return
    if not x_api_key or not _constant_time_eq(x_api_key, configured):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")
