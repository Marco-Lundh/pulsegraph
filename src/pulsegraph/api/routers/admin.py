"""Admin-only endpoints (ADR 0020/0021)."""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_db, require_admin
from pulsegraph.api.eval_health import eval_health_summary
from pulsegraph.api.health import operational_summary
from pulsegraph.api.schemas import (
    ReviewDecisionCreate,
    SourceHealthOut,
    UserOut,
)
from pulsegraph.config import get_settings
from pulsegraph.db.models import (
    AuditLogEntry,
    Evaluation,
    ReviewDecision,
    SourceHealth,
    User,
)
from pulsegraph.domain.enums import EvalStatus, SourceKind, SourceStatus
from pulsegraph.redis_client import make_redis

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/source-health", response_model=list[SourceHealthOut])
def list_source_health(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SourceHealth]:
    return db.query(SourceHealth).all()


@router.post("/source-health/{source}/resume", response_model=SourceHealthOut)
def resume_source(
    source: SourceKind,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> SourceHealth:
    """Clear a source's drift pause so the scheduler resumes it (ADR 0010).

    A source paused for schema drift is never triggered again on its own
    (the scheduler skips it), so recovery is an explicit operator action
    once the upstream schema is back or the plugin has been fixed.
    """
    row = db.query(SourceHealth).filter(SourceHealth.source == source).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    row.status = SourceStatus.HEALTHY
    row.drift_detail = None
    row.last_checked_at = datetime.datetime.now(datetime.UTC)
    db.add(
        AuditLogEntry(
            actor_user_id=admin.id,
            action="source.resume",
            entity_type="source_health",
            entity_id=None,
            meta={"source": source},
        )
    )
    db.commit()
    return row


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


@router.get("/eval-health")
def eval_health(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Aggregate eval-quality signal for the dashboard (ADR 0006).

    Distinct from ``/admin/ops`` (infrastructure health) — this reports
    what fraction of analyses the Evaluator approved in the lookback
    window, e.g. "94% approved in the last 24h".
    """
    return eval_health_summary(db, datetime.datetime.now(datetime.UTC))


@router.get("/review-queue")
def list_review_queue(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[dict]:
    # A decided evaluation stays REVIEW forever (ADR 0012 — decisions
    # feed the offline golden dataset, they don't retroactively resolve
    # the live evaluation), so it must be excluded here explicitly or it
    # would never leave the queue. FakeSession has no join support, so
    # decided ids are fetched separately and diffed in Python — correct
    # under both the fake and the real ORM.
    decided_ids = {d.evaluation_id for d in db.query(ReviewDecision).all()}
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
        if r.status == EvalStatus.REVIEW and r.id not in decided_ids
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


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[User]:
    return db.query(User).order_by(User.created_at.desc()).all()


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
