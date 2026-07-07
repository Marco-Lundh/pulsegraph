"""Retry failed instant notification deliveries (ADR 0016).

Instant email/webhook delivery is attempted in the Notifier node while the
run executes; :func:`pulsegraph.worker.persistence.persist_run_results`
writes a per-channel ``Notification`` row for each attempt — ``SENT`` when
it got through, ``PENDING`` when it failed. This job picks up the
``PENDING`` email/webhook rows and resends them on exactly the channel they
failed on, so a transient outage (SMTP hiccup, momentarily unreachable
webhook) is recovered without waiting for the item to reappear.

It mirrors the daily digest job (:mod:`pulsegraph.worker.digest`): delivery
is best-effort, a successful resend flips the row to ``SENT``, and a row
that keeps failing has its ``attempts`` incremented until it reaches
``Settings.instant_max_attempts`` and is dead-lettered (``FAILED``) instead
of being retried forever against a permanently broken destination. A row
whose channel the user has since disabled (the resolver returns no
destination) is dead-lettered immediately — it can never be delivered.

Digest ``PENDING`` rows are the dashboard channel and are handled by the
digest job, so filtering to the email/webhook channels keeps the two retry
paths cleanly separate.
"""

import datetime
from collections import defaultdict

from sqlalchemy.orm import Session

from pulsegraph.config import Settings, get_settings
from pulsegraph.db.models import Analysis, Notification
from pulsegraph.domain.enums import (
    NotificationChannel,
    NotificationFrequency,
    NotificationStatus,
)
from pulsegraph.pipeline.contracts import NotificationDraft
from pulsegraph.pipeline.delivery import ChannelOutcome
from pulsegraph.worker.sinks import build_channel_sink

_INSTANT_CHANNELS = (NotificationChannel.EMAIL, NotificationChannel.WEBHOOK)


def _rebuild_draft(
    db: Session, notification: Notification
) -> NotificationDraft:
    """Reconstruct the draft for a stored notification from its analysis.

    Labels are not persisted, so (like the digest job) the resend carries
    the analysis summary as title/body without them.
    """
    analysis = db.get(Analysis, notification.analysis_id)
    summary = (analysis.result if analysis else "") or ""
    title = summary.splitlines()[0] if summary else "Update"
    return NotificationDraft(
        user_id=str(notification.user_id),
        title=title,
        body=summary,
        dedup_key=notification.dedup_key,
    )


def retry_instant_notifications(
    db: Session,
    settings: Settings,
    *,
    now: datetime.datetime | None = None,
) -> dict:
    """Resend every pending instant email/webhook notification.

    A row is flipped to ``SENT`` on a successful resend; a failed resend
    increments ``attempts`` and dead-letters (``FAILED``) once it reaches
    ``Settings.instant_max_attempts``; a row whose channel the user has
    disabled is dead-lettered immediately. Channels turned off globally are
    left untouched (``PENDING``) to be retried when re-enabled. Commits its
    own transaction. Returns counts of rows resent, still failing, and
    dead-lettered this run.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    # FakeSession.filter() is a no-op in tests, so re-check in Python too
    # (mirrors the pattern used throughout worker/*.py).
    pending = [
        n
        for n in db.query(Notification)
        .filter(
            Notification.status == NotificationStatus.PENDING,
            Notification.channel.in_(_INSTANT_CHANNELS),
        )
        .all()
        if n.status == NotificationStatus.PENDING
        and n.channel in _INSTANT_CHANNELS
    ]

    by_channel: dict[NotificationChannel, list[Notification]] = defaultdict(
        list
    )
    for notification in pending:
        by_channel[notification.channel].append(notification)

    resent = 0
    still_failing = 0
    dead_lettered = 0
    for channel, notifications in by_channel.items():
        sink = build_channel_sink(
            settings, db, channel, NotificationFrequency.INSTANT
        )
        if sink is None:
            # Channel disabled globally: leave the rows PENDING so they are
            # retried if it is re-enabled (mirrors the digest job).
            continue
        for notification in notifications:
            outcome = sink.deliver(_rebuild_draft(db, notification))
            if outcome is ChannelOutcome.SENT:
                notification.status = NotificationStatus.SENT
                notification.delivered_at = now
                resent += 1
            elif outcome is ChannelOutcome.SKIPPED:
                # The user disabled this channel since the send: it can
                # never be delivered, so dead-letter it now.
                notification.status = NotificationStatus.FAILED
                dead_lettered += 1
            else:
                notification.attempts += 1
                still_failing += 1
                if notification.attempts >= settings.instant_max_attempts:
                    notification.status = NotificationStatus.FAILED
                    dead_lettered += 1

    db.commit()
    return {
        "resent": resent,
        "still_failing": still_failing,
        "dead_lettered": dead_lettered,
    }


async def run_instant_retry(ctx: dict) -> dict:
    """arq cron entry point: retry all pending instant sends (ADR 0016)."""
    db = ctx["db_factory"]()
    try:
        return retry_instant_notifications(db, get_settings())
    finally:
        db.close()
