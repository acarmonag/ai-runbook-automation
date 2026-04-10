"""
Async SQLAlchemy engine + session factory.

DATABASE_URL defaults to PostgreSQL via asyncpg.
On startup, create_all() ensures all tables exist (no Alembic needed for dev).
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://sre:sre@localhost:5432/runbooks",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def create_tables() -> None:
    """Create all tables on startup (idempotent)."""
    from db import models  # noqa: F401 — registers models with Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[return]
    """Dependency-injection helper for FastAPI routes."""
    async with AsyncSessionLocal() as session:
        yield session
