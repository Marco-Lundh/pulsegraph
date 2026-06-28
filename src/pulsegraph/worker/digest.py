"""Daily digest batching for notifications (ADR 0016).

Users whose channel frequency is ``DAILY_DIGEST`` are not pushed one
message per item (the instant sink skips them, see ``worker.sinks``);
their notifications are persisted ``PENDING`` and this job batches them
into a single periodic message, then marks them ``SENT``. Runs on the
same scheduler as the pipeline (ADR 0015).

Delivery is best-effort, like the instant path: ``MultiSink`` isolates a
failing channel, and the dashboard ``Notification`` row stays as the
durable record regardless of push outcome.
"""

import datetime
import uuid
from collections import defaultdict

from sqlalchemy.orm import Session

from pulsegraph.config import Settings, get_settings
from pulsegraph.db.models import Analysis, Notification, NotificationSetting
from pulsegraph.domain.enums import NotificationFrequency, NotificationStatus
from pulsegraph.pipeline.contracts import NotificationDraft
from pulsegraph.worker.sinks import build_notification_sink


def user_wants_digest(db: Session, user_id: uuid.UUID) -> bool:
    """Whether *user_id* receives a daily digest rather than instant push.

    True only when the user has an active ``DAILY_DIGEST`` setting and no
    active ``INSTANT`` one, so a mixed config never both pushes instantly
    and digests the same item. Filtered in Python too, so it is correct
    under the FakeSession test double (mirrors ``worker.scheduler``).
    """
    settings = [
        s
        for s in db.query(NotificationSetting)
        .filter(NotificationSetting.user_id == user_id)
        .all()
        if s.user_id == user_id and s.is_active
    ]
    has_digest = any(
        s.frequency == NotificationFrequency.DAILY_DIGEST for s in settings
    )
    has_instant = any(
        s.frequency == NotificationFrequency.INSTANT for s in settings
    )
    return has_digest and not has_instant


def build_digest_draft(
    user_id: str, summaries: list[str], now: datetime.datetime
) -> NotificationDraft:
    """Combine a user's pending items into one digest notification."""
    count = len(summaries)
    plural = "s" if count != 1 else ""
    lines = "\n".join(f"- {summary}" for summary in summaries)
    return NotificationDraft(
        user_id=user_id,
        title=f"Your PulseGraph digest: {count} update{plural}",
        body=f"{count} new update{plural} since your last digest:\n\n{lines}",
        dedup_key=f"digest:{user_id}:{now.date().isoformat()}",
    )


def send_digests(
    db: Session,
    settings: Settings,
    *,
    now: datetime.datetime | None = None,
) -> dict:
    """Batch and deliver every pending digest, marking rows ``SENT``.

    Returns counts of users and notifications digested. Commits its own
    transaction.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    pending = [
        n
        for n in db.query(Notification)
        .filter(Notification.status == NotificationStatus.PENDING)
        .all()
        if n.status == NotificationStatus.PENDING
    ]

    by_user: dict[uuid.UUID, list[Notification]] = defaultdict(list)
    for notification in pending:
        by_user[notification.user_id].append(notification)

    sink = build_notification_sink(
        settings, db, NotificationFrequency.DAILY_DIGEST
    )
    digested = 0
    for user_id, notifications in by_user.items():
        summaries = []
        for notification in notifications:
            analysis = db.get(Analysis, notification.analysis_id)
            summaries.append(analysis.result if analysis else "(item)")
        sink.send(build_digest_draft(str(user_id), summaries, now))
        for notification in notifications:
            notification.status = NotificationStatus.SENT
            notification.delivered_at = now
        digested += len(notifications)

    db.commit()
    return {"users": len(by_user), "notifications": digested}


async def run_digest(ctx: dict) -> dict:
    """arq cron entry point: send all pending digests (ADR 0016)."""
    db = ctx["db_factory"]()
    try:
        return send_digests(db, get_settings())
    finally:
        db.close()
