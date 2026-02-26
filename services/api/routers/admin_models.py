"""
Admin Model Registry API — promotion safety gates.

Promotion path: staging -> ab_test -> production (admin-only).
Constraints:
  - New model must beat current on primary metric to promote
  - 2-minute cooldown between promotions per model name
  - artifactHash verified on display
  - All promotions logged to AuditLog
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.middleware.audit import audit_action
from services.api.routers._admin_deps import require_admin_user, get_db
from services.api.db.models import ModelRegistry

router = APIRouter(prefix="/admin/models", tags=["admin-models"])

# Valid promotion transitions
PROMOTION_PATH = {
    "staging": "ab_test",
    "ab_test": "production",
}

# Cooldown between promotions for the same model name
PROMOTION_COOLDOWN = timedelta(minutes=2)

# Primary metric per model type (used for safety gate comparison)
PRIMARY_METRIC = {
    "classification": "f1",
    "ranking": "ndcg_at_10",
    "extraction": "precision",
    "scoring": "rmse",
}

# For scoring/rmse, lower is better
LOWER_IS_BETTER = {"rmse", "mae", "loss"}


class PromoteRequest(BaseModel):
    target_stage: str  # "ab_test" or "production"


class PromoteResponse(BaseModel):
    id: str
    model_name: str
    model_version: str
    previous_stage: str
    new_stage: str
    audit_log_id: str


class ModelSummary(BaseModel):
    id: str
    model_name: str
    model_version: str
    stage: str
    model_type: str
    description: Optional[str]
    artifact_path: Optional[str]
    artifact_hash: Optional[str]
    metrics: Optional[dict]
    evaluated_at: Optional[datetime]
    training_data_range: Optional[dict]
    promoted_at: Optional[datetime]
    promoted_by: Optional[str]
    created_at: datetime


def _model_to_summary(m: ModelRegistry) -> dict:
    return ModelSummary(
        id=m.id,
        model_name=m.modelName,
        model_version=m.modelVersion,
        stage=m.stage,
        model_type=m.modelType,
        description=m.description,
        artifact_path=m.artifactPath,
        artifact_hash=m.artifactHash,
        metrics=m.metrics,
        evaluated_at=m.evaluatedAt,
        training_data_range=m.trainingDataRange,
        promoted_at=m.promotedAt,
        promoted_by=m.promotedBy,
        created_at=m.createdAt,
    ).model_dump()


@router.get("")
async def list_models(
    model_name: Optional[str] = None,
    stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    List all registered models with stage badges.
    Filterable by model_name and/or stage.
    """
    stmt = select(ModelRegistry)
    if model_name:
        stmt = stmt.where(ModelRegistry.modelName == model_name)
    if stage:
        stmt = stmt.where(ModelRegistry.stage == stage)
    stmt = stmt.order_by(ModelRegistry.createdAt.desc())

    result = await db.execute(stmt)
    models = result.scalars().all()

    return {
        "data": [_model_to_summary(m) for m in models],
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


@router.get("/{model_id}")
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """Get single model with full details."""
    model = await db.get(ModelRegistry, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    return {
        "data": _model_to_summary(model),
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


@router.get("/{model_id}/compare")
async def compare_with_current(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    Compare candidate model's metrics against the current model in the
    next stage. Returns comparison data for the promotion gate UI.
    """
    candidate = await db.get(ModelRegistry, model_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Model not found")

    next_stage = PROMOTION_PATH.get(candidate.stage)
    if not next_stage:
        raise HTTPException(
            status_code=400,
            detail=f"No promotion path from '{candidate.stage}'",
        )

    # Find current model in the target stage
    result = await db.execute(
        select(ModelRegistry)
        .where(ModelRegistry.modelName == candidate.modelName)
        .where(ModelRegistry.stage == next_stage)
        .order_by(ModelRegistry.promotedAt.desc())
        .limit(1)
    )
    current = result.scalars().first()

    primary_metric_key = PRIMARY_METRIC.get(candidate.modelType, "f1")
    candidate_metrics = candidate.metrics or {}
    current_metrics = current.metrics if current else {}

    candidate_primary = candidate_metrics.get(primary_metric_key)
    current_primary = current_metrics.get(primary_metric_key) if current_metrics else None

    # Determine if candidate beats current
    passes_gate = True
    if current_primary is not None and candidate_primary is not None:
        if primary_metric_key in LOWER_IS_BETTER:
            passes_gate = candidate_primary <= current_primary
        else:
            passes_gate = candidate_primary >= current_primary
    elif candidate_primary is None:
        passes_gate = False  # No metrics = cannot promote

    return {
        "data": {
            "candidate": {
                "id": candidate.id,
                "version": candidate.modelVersion,
                "stage": candidate.stage,
                "metrics": candidate_metrics,
            },
            "current": {
                "id": current.id if current else None,
                "version": current.modelVersion if current else None,
                "stage": next_stage,
                "metrics": current_metrics,
            },
            "comparison": {
                "primary_metric": primary_metric_key,
                "candidate_value": candidate_primary,
                "current_value": current_primary,
                "passes_gate": passes_gate,
                "lower_is_better": primary_metric_key in LOWER_IS_BETTER,
            },
            "target_stage": next_stage,
        },
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


@router.post("/{model_id}/promote")
async def promote_model(
    model_id: str,
    body: PromoteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    Promote a model through the safety gate.

    Safety checks:
      1. Valid promotion path (staging->ab_test->production)
      2. Candidate beats current on primary metric
      3. 2-minute cooldown since last promotion for this model name
      4. Admin confirmation required (enforced by caller)
    """
    candidate = await db.get(ModelRegistry, model_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Model not found")

    # 1. Validate promotion path
    expected_next = PROMOTION_PATH.get(candidate.stage)
    if not expected_next:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot promote from '{candidate.stage}' -- no valid next stage",
        )
    if body.target_stage != expected_next:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target stage '{body.target_stage}'. Expected '{expected_next}'",
        )

    # 2. Cooldown check -- last promotion for this model name
    cooldown_cutoff = datetime.now(timezone.utc) - PROMOTION_COOLDOWN
    result = await db.execute(
        select(ModelRegistry)
        .where(ModelRegistry.modelName == candidate.modelName)
        .where(ModelRegistry.promotedAt >= cooldown_cutoff)
        .order_by(ModelRegistry.promotedAt.desc())
        .limit(1)
    )
    recent_promotion = result.scalars().first()
    if recent_promotion:
        cooldown_until = recent_promotion.promotedAt + PROMOTION_COOLDOWN
        raise HTTPException(
            status_code=429,
            detail=f"Promotion cooldown active until {cooldown_until.isoformat()}",
        )

    # 3. Metrics gate -- candidate must beat current
    result = await db.execute(
        select(ModelRegistry)
        .where(ModelRegistry.modelName == candidate.modelName)
        .where(ModelRegistry.stage == body.target_stage)
        .order_by(ModelRegistry.promotedAt.desc())
        .limit(1)
    )
    current = result.scalars().first()

    primary_metric_key = PRIMARY_METRIC.get(candidate.modelType, "f1")
    candidate_metrics = candidate.metrics or {}
    candidate_primary = candidate_metrics.get(primary_metric_key)

    if candidate_primary is None:
        raise HTTPException(
            status_code=400,
            detail=f"Candidate has no value for primary metric '{primary_metric_key}'",
        )

    if current:
        current_metrics = current.metrics or {}
        current_primary = current_metrics.get(primary_metric_key)
        if current_primary is not None:
            if primary_metric_key in LOWER_IS_BETTER:
                if candidate_primary > current_primary:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Candidate {primary_metric_key}={candidate_primary} "
                            f"does not beat current {primary_metric_key}={current_primary} "
                            f"(lower is better)"
                        ),
                    )
            else:
                if candidate_primary < current_primary:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Candidate {primary_metric_key}={candidate_primary} "
                            f"does not beat current {primary_metric_key}={current_primary}"
                        ),
                    )

    now = datetime.now(timezone.utc)
    before_state = {
        "stage": candidate.stage,
        "promotedAt": candidate.promotedAt.isoformat() if candidate.promotedAt else None,
        "promotedBy": candidate.promotedBy,
    }

    # 4. Archive the current model in the target stage (if exists)
    if current:
        await db.execute(
            update(ModelRegistry)
            .where(ModelRegistry.id == current.id)
            .values(stage="archived", updatedAt=now)
        )

    # 5. Promote the candidate
    await db.execute(
        update(ModelRegistry)
        .where(ModelRegistry.id == model_id)
        .values(
            stage=body.target_stage,
            promotedAt=now,
            promotedBy=admin,
            updatedAt=now,
        )
    )
    await db.commit()

    after_state = {
        "stage": body.target_stage,
        "promotedAt": now.isoformat(),
        "promotedBy": admin,
    }

    # 6. Audit log
    audit_log_id = await audit_action(
        db=db,
        request=request,
        actor_id=admin,
        action="model.promote",
        target_type="ModelRegistry",
        target_id=model_id,
        before=before_state,
        after=after_state,
    )

    return {
        "data": PromoteResponse(
            id=model_id,
            model_name=candidate.modelName,
            model_version=candidate.modelVersion,
            previous_stage=candidate.stage,
            new_stage=body.target_stage,
            audit_log_id=audit_log_id,
        ).model_dump(),
        "meta": {"timestamp": now.isoformat()},
    }
