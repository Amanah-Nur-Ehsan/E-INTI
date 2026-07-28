"""Engine/session factories.

The API uses the async engine (asyncpg); Celery workers use the sync
engine (psycopg) — mixing an async engine into prefork workers is a
known footgun, so the two paths are kept fully separate.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_async_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)


@lru_cache
def get_sync_engine():
    return create_engine(get_settings().sync_db_url, pool_pre_ping=True)


@lru_cache
def get_sync_session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_sync_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_async_session_factory()() as session:
        yield session
