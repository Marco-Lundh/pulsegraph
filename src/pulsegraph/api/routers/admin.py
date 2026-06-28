"""Admin-only endpoints (ADR 0020/0021)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_db, require_admin
from pulsegraph.api.health import operational_summary
from pulsegraph.api.schemas import (
    ReviewDecisionCreate,
    SourceHealthOut,
)
from pulsegraph.config import get_settings
from pulsegraph.db.models import (
    AuditLogEntry,
    Evaluation,
    ReviewDecision,
    SourceHealth,
    User,
)
from pulsegraph.domain.enums import EvalStatus
from pulsegraph.redis_client import make_redis

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/source-health", response_model=list[SourceHealthOut])
def list_source_health(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SourceHealth]:
    return db.query(SourceHealth).all()


@router.get("/ops")
def operational_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Operator dashboard of infrastructure signals (ADR 0020).

    Distinct from product eval-health (ADR 0006): cloud-model spend vs the
    cap (ADR 0008), queue depth and worker liveness (ADR 0015), run
    latency, and any sources paused for drift (ADR 0010). Each section
    carries the alert flag operators watch.
    """
    settings = get_settings()
    return operational_summary(db, make_redis(settings.redis_url), settings)


@router.get("/review-queue")
def list_review_queue(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[dict]:
    rows = (
        db.query(Evaluation)
        .filter(Evaluation.status == EvalStatus.REVIEW)
        .order_by(Evaluation.evaluated_at.asc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "analysis_id": str(r.analysis_id),
            "relevance_score": r.relevance_score,
            "confidence": r.confidence,
            "evaluated_at": r.evaluated_at.isoformat(),
        }
        for r in rows
    ]


@router.post(
    "/review-queue/{evaluation_id}/decide",
    status_code=status.HTTP_201_CREATED,
)
def decide(
    evaluation_id: uuid.UUID,
    body: ReviewDecisionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    existing = (
        db.query(ReviewDecision)
        .filter(ReviewDecision.evaluation_id == evaluation_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Decision already recorded",
        )
    decision = ReviewDecision(
        evaluation_id=evaluation_id,
        reviewer_id=admin.id,
        decision=body.decision,
        corrected_label=body.corrected_label,
        note=body.note,
    )
    db.add(decision)
    db.add(
        AuditLogEntry(
            actor_user_id=admin.id,
            action="review.decide",
            entity_type="evaluation",
            entity_id=evaluation_id,
            meta={"decision": body.decision},
        )
    )
    db.commit()
    db.refresh(decision)
    return {"id": str(decision.id), "decision": decision.decision}


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    """Erase a user and all their data (GDPR right to erasure, ADR 0018).

    All user-owned rows cascade via ON DELETE CASCADE. The audit entry
    records the admin actor plus the erased user's id and email.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    db.add(
        AuditLogEntry(
            actor_user_id=admin.id,
            action="user.delete",
            entity_type="user",
            entity_id=user_id,
            meta={"email": target.email, "by": "admin"},
        )
    )
    db.delete(target)
    db.commit()
