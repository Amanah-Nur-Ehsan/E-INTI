import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

# Tests always run fully offline against the test database.
os.environ["USE_MOCK_PROVIDERS"] = "true"
os.environ["EMBEDDING_FAKE"] = "true"
os.environ["RERANKER_FAKE"] = "true"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://dev:dev@localhost:5433/citation_test"
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def settings():
    from app.core.config import get_settings

    return get_settings()


@pytest.fixture(scope="session")
def _migrated_db(settings) -> Iterator[None]:
    """Run Alembic once per session against the test database."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.sync_db_url)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def clean_db(_migrated_db, settings) -> Iterator[None]:
    """Truncate all data tables before each test."""
    from sqlalchemy import create_engine, text

    engine = create_engine(settings.sync_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE projects, drafts, reference_papers, claims, "
                "citation_recommendations, accepted_citations, "
                "llm_verification_cache, analysis_runs RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()
    yield


@pytest.fixture
async def client(clean_db) -> AsyncIterator:
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def db_session(clean_db) -> Iterator:
    """Sync session, matching what Celery worker code uses."""
    from app.db.session import get_sync_session_factory

    with get_sync_session_factory()() as session:
        yield session
