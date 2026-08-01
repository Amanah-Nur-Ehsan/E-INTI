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
                "TRUNCATE projects, drafts, reference_papers, claims, "
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


async def create_project(client, name: str = "Test project", **fields) -> str:
    payload = {"name": name, **fields}
    return (await client.post("/api/v1/projects", json=payload)).json()["id"]


async def upload_draft(client, project_id: str, filename: str = "sample_draft.docx") -> str:
    data = (FIXTURES / filename).read_bytes()
    resp = await client.post(
        f"/api/v1/projects/{project_id}/drafts/upload", files={"file": (filename, data)}
    )
    return resp.json()["id"]


async def import_dataset(client, project_id: str | None = None, filename: str = "sample_dataset.xlsx") -> dict:
    """Import the fixture dataset into the shared library.

    `project_id` is accepted (and ignored) for backwards compatibility with
    the many call sites that predate the global library -- the library has
    no project scoping.
    """
    data = (FIXTURES / filename).read_bytes()
    resp = await client.post("/api/v1/library/import", files={"file": (filename, data)})
    return resp.json()


@pytest.fixture
async def seeded_project(client, db_session) -> str:
    """Project with the fixture draft uploaded and the shared library seeded+enriched."""
    from app.services.embedding_service import embed_pending_references
    from app.services.enrichment import enrich_pending_references

    project_id = await create_project(client, "Fraud detection", field_of_study="Computer Science")
    await upload_draft(client, project_id)
    await import_dataset(client)
    enrich_pending_references(db_session)
    embed_pending_references(db_session)
    db_session.commit()
    return project_id


@pytest.fixture
def db_session(clean_db) -> Iterator:
    """Sync session, matching what Celery worker code uses."""
    from app.db.session import get_sync_session_factory

    with get_sync_session_factory()() as session:
        yield session
