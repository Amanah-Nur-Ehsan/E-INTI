import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

# Tests always run fully offline against the test database.
os.environ["USE_MOCK_PROVIDERS"] = "true"
os.environ["EMBEDDING_FAKE"] = "true"
os.environ["RERANKER_FAKE"] = "true"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
# Registration is off unless a test explicitly enables it (the .env may
# have it on for the dev server; tests must not depend on that).
os.environ["REGISTRATION_ENABLED"] = "false"
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://dev:dev@localhost:5433/citation_test"
)

FIXTURES = Path(__file__).parent / "fixtures"

ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "admin-pass-123"


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
                "analysis_runs, exports, users, user_tokens "
                "RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()
    yield


@pytest.fixture
async def anon_client(clean_db) -> AsyncIterator:
    """Unauthenticated client -- no admin session. Use this (not `client`)
    when a test specifically exercises the unauthenticated/401 path;
    everything else should use `client`, which is pre-logged-in so the
    hundreds of tests seeding the library via POST /library/import don't
    each need to know about admin auth.
    """
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class _EmailStub:
    def __init__(self):
        self.messages: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str, html: str) -> None:
        self.messages.append((to, subject, text))


@pytest.fixture
async def email_stub(anon_client):
    from app.main import app
    from app.services.email_client import get_email_sender

    stub = _EmailStub()
    app.dependency_overrides[get_email_sender] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_email_sender, None)


@pytest.fixture
async def client(anon_client, settings, monkeypatch, email_stub) -> AsyncIterator:
    """Role-admin-authenticated by default. Registers an admin user (email
    in admin_emails) and activates it, so the cin_user cookie carries a
    role=admin session covering the admin-gated routes most tests only use
    incidentally, to seed data, not to test auth itself.
    """
    import re

    monkeypatch.setattr(settings, "registration_enabled", True)
    monkeypatch.setattr(settings, "admin_emails", [ADMIN_EMAIL])
    resp = await anon_client.post(
        "/api/v1/auth/register", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 201, f"test admin registration failed: {resp.text}"
    text = email_stub.messages[-1][2]
    token = re.search(r"token=([A-Za-z0-9_\-]+)", text).group(1)
    resp = await anon_client.post("/api/v1/auth/activate", json={"token": token})
    assert resp.status_code == 204, f"test admin activation failed: {resp.text}"
    yield anon_client


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
