"""Shared dependencies for admin routers."""
from fastapi import HTTPException, Request


async def require_admin_user(request: Request) -> str:
    """Validates admin auth from request headers. Returns actor_id."""
    actor_id = request.headers.get("X-Admin-User-Id")
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = request.headers.get("X-Admin-Role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return actor_id


async def get_db(request: Request):
    """Get the shared database client from app state."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return db
