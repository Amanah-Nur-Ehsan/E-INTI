from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    log.info(
        "startup",
        mock_llm=settings.llm_mocked,
        mock_scopus=settings.scopus_mocked,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="CitationINTI", version="0.1.0", lifespan=lifespan)

    from app.api.routes import register_routes

    register_routes(app)

    @app.get("/healthz")
    async def healthz() -> dict:
        settings = get_settings()
        status = {"status": "ok", "db": "down", "redis": "down"}

        from app.db.session import get_async_engine

        try:
            async with get_async_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            status["db"] = "up"
        except Exception as exc:  # pragma: no cover - infra failure path
            status["status"] = "degraded"
            status["db"] = f"down: {type(exc).__name__}"

        try:
            r = aioredis.from_url(settings.redis_url)
            await r.ping()
            await r.aclose()
            status["redis"] = "up"
        except Exception as exc:  # pragma: no cover
            status["status"] = "degraded"
            status["redis"] = f"down: {type(exc).__name__}"

        return status

    return app


app = create_app()
