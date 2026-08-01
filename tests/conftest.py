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
    from alembic.config import Config

    from alembic import command

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
                "TRUNCATE drafts, reference_papers, claims, "
                "citation_recommendations, accepted_citations, "
                "llm_verification_cache, llm_classification_cache, "
                "analysis_runs, exports RESTART IDENTITY CASCADE"
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


async def upload_draft(client, filename: str = "sample_draft.docx") -> str:
    data = (FIXTURES / filename).read_bytes()
    resp = await client.post("/api/v1/drafts/upload", files={"file": (filename, data)})
    return resp.json()["id"]


async def import_dataset(client, filename: str = "sample_dataset.xlsx") -> dict:
    """Import the fixture dataset into the shared library."""
    data = (FIXTURES / filename).read_bytes()
    resp = await client.post("/api/v1/library/import", files={"file": (filename, data)})
    return resp.json()


@pytest.fixture
async def seeded_draft(client, db_session) -> str:
    """Draft uploaded with the shared library seeded and enriched+embedded."""
    from app.services.embedding_service import embed_pending_references
    from app.services.enrichment import enrich_pending_references

    draft_id = await upload_draft(client)
    await import_dataset(client)
    enrich_pending_references(db_session)
    embed_pending_references(db_session)
    db_session.commit()
    return draft_id


@pytest.fixture
def db_session(clean_db) -> Iterator:
    """Sync session, matching what Celery worker code uses."""
    from app.db.session import get_sync_session_factory

    with get_sync_session_factory()() as session:
        yield session
