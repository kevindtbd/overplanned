"""Shared dependencies for admin routers."""
from fastapi import HTTPException, Request

from services.api.middleware.admin_hmac import verify_admin_hmac


async def require_admin_user(request: Request) -> str:
    """
    Validates admin auth via HMAC signature verification.

    Returns the verified actor_id from the signed X-Admin-User-Id header.
    No fallback -- if HMAC secret is missing or verification fails, request is rejected.
    """
    return await verify_admin_hmac(request)


async def get_db(request: Request):
    """Get an SA AsyncSession from app state's session factory."""
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with factory() as session:
        yield session
