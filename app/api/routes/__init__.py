from fastapi import Depends, FastAPI

from app.api.deps import require_user

API_PREFIX = "/api/v1"


def register_routes(app: FastAPI) -> None:
    from app.api.routes import (
        admin,
        analysis,
        auth,
        claims,
        drafts,
        exports,
        recommendations,
        references,
    )

    # Public: authentication, legacy admin login, library status.
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(references.router, prefix=API_PREFIX)
    # Admin-only: library management (router-level dep, see references.py).
    app.include_router(references.admin_router, prefix=API_PREFIX)

    # The whole main app requires login. Gated centrally here (not per-route)
    # so a route added later can't accidentally be public.
    app.include_router(
        drafts.router, prefix=API_PREFIX, dependencies=[Depends(require_user)]
    )
    app.include_router(
        analysis.router, prefix=API_PREFIX, dependencies=[Depends(require_user)]
    )
    app.include_router(
        claims.router, prefix=API_PREFIX, dependencies=[Depends(require_user)]
    )
    app.include_router(
        recommendations.router, prefix=API_PREFIX, dependencies=[Depends(require_user)]
    )
    app.include_router(
        exports.router, prefix=API_PREFIX, dependencies=[Depends(require_user)]
    )
