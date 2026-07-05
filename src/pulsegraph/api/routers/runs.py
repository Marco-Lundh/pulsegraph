"""Pipeline run history — tenant-scoped (ADR 0007/0015)."""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_current_user, get_db
from pulsegraph.api.schemas import ItemResultOut, RunOut
from pulsegraph.db.models import (
    Analysis,
    Evaluation,
    Item,
    Notification,
    PipelineRun,
    User,
    Watch,
)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
def list_runs(
    watch_id: uuid.UUID | None = None,
    since: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PipelineRun]:
    """List the caller's pipeline runs, optionally scoped to a watch.

    ``since`` bounds the result to runs started on or after that instant
    (e.g. a 7-day dashboard chart), so callers don't have to pull the
    caller's entire run history on every poll.
    """
    # Scope to the authenticated user's watches only. Filtered in Python
    # too, so it is correct under the FakeSession test double whose
    # filter is a no-op.
    user_watch_ids = {
        w.id
        for w in db.query(Watch).filter(Watch.user_id == user.id).all()
        if w.user_id == user.id
    }
    q = db.query(PipelineRun).filter(PipelineRun.watch_id.in_(user_watch_ids))
    if watch_id is not None:
        q = q.filter(PipelineRun.watch_id == watch_id)
    if since is not None:
        q = q.filter(PipelineRun.started_at >= since)
    runs = q.order_by(PipelineRun.started_at.desc()).all()
    runs = [r for r in runs if r.watch_id in user_watch_ids]
    if watch_id is not None:
        runs = [r for r in runs if r.watch_id == watch_id]
    if since is not None:
        runs = [r for r in runs if r.started_at >= since]
    runs.sort(key=lambda r: r.started_at, reverse=True)
    return runs


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PipelineRun:
    """Return one of the caller's runs (ADR 0007/0015).

    404 if the run does not belong to one of the caller's watches, so a run
    detail page can deep-link by id without leaking other tenants' runs.
    """
    user_watch_ids = {
        w.id
        for w in db.query(Watch).filter(Watch.user_id == user.id).all()
        if w.user_id == user.id
    }
    run = db.get(PipelineRun, run_id)
    if run is None or run.watch_id not in user_watch_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return run


@router.get("/{run_id}/items", response_model=list[ItemResultOut])
def list_run_items(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ItemResultOut]:
    """Per-item results for one of the caller's runs (ADR 0002/0006).

    For every item the run analyzed, returns which model produced the
    analysis (ADR 0002) and how the Evaluator graded it — relevance,
    confidence, status (ADR 0006) — plus whether it surfaced a dashboard
    notification. 404 if the run is not one of the caller's own.

    The item -> analysis -> evaluation -> notification chain is stitched in
    Python: the FakeSession test double has no join support, and loading
    each table separately keeps the ownership filter correct under its
    no-op ``filter`` (same pattern as ``list_runs`` and ``persistence``).
    """
    # Ownership: the run must belong to one of the caller's watches.
    user_watch_ids = {
        w.id
        for w in db.query(Watch).filter(Watch.user_id == user.id).all()
        if w.user_id == user.id
    }
    run = db.get(PipelineRun, run_id)
    if run is None or run.watch_id not in user_watch_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    items = [
        it
        for it in db.query(Item).filter(Item.run_id == run_id).all()
        if it.run_id == run_id and it.watch_id in user_watch_ids
    ]
    if not items:
        return []
    item_ids = {it.id for it in items}

    analyses = [
        a
        for a in db.query(Analysis)
        .filter(Analysis.item_id.in_(item_ids))
        .all()
        if a.item_id in item_ids
    ]
    analysis_by_item = {a.item_id: a for a in analyses}
    analysis_ids = {a.id for a in analyses}

    eval_by_analysis = {}
    notified_analysis_ids: set[uuid.UUID] = set()
    if analysis_ids:
        eval_by_analysis = {
            e.analysis_id: e
            for e in db.query(Evaluation)
            .filter(Evaluation.analysis_id.in_(analysis_ids))
            .all()
            if e.analysis_id in analysis_ids
        }
        notified_analysis_ids = {
            row.analysis_id
            for row in db.query(Notification.analysis_id)
            .filter(Notification.analysis_id.in_(analysis_ids))
            .all()
            if row.analysis_id in analysis_ids
        }

    results: list[ItemResultOut] = []
    for it in items:
        analysis = analysis_by_item.get(it.id)
        if analysis is None:
            # Every persisted item carries an analysis; skip defensively.
            continue
        evaluation = eval_by_analysis.get(analysis.id)
        results.append(
            ItemResultOut(
                item_id=it.id,
                external_id=it.external_id,
                source=it.source,
                fetched_at=it.fetched_at,
                model_used=analysis.model_used,
                model_version=analysis.model_version,
                summary=analysis.result,
                analysis_confidence=analysis.confidence,
                relevance_score=(
                    evaluation.relevance_score if evaluation else None
                ),
                eval_confidence=evaluation.confidence if evaluation else None,
                eval_status=evaluation.status if evaluation else None,
                notified=analysis.id in notified_analysis_ids,
            )
        )
    results.sort(key=lambda r: r.fetched_at, reverse=True)
    return results
