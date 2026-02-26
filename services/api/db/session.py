"""
FastAPI dependency for SA async sessions.

expire_on_commit=False is set on the factory (in lifespan) because NullPool
returns the connection after commit. Without this flag, accessing any model
attribute after commit triggers a lazy load on a closed connection.
"""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency -- yields an SA session from app.state.db_session_factory.
    """
    factory: async_sessionmaker = request.app.state.db_session_factory
    async with factory() as session:
        yield session
