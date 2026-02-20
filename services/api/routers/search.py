"""
Search endpoint — GET /search

Wraps ActivitySearchService for HTTP consumers.
Returns API envelope with hydrated activity results.
"""

from fastapi import APIRouter, Query, Request

router = APIRouter(tags=["search"])


@router.get("/search")
async def search_activities(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    city: str = Query(..., min_length=1, max_length=100, description="City to search in"),
    category: str | None = Query(None, description="Activity category filter"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
) -> dict:
    search_service = request.app.state.search_service

    filters = {}
    if category:
        filters["category"] = category

    result = await search_service.search(
        query=q,
        city=city,
        filters=filters if filters else None,
        limit=limit,
    )

    response = {
        "success": True,
        "data": {
            "results": result["results"],
            "count": result["count"],
        },
        "requestId": request.state.request_id,
    }

    if result.get("warning"):
        response["data"]["warning"] = result["warning"]

    return response
