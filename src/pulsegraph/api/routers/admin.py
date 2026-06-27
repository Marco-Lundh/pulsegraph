"""Admin-only endpoints (ADR 0020/0021)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_db, require_admin
from pulsegraph.api.schemas import (
    ReviewDecisionCreate,
    SourceHealthOut,
)
from pulsegraph.db.models import (
    AuditLogEntry,
    Evaluation,
    ReviewDecision,
    SourceHealth,
    User,
)
from pulsegraph.domain.enums import EvalStatus

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/source-health", response_model=list[SourceHealthOut])
def list_source_health(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SourceHealth]:
    return db.query(SourceHealth).all()


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
