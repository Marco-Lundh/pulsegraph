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
import logging
import uuid

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulsegraph.db.models import (
    Analysis,
    CostEvent,
    Evaluation,
    Item,
    Notification,
    PipelineRun,
    SourceHealth,
    Watch,
)
from pulsegraph.domain.constants import EMBEDDING_DIM
from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    NotificationChannel,
    NotificationStatus,
    PromptRole,
    SourceKind,
    SourceStatus,
)
from pulsegraph.pipeline.agents import build_notification_draft
from pulsegraph.pipeline.contracts import EvaluationRecord
from pulsegraph.pipeline.delivery import ChannelDelivery, ChannelOutcome
from pulsegraph.pipeline.prompts import active_prompt_id
from pulsegraph.pipeline.state import PipelineState
from pulsegraph.worker.similarity import find_similar_items

logger = logging.getLogger(__name__)


def _validated_embedding(vector: list[float] | None) -> list[float] | None:
    """Drop an embedding whose dimension doesn't match the stored column.

    An embedding-model swap that changes the vector dimension would
    otherwise fail the insert or silently corrupt dedup/similarity (ADR
    0014). We store ``None`` instead and log it, so the run still succeeds
    and the re-embed job (:mod:`pulsegraph.worker.reembed`) can fill the
    vector in later against the correct model.
    """
    if vector is not None and len(vector) != EMBEDDING_DIM:
        logger.warning(
            "dropping embedding with dim %d (expected %d)",
            len(vector),
            EMBEDDING_DIM,
        )
        return None
    return vector


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


def mark_source_paused(
    db: Session,
    source: SourceKind,
    detail: str,
    *,
    now: datetime.datetime | None = None,
) -> None:
    """Flag *source* as paused for schema drift (ADR 0010).

    Upserts the single ``source_health`` row keyed by source: the Watcher
    then skips triggering that source until it is resumed (manually via the
    admin API or a plugin fix). Adds/updates the row without committing;
    the caller owns the transaction.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    row = db.query(SourceHealth).filter(SourceHealth.source == source).first()
    if row is None:
        db.add(
            SourceHealth(
                source=source,
                status=SourceStatus.PAUSED,
                drift_detail=detail,
                last_checked_at=now,
            )
        )
        return
    row.status = SourceStatus.PAUSED
    row.drift_detail = detail
    row.last_checked_at = now


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
    similarity_threshold: float = 1.0,
    deliveries: dict[str, list[ChannelDelivery]] | None = None,
) -> int:
    """Write the run's items, analyses, evaluations and notifications.

    Returns the number of notifications written. Adds rows to *db*
    without committing; the caller commits as part of the run's
    transaction. When *digest* is true the notification is recorded
    ``PENDING`` (queued for the daily digest job, ADR 0016) instead of
    ``SENT``; instant delivery already happened in the Notifier node.

    ``deliveries`` is the Notifier sink's per-channel delivery log for this
    run (dedup_key -> outcomes). For each surfaced item, a per-channel
    ``Notification`` row is written alongside the dashboard row so instant
    email/webhook delivery is tracked and a failure can be retried (ADR
    0016). Digest users are skipped by the instant sink, so their log is
    empty and only the dashboard row is written, as before.

    ``similarity_threshold`` (0-1) enables semantic dedup (ADR 0014): a new
    item whose vector is at least this cosine-similar to one from an earlier
    run is still persisted but not re-notified. The default 1.0 disables it
    (only an exact-distance match would suppress); the worker passes the
    configured threshold.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    deliveries = deliveries or {}
    embeddings = state.get("embeddings", {})
    # The Notifier already applied cross-run dedup, so its drafts are the
    # exact set of new, approved items to surface on the dashboard.
    new_keys = {draft.dedup_key for draft in state.get("notifications", [])}
    # Pin the active analyzer prompt so every Analysis records the exact
    # versioned prompt that produced it (ADR 0011). Resolved once per run.
    prompt_id = active_prompt_id(db, PromptRole.ANALYZER)

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
                    prompt_id=prompt_id,
                    similarity_threshold=similarity_threshold,
                    deliveries=deliveries,
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
    prompt_id: uuid.UUID | None = None,
    similarity_threshold: float = 1.0,
    deliveries: dict[str, list[ChannelDelivery]] | None = None,
) -> bool:
    """Persist one evaluation's chain; return whether a notif was written."""
    deliveries = deliveries or {}
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
        embedding=_validated_embedding(embeddings.get(content_hash)),
        embedding_model=embedding_model,
    )
    db.add(item)
    db.flush()

    analysis = Analysis(
        item_id=item.id,
        prompt_id=prompt_id,
        model_used=result.model,
        model_version=model_versions.get(result.model, result.model.value),
        params=result.params,
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

    # Record the model call in the per-user, per-run cost ledger (ADR 0008).
    # Local calls are free (cost 0) but still logged for token volume; the
    # global monthly cap is metered separately in Redis.
    db.add(
        CostEvent(
            user_id=watch.user_id,
            run_id=run.id,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
        )
    )

    if evaluation.status is not EvalStatus.APPROVED:
        return False
    # Semantic dedup (ADR 0014): if a same-model near-duplicate from an
    # earlier run is already stored for this user, keep the item for
    # provenance but suppress its dashboard notification — a reworded repost
    # has a different content hash (so the exact-hash dedup misses it) but a
    # near-identical vector. Excludes this run so the item never matches
    # itself or its batch siblings. Scope: this suppresses the persisted
    # dashboard channel; instant email/webhook (if enabled) already fired in
    # the Notifier node, so with the local-first dashboard-only default this
    # is complete. A no-op when there is no vector, or when similarity is
    # unavailable (the query degrades to []).
    if item.embedding is not None and find_similar_items(
        db,
        user_id=watch.user_id,
        embedding=item.embedding,
        embedding_model=embedding_model,
        threshold=similarity_threshold,
        exclude_run_id=run.id,
        limit=1,
    ):
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
    # Per-channel instant delivery rows (ADR 0016): the Notifier already
    # attempted email/webhook for this draft and the sink recorded the
    # outcome per channel. Write a row for each real attempt so its status
    # is tracked and a transient failure can be retried; a SKIPPED channel
    # (the user has not enabled it) recorded nothing, so no row is written.
    for delivery in deliveries.get(draft.dedup_key, ()):
        if delivery.outcome is ChannelOutcome.SKIPPED:
            continue
        sent = delivery.outcome is ChannelOutcome.SENT
        db.add(
            Notification(
                user_id=watch.user_id,
                analysis_id=analysis.id,
                channel=delivery.channel,
                dedup_key=draft.dedup_key,
                status=(
                    NotificationStatus.SENT
                    if sent
                    else NotificationStatus.PENDING
                ),
                delivered_at=now if sent else None,
                attempts=0,
            )
        )
    # Flush so a duplicate (user_id, dedup_key, channel) trips the savepoint.
    db.flush()
    return True
