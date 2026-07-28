from fastapi import FastAPI

API_PREFIX = "/api/v1"


def register_routes(app: FastAPI) -> None:
    from app.api.routes import (
        analysis,
        claims,
        drafts,
        exports,
        projects,
        recommendations,
        references,
    )

    app.include_router(projects.router, prefix=API_PREFIX)
    app.include_router(drafts.router, prefix=API_PREFIX)
    app.include_router(references.router, prefix=API_PREFIX)
    app.include_router(analysis.router, prefix=API_PREFIX)
    app.include_router(claims.router, prefix=API_PREFIX)
    app.include_router(recommendations.router, prefix=API_PREFIX)
    app.include_router(exports.router, prefix=API_PREFIX)
