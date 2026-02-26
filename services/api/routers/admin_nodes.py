"""
Admin Node Queue: flagged/low-convergence node management.
Approve, edit, archive nodes -- all actions logged to AuditLog.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.middleware.audit import audit_action
from services.api.routers._admin_deps import require_admin_user, get_db
from services.api.db.models import ActivityNode, ActivityAlias

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
# Helpers
# ---------------------------------------------------------------------------

def node_to_snapshot(node: ActivityNode) -> dict:
    """Convert an SA ActivityNode to a serialisable dict for audit before/after."""
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

_SORT_COLUMN_MAP = {
    "convergenceScore": ActivityNode.convergenceScore,
    "sourceCount": ActivityNode.sourceCount,
    "updatedAt": ActivityNode.updatedAt,
    "createdAt": ActivityNode.createdAt,
    "name": ActivityNode.name,
    "city": ActivityNode.city,
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
    db: AsyncSession = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    List flagged/low-convergence nodes for admin review.
    Default: all flagged + pending nodes, sorted by convergence (lowest first).
    """
    stmt = select(ActivityNode)
    count_stmt = select(func.count()).select_from(ActivityNode)

    # Status filter -- default to flagged + pending if not specified
    if status:
        stmt = stmt.where(ActivityNode.status == status)
        count_stmt = count_stmt.where(ActivityNode.status == status)
    else:
        stmt = stmt.where(ActivityNode.status.in_(["flagged", "pending"]))
        count_stmt = count_stmt.where(ActivityNode.status.in_(["flagged", "pending"]))

    # Convergence range filter
    if min_convergence is not None:
        stmt = stmt.where(ActivityNode.convergenceScore >= min_convergence)
        count_stmt = count_stmt.where(ActivityNode.convergenceScore >= min_convergence)
    if max_convergence is not None:
        stmt = stmt.where(ActivityNode.convergenceScore <= max_convergence)
        count_stmt = count_stmt.where(ActivityNode.convergenceScore <= max_convergence)

    # City filter
    if city:
        stmt = stmt.where(ActivityNode.city.ilike(f"%{city}%"))
        count_stmt = count_stmt.where(ActivityNode.city.ilike(f"%{city}%"))

    # Text search on name/canonicalName
    if search:
        search_filter = or_(
            ActivityNode.name.ilike(f"%{search}%"),
            ActivityNode.canonicalName.ilike(f"%{search}%"),
        )
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    # Sort
    sort_field = sort if sort in ALLOWED_SORT_FIELDS else "convergenceScore"
    sort_col = _SORT_COLUMN_MAP[sort_field]
    if order == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    stmt = stmt.offset(skip).limit(take)

    result = await db.execute(stmt)
    nodes = result.scalars().all()

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Fetch aliases for these nodes
    node_ids = [n.id for n in nodes]
    alias_result = await db.execute(
        select(ActivityAlias).where(ActivityAlias.activityNodeId.in_(node_ids))
    ) if node_ids else None
    aliases_by_node: dict[str, list] = {}
    if alias_result:
        for a in alias_result.scalars().all():
            aliases_by_node.setdefault(a.activityNodeId, []).append(a)

    return {
        "nodes": [
            {
                **node_to_snapshot(n),
                "aliasCount": len(aliases_by_node.get(n.id, [])),
                "aliases": [
                    {"id": a.id, "alias": a.alias, "source": a.source}
                    for a in aliases_by_node.get(n.id, [])
                ],
                "qualitySignalCount": 0,  # Omit heavy join for list view
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
    db: AsyncSession = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """Get single node with full detail for editor."""
    node = await db.get(ActivityNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Fetch aliases
    alias_result = await db.execute(
        select(ActivityAlias).where(ActivityAlias.activityNodeId == node_id)
    )
    aliases = alias_result.scalars().all()

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
            for a in aliases
        ],
        # qualitySignals and vibeTags omitted -- separate SA queries needed
        # and admin_nodes list_nodes uses raw SQL in the original for these joins
        "qualitySignals": [],
        "vibeTags": [],
    }


@router.patch("/{node_id}")
async def update_node(
    node_id: str,
    body: NodeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Update a node's fields or status.
    All changes logged to AuditLog with before/after snapshots.
    """
    # Fetch current state
    node = await db.get(ActivityNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    before = node_to_snapshot(node)

    # Build update data from non-None fields
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate status enum if changing
    if "status" in update_data:
        valid_statuses = {"pending", "approved", "flagged", "archived"}
        if update_data["status"] not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status: {update_data['status']}")

    await db.execute(
        update(ActivityNode).where(ActivityNode.id == node_id).values(**update_data)
    )
    await db.commit()

    # Re-fetch for after snapshot
    await db.refresh(node)
    after = node_to_snapshot(node)

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
    db: AsyncSession = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """Add an alias to a node. Logged to AuditLog."""
    node = await db.get(ActivityNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    from datetime import datetime, timezone
    alias = ActivityAlias(
        activityNodeId=node_id,
        alias=body.alias,
        source=body.source,
        createdAt=datetime.now(timezone.utc),
    )
    db.add(alias)
    await db.flush()
    await db.commit()

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
    db: AsyncSession = Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """Remove an alias from a node. Logged to AuditLog."""
    alias = await db.get(ActivityAlias, alias_id)
    if not alias or alias.activityNodeId != node_id:
        raise HTTPException(status_code=404, detail="Alias not found")

    alias_data = {"aliasId": alias.id, "alias": alias.alias, "source": alias.source}

    await db.execute(delete(ActivityAlias).where(ActivityAlias.id == alias_id))
    await db.commit()

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="activityNode.alias.remove",
        target_type="ActivityNode",
        target_id=node_id,
        before=alias_data,
    )

    return {"deleted": True}
