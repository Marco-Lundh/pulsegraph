"""Persist a completed run's provenance chain to the database.

The pipeline produces its records in memory (items, analyses,
evaluations, notification drafts); this module writes them through so
the dashboard can read delivered notifications and so deduplication and
delivery stay idempotent across runs (ADR 0003/0016).

The dashboard is just another delivery channel: a ``Notification`` row
is written for exactly the drafts the Notifier emitted this run (the new,
approved items), reusing the same dedup identity as the email and webhook
channels. The full ``Item -> Analysis -> Evaluation`` chain is persisted
for every new item so each notification has its provenance.

Each item is written inside its own savepoint: if a row already exists
(an item whose hash aged out of the dedup window and reappeared), the
unique constraint trips, the savepoint rolls back, and the run continues
instead of failing.
"""

import datetime
import uuid

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulsegraph.db.models import (
    Analysis,
    Evaluation,
    Item,
    Notification,
    PipelineRun,
    Watch,
)
from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    NotificationChannel,
    NotificationStatus,
)
from pulsegraph.pipeline.agents import build_notification_draft
from pulsegraph.pipeline.contracts import EvaluationRecord
from pulsegraph.pipeline.state import PipelineState


def load_dedup_memory(
    db: Session,
    user_id: uuid.UUID,
    *,
    lookback_days: int = 90,
) -> tuple[set[str], set[str]]:
    """Return the user's recent seen content hashes and sent dedup keys.

    Seeds a run's cross-run memory so the Fetcher skips already-stored
    items and the Notifier never re-delivers (ADR 0003/0016). Only the
    two scalar columns are selected (never embedding vectors), and only
    rows from the last ``lookback_days`` are loaded to bound the lookup;
    older duplicates are caught by the unique constraints in
    :func:`persist_run_results`. Notifications still PENDING (queued for a
    digest, ADR 0016) count as already-sent so a digest user's item is
    not re-queued on every run before the digest goes out.
    """
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        days=lookback_days
    )
    seen = {
        row.content_hash
        for row in db.query(Item.content_hash)
        .filter(Item.user_id == user_id, Item.fetched_at >= cutoff)
        .all()
    }
    sent = {
        row.dedup_key
        for row in db.query(Notification.dedup_key)
        .filter(
            Notification.user_id == user_id,
            or_(
                Notification.delivered_at >= cutoff,
                Notification.status == NotificationStatus.PENDING,
            ),
        )
        .all()
    }
    return seen, sent


def persist_run_results(
    db: Session,
    run: PipelineRun,
    watch: Watch,
    state: PipelineState,
    *,
    embedding_model: str,
    model_versions: dict[ModelKind, str],
    now: datetime.datetime | None = None,
    digest: bool = False,
) -> int:
    """Write the run's items, analyses, evaluations and notifications.

    Returns the number of notifications written. Adds rows to *db*
    without committing; the caller commits as part of the run's
    transaction. When *digest* is true the notification is recorded
    ``PENDING`` (queued for the daily digest job, ADR 0016) instead of
    ``SENT``; instant delivery already happened in the Notifier node.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    embeddings = state.get("embeddings", {})
    # The Notifier already applied cross-run dedup, so its drafts are the
    # exact set of new, approved items to surface on the dashboard.
    new_keys = {draft.dedup_key for draft in state.get("notifications", [])}

    notified = 0
    for evaluation in state.get("evaluations", []):
        try:
            with db.begin_nested():
                created = _persist_evaluation(
                    db,
                    run,
                    watch,
                    evaluation,
                    embeddings=embeddings,
                    embedding_model=embedding_model,
                    model_versions=model_versions,
                    new_keys=new_keys,
                    now=now,
                    digest=digest,
                )
        except IntegrityError:
            # Already stored by an earlier run; the savepoint rolled back.
            continue
        if created:
            notified += 1

    return notified


def _persist_evaluation(
    db: Session,
    run: PipelineRun,
    watch: Watch,
    evaluation: EvaluationRecord,
    *,
    embeddings: dict[str, list[float]],
    embedding_model: str,
    model_versions: dict[ModelKind, str],
    new_keys: set[str],
    now: datetime.datetime,
    digest: bool = False,
) -> bool:
    """Persist one evaluation's chain; return whether a notif was written."""
    analysis_record = evaluation.analysis
    fetched = analysis_record.item
    content_hash = analysis_record.content_hash
    result = analysis_record.result

    item = Item(
        user_id=watch.user_id,
        watch_id=watch.id,
        run_id=run.id,
        source=fetched.source,
        external_id=fetched.external_id,
        raw_payload=fetched.raw,
        content_hash=content_hash,
        embedding=embeddings.get(content_hash),
        embedding_model=embedding_model,
    )
    db.add(item)
    db.flush()

    analysis = Analysis(
        item_id=item.id,
        model_used=result.model,
        model_version=model_versions.get(result.model, result.model.value),
        result=result.summary,
        confidence=result.confidence,
    )
    db.add(analysis)
    db.flush()

    db.add(
        Evaluation(
            analysis_id=analysis.id,
            relevance_score=result.relevance,
            confidence=result.confidence,
            status=evaluation.status,
        )
    )

    if evaluation.status is not EvalStatus.APPROVED:
        return False
    draft = build_notification_draft(str(watch.user_id), evaluation)
    if draft.dedup_key not in new_keys:
        return False
    new_keys.discard(draft.dedup_key)
    status = NotificationStatus.PENDING if digest else NotificationStatus.SENT
    db.add(
        Notification(
            user_id=watch.user_id,
            analysis_id=analysis.id,
            channel=NotificationChannel.DASHBOARD,
            dedup_key=draft.dedup_key,
            status=status,
            delivered_at=None if digest else now,
            attempts=0,
        )
    )
    # Flush so a duplicate (user_id, dedup_key) trips inside the savepoint.
    db.flush()
    return True
