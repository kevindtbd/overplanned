"""
AsyncEngine factory and standalone session context manager.

NullPool because PgBouncer owns connection pooling — SA should not
maintain its own pool on top. This matches the devops playbook
(PgBouncer pool_size=20 on Cloud SQL).
"""

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from services.api.config import settings


def create_engine() -> AsyncEngine:
    """
    Create async engine for use with PgBouncer transaction-mode pooling.

    NullPool because PgBouncer owns connection pooling — SA should not
    maintain its own pool on top.
    """
    url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        url,
        pool_class=NullPool,
        echo=settings.debug and settings.environment == "development",
    )


@asynccontextmanager
async def standalone_session():
    """
    For standalone scripts (completion.py, disambiguation.py) that run outside FastAPI.
    Handles engine lifecycle to prevent connection leaks with NullPool.
    """
    engine = create_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()
