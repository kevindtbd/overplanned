"""
Admin Node Queue: flagged/low-convergence node management.
Approve, edit, archive nodes — all actions logged to AuditLog.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from prisma import Prisma

from services.api.middleware.audit import audit_action

router = APIRouter(prefix="/admin/nodes", tags=["admin-nodes"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NodeListParams(BaseModel):
    status: Optional[str] = None  # pending | approved | flagged | archived
    min_convergence: Optional[float] = None
    max_convergence: Optional[float] = None
    city: Optional[str] = None
    search: Optional[str] = None
    sort: str = "convergenceScore"
    order: str = "asc"
    skip: int = 0
    take: int = 50


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    canonicalName: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    neighborhood: Optional[str] = None
    address: Optional[str] = None
    phoneNumber: Optional[str] = None
    websiteUrl: Optional[str] = None
    descriptionShort: Optional[str] = None
    descriptionLong: Optional[str] = None
    priceLevel: Optional[int] = None
    status: Optional[str] = None  # pending | approved | flagged | archived
    flagReason: Optional[str] = None
    resolvedToId: Optional[str] = None
    isCanonical: Optional[bool] = None


class AliasCreate(BaseModel):
    alias: str = Field(..., min_length=1, max_length=500)
    source: str = Field(default="admin", max_length=100)


class NodeSummary(BaseModel):
    id: str
    name: str
    canonicalName: str
    city: str
    country: str
    category: str
    status: str
    convergenceScore: Optional[float]
    sourceCount: int
    flagReason: Optional[str]
    aliasCount: int
    updatedAt: str


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_db() -> Prisma:
    """Placeholder — wire to actual Prisma client in app startup."""
    from prisma import Prisma
    db = Prisma()
    await db.connect()
    try:
        yield db
    finally:
        await db.disconnect()


async def require_admin_user(request: Request):
    """
    Validates admin auth from request headers.
    In production, wired to session/JWT check.
    """
    actor_id = request.headers.get("X-Admin-User-Id")
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = request.headers.get("X-Admin-Role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return actor_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def node_to_snapshot(node) -> dict:
    """Convert a Prisma ActivityNode to a serialisable dict for audit before/after."""
    return {
        "id": node.id,
        "name": node.name,
        "canonicalName": node.canonicalName,
        "city": node.city,
        "country": node.country,
        "category": node.category,
        "subcategory": node.subcategory,
        "neighborhood": node.neighborhood,
        "status": node.status,
        "flagReason": node.flagReason,
        "convergenceScore": node.convergenceScore,
        "resolvedToId": node.resolvedToId,
        "isCanonical": node.isCanonical,
        "priceLevel": node.priceLevel,
        "address": node.address,
        "phoneNumber": node.phoneNumber,
        "websiteUrl": node.websiteUrl,
        "descriptionShort": node.descriptionShort,
        "descriptionLong": node.descriptionLong,
        "sourceCount": node.sourceCount,
    }


ALLOWED_SORT_FIELDS = {
    "convergenceScore", "sourceCount", "updatedAt", "createdAt", "name", "city",
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_nodes(
    request: Request,
    status: Optional[str] = Query(None),
    min_convergence: Optional[float] = Query(None),
    max_convergence: Optional[float] = Query(None),
    city: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("convergenceScore"),
    order: str = Query("asc"),
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
    db: Prisma = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    List flagged/low-convergence nodes for admin review.
    Default: all flagged + pending nodes, sorted by convergence (lowest first).
    """
    where: dict = {}

    # Status filter — default to flagged + pending if not specified
    if status:
        where["status"] = status
    else:
        where["status"] = {"in": ["flagged", "pending"]}

    # Convergence range filter
    if min_convergence is not None or max_convergence is not None:
        conv_filter = {}
        if min_convergence is not None:
            conv_filter["gte"] = min_convergence
        if max_convergence is not None:
            conv_filter["lte"] = max_convergence
        where["convergenceScore"] = conv_filter

    # City filter
    if city:
        where["city"] = {"contains": city, "mode": "insensitive"}

    # Text search on name/canonicalName
    if search:
        where["OR"] = [
            {"name": {"contains": search, "mode": "insensitive"}},
            {"canonicalName": {"contains": search, "mode": "insensitive"}},
        ]

    # Validate sort field
    sort_field = sort if sort in ALLOWED_SORT_FIELDS else "convergenceScore"
    sort_order = "asc" if order == "asc" else "desc"

    nodes = await db.activitynode.find_many(
        where=where,
        include={"aliases": True, "qualitySignals": {"take": 5}},
        order={sort_field: sort_order},
        skip=skip,
        take=take,
    )

    total = await db.activitynode.count(where=where)

    return {
        "nodes": [
            {
                **node_to_snapshot(n),
                "aliasCount": len(n.aliases) if n.aliases else 0,
                "aliases": [
                    {"id": a.id, "alias": a.alias, "source": a.source}
                    for a in (n.aliases or [])
                ],
                "qualitySignalCount": len(n.qualitySignals) if n.qualitySignals else 0,
                "updatedAt": n.updatedAt.isoformat(),
            }
            for n in nodes
        ],
        "total": total,
        "skip": skip,
        "take": take,
    }


@router.get("/{node_id}")
async def get_node(
    node_id: str,
    request: Request,
    db: Prisma = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """Get single node with full detail for editor."""
    node = await db.activitynode.find_unique(
        where={"id": node_id},
        include={
            "aliases": True,
            "qualitySignals": {"order_by": {"createdAt": "desc"}, "take": 20},
            "vibeTags": {"include": {"vibeTag": True}},
        },
    )
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return {
        **node_to_snapshot(node),
        "slug": node.slug,
        "latitude": node.latitude,
        "longitude": node.longitude,
        "hours": node.hours,
        "foursquareId": node.foursquareId,
        "googlePlaceId": node.googlePlaceId,
        "primaryImageUrl": node.primaryImageUrl,
        "imageSource": node.imageSource,
        "imageValidated": node.imageValidated,
        "contentHash": node.contentHash,
        "lastScrapedAt": node.lastScrapedAt.isoformat() if node.lastScrapedAt else None,
        "lastValidatedAt": node.lastValidatedAt.isoformat() if node.lastValidatedAt else None,
        "createdAt": node.createdAt.isoformat(),
        "updatedAt": node.updatedAt.isoformat(),
        "aliases": [
            {"id": a.id, "alias": a.alias, "source": a.source, "createdAt": a.createdAt.isoformat()}
            for a in (node.aliases or [])
        ],
        "qualitySignals": [
            {
                "id": qs.id,
                "sourceName": qs.sourceName,
                "sourceAuthority": qs.sourceAuthority,
                "signalType": qs.signalType,
                "extractedAt": qs.extractedAt.isoformat(),
            }
            for qs in (node.qualitySignals or [])
        ],
        "vibeTags": [
            {
                "id": vt.id,
                "tagName": vt.vibeTag.name if vt.vibeTag else None,
                "tagSlug": vt.vibeTag.slug if vt.vibeTag else None,
                "score": vt.score,
                "source": vt.source,
            }
            for vt in (node.vibeTags or [])
        ],
    }


@router.patch("/{node_id}")
async def update_node(
    node_id: str,
    body: NodeUpdate,
    request: Request,
    db: Prisma = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Update a node's fields or status.
    All changes logged to AuditLog with before/after snapshots.
    """
    # Fetch current state
    node = await db.activitynode.find_unique(where={"id": node_id})
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    before = node_to_snapshot(node)

    # Build update data from non-None fields
    update_data = body.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate status enum if changing
    if "status" in update_data:
        valid_statuses = {"pending", "approved", "flagged", "archived"}
        if update_data["status"] not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status: {update_data['status']}")

    updated = await db.activitynode.update(
        where={"id": node_id},
        data=update_data,
    )

    after = node_to_snapshot(updated)

    # Determine audit action based on what changed
    action = "activityNode.update"
    if "status" in update_data:
        action = f"activityNode.status.{update_data['status']}"

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action=action,
        target_type="ActivityNode",
        target_id=node_id,
        before=before,
        after=after,
    )

    return {"node": after, "auditAction": action}


@router.post("/{node_id}/aliases")
async def add_alias(
    node_id: str,
    body: AliasCreate,
    request: Request,
    db: Prisma = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """Add an alias to a node. Logged to AuditLog."""
    node = await db.activitynode.find_unique(where={"id": node_id})
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    alias = await db.activityalias.create(
        data={
            "activityNodeId": node_id,
            "alias": body.alias,
            "source": body.source,
        }
    )

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="activityNode.alias.add",
        target_type="ActivityNode",
        target_id=node_id,
        after={"aliasId": alias.id, "alias": body.alias, "source": body.source},
    )

    return {"alias": {"id": alias.id, "alias": alias.alias, "source": alias.source}}


@router.delete("/{node_id}/aliases/{alias_id}")
async def remove_alias(
    node_id: str,
    alias_id: str,
    request: Request,
    db: Prisma = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """Remove an alias from a node. Logged to AuditLog."""
    alias = await db.activityalias.find_unique(where={"id": alias_id})
    if not alias or alias.activityNodeId != node_id:
        raise HTTPException(status_code=404, detail="Alias not found")

    await db.activityalias.delete(where={"id": alias_id})

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="activityNode.alias.remove",
        target_type="ActivityNode",
        target_id=node_id,
        before={"aliasId": alias.id, "alias": alias.alias, "source": alias.source},
    )

    return {"deleted": True}
