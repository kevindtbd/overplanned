"""
Admin User Management: search, view, feature flags, subscription tiers.
All actions logged to AuditLog.
"""

from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from services.api.middleware.audit import audit_action
from services.api.routers._admin_deps import require_admin_user, get_db

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FeatureFlagUpdate(BaseModel):
    flags: dict[str, bool] = Field(
        ..., description="Map of flag name to enabled state"
    )


class SubscriptionTierUpdate(BaseModel):
    tier: str = Field(
        ..., description="New subscription tier: free | beta | pro | lifetime"
    )


class UserSummary(BaseModel):
    id: str
    email: str
    name: Optional[str]
    avatarUrl: Optional[str]
    subscriptionTier: str
    systemRole: str
    featureFlags: Optional[dict[str, Any]]
    onboardingComplete: bool
    lastActiveAt: Optional[str]
    createdAt: str
    tripCount: int
    signalCount: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_TIERS = {"free", "beta", "pro", "lifetime"}

ALLOWED_SORT_FIELDS = {
    "createdAt",
    "lastActiveAt",
    "email",
    "name",
    "subscriptionTier",
}


def user_to_snapshot(user) -> dict:
    """Convert a Prisma User to a serialisable dict for audit before/after."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "subscriptionTier": user.subscriptionTier,
        "systemRole": user.systemRole,
        "featureFlags": user.featureFlags,
        "onboardingComplete": user.onboardingComplete,
        "accessCohort": user.accessCohort,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def search_users(
    request: Request,
    q: Optional[str] = Query(None, description="Search by email or name"),
    tier: Optional[str] = Query(None, description="Filter by subscription tier"),
    role: Optional[str] = Query(None, description="Filter by system role"),
    sort: str = Query("createdAt"),
    order: str = Query("desc"),
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Search users by email/name. Supports tier and role filters.
    All lookups logged to AuditLog (action: "user_lookup").
    """
    where: dict = {}

    # Text search on email or name
    if q:
        where["OR"] = [
            {"email": {"contains": q, "mode": "insensitive"}},
            {"name": {"contains": q, "mode": "insensitive"}},
        ]

    # Tier filter
    if tier and tier in VALID_TIERS:
        where["subscriptionTier"] = tier

    # Role filter
    if role and role in {"user", "admin"}:
        where["systemRole"] = role

    # Validate sort field
    sort_field = sort if sort in ALLOWED_SORT_FIELDS else "createdAt"
    sort_order = "asc" if order == "asc" else "desc"

    users = await db.user.find_many(
        where=where,
        order={sort_field: sort_order},
        skip=skip,
        take=take,
    )

    total = await db.user.count(where=where)

    # Log the lookup
    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="user_lookup",
        target_type="User",
        target_id="search",
        after={"query": q, "tier": tier, "role": role, "results": total},
    )

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "avatarUrl": u.avatarUrl,
                "subscriptionTier": u.subscriptionTier,
                "systemRole": u.systemRole,
                "featureFlags": u.featureFlags,
                "onboardingComplete": u.onboardingComplete,
                "lastActiveAt": u.lastActiveAt.isoformat() if u.lastActiveAt else None,
                "createdAt": u.createdAt.isoformat(),
            }
            for u in users
        ],
        "total": total,
        "skip": skip,
        "take": take,
    }


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Get single user with signals, trips, tier, and feature flags.
    Lookup logged to AuditLog.
    """
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch related data
    trips = await db.trip.find_many(
        where={"userId": user_id},
        order={"createdAt": "desc"},
        take=20,
    )

    signal_count = await db.behavioralsignal.count(where={"userId": user_id})

    recent_signals = await db.behavioralsignal.find_many(
        where={"userId": user_id},
        order={"createdAt": "desc"},
        take=20,
    )

    # Log the lookup
    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="user_lookup",
        target_type="User",
        target_id=user_id,
    )

    return {
        "user": {
            **user_to_snapshot(user),
            "avatarUrl": user.avatarUrl,
            "googleId": user.googleId,
            "emailVerified": user.emailVerified.isoformat() if user.emailVerified else None,
            "stripeCustomerId": user.stripeCustomerId,
            "stripeSubId": user.stripeSubId,
            "lastActiveAt": user.lastActiveAt.isoformat() if user.lastActiveAt else None,
            "createdAt": user.createdAt.isoformat(),
            "updatedAt": user.updatedAt.isoformat(),
        },
        "trips": [
            {
                "id": t.id,
                "destination": t.destination,
                "city": t.city,
                "country": t.country,
                "mode": t.mode,
                "status": t.status,
                "startDate": t.startDate.isoformat(),
                "endDate": t.endDate.isoformat(),
                "createdAt": t.createdAt.isoformat(),
            }
            for t in trips
        ],
        "signalCount": signal_count,
        "recentSignals": [
            {
                "id": s.id,
                "signalType": s.signalType,
                "signalValue": s.signalValue,
                "tripPhase": s.tripPhase,
                "rawAction": s.rawAction,
                "createdAt": s.createdAt.isoformat(),
            }
            for s in recent_signals
        ],
    }


@router.patch("/{user_id}/feature-flags")
async def update_feature_flags(
    user_id: str,
    body: FeatureFlagUpdate,
    request: Request,
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Override feature flags for a user.
    Merges with existing flags. Logged to AuditLog with before/after.
    """
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before_flags = user.featureFlags or {}

    # Merge new flags into existing
    merged = {**before_flags, **body.flags}

    updated = await db.user.update(
        where={"id": user_id},
        data={"featureFlags": merged},
    )

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="user.feature_flag_override",
        target_type="User",
        target_id=user_id,
        before={"featureFlags": before_flags},
        after={"featureFlags": merged},
    )

    return {
        "featureFlags": updated.featureFlags,
        "auditAction": "user.feature_flag_override",
    }


@router.patch("/{user_id}/subscription-tier")
async def update_subscription_tier(
    user_id: str,
    body: SubscriptionTierUpdate,
    request: Request,
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Change a user's subscription tier via admin panel.
    Replaces manual SQL for lifetime users. Logged to AuditLog.
    """
    if body.tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier: {body.tier}. Must be one of: {', '.join(sorted(VALID_TIERS))}",
        )

    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before_tier = user.subscriptionTier

    updated = await db.user.update(
        where={"id": user_id},
        data={"subscriptionTier": body.tier},
    )

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="user.subscription_tier_change",
        target_type="User",
        target_id=user_id,
        before={"subscriptionTier": before_tier},
        after={"subscriptionTier": body.tier},
    )

    return {
        "subscriptionTier": updated.subscriptionTier,
        "auditAction": "user.subscription_tier_change",
    }
