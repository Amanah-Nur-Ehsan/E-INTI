from fastapi import Depends, FastAPI

from app.api.deps import require_user

API_PREFIX = "/api/v1"


def register_routes(app: FastAPI) -> None:
    from app.api.routes import (
        admin_dashboard,
        admin_users,
        analysis,
        auth,
        claims,
        drafts,
        exports,
        history,
        recommendations,
        references,
    )

    # Public: authentication and library status.
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(references.router, prefix=API_PREFIX)
    # Admin-only: dashboard, library management, and user management.
    app.include_router(admin_dashboard.router, prefix=API_PREFIX)
    app.include_router(references.admin_router, prefix=API_PREFIX)
    app.include_router(admin_users.router, prefix=API_PREFIX)

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
    app.include_router(
        history.router, prefix=API_PREFIX, dependencies=[Depends(require_user)]
    )
