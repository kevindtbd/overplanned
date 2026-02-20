"""Health check endpoint."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> dict:
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "version": request.app.state.settings.app_version,
        },
        "requestId": request.state.request_id,
    }
