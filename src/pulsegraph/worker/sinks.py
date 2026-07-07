"""Assemble the enabled notification channels for one run (ADR 0016).

Built per run against the run's live database session, so resolving a
user's destination is a plain read on the session already in hand — no
extra session is opened per notification. The resulting sink is swapped
into the pipeline deps for that run (see ``worker.tasks``).
"""

import uuid

from sqlalchemy.orm import Session

from pulsegraph.config import Settings
from pulsegraph.db.models import NotificationSetting, User
from pulsegraph.domain.enums import NotificationChannel, NotificationFrequency
from pulsegraph.pipeline.contracts import NotificationSink
from pulsegraph.pipeline.delivery import (
    EmailSink,
    MultiSink,
    Resolver,
    SmtpTransport,
    WebhookSink,
)


def _destination_resolver(
    db: Session,
    channel: NotificationChannel,
    frequency: NotificationFrequency,
) -> Resolver:
    """Resolve a user's destination for ``channel`` at ``frequency``.

    Returns ``None`` when the user has no active setting for the channel
    at that frequency, so the sink skips them. This is what separates
    instant from digest delivery: the instant sink only resolves
    ``INSTANT`` settings, the digest sink only ``DAILY_DIGEST`` (ADR 0016).
    An email setting with no explicit destination falls back to the
    user's account email.
    """

    def resolve(user_id: str) -> str | None:
        uid = uuid.UUID(user_id)
        # FakeSession.filter() is a no-op in tests, so re-check every
        # condition in Python too (mirrors the pattern used throughout
        # worker/*.py) — otherwise the first matching-frequency row in the
        # whole store wins, leaking another user's destination.
        setting = next(
            (
                s
                for s in db.query(NotificationSetting)
                .filter(
                    NotificationSetting.user_id == uid,
                    NotificationSetting.channel == channel,
                    NotificationSetting.frequency == frequency,
                    NotificationSetting.is_active.is_(True),
                )
                .all()
                if s.user_id == uid
                and s.channel == channel
                and s.frequency == frequency
                and s.is_active
            ),
            None,
        )
        if setting is None:
            return None
        if setting.destination:
            return setting.destination
        if channel is NotificationChannel.EMAIL:
            user = db.get(User, uid)
            return user.email if user else None
        return None

    return resolve


def _build_email_sink(
    settings: Settings, db: Session, frequency: NotificationFrequency
) -> EmailSink | None:
    """The email sink if the channel is enabled globally, else None."""
    if not settings.email_enabled:
        return None
    return EmailSink(
        sender=settings.email_from,
        transport=SmtpTransport(
            settings.smtp_host,
            settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
        ),
        resolve=_destination_resolver(
            db, NotificationChannel.EMAIL, frequency
        ),
    )


def _build_webhook_sink(
    settings: Settings, db: Session, frequency: NotificationFrequency
) -> WebhookSink | None:
    """The webhook sink if the channel is enabled globally, else None."""
    if not settings.webhook_enabled:
        return None
    return WebhookSink(
        resolve=_destination_resolver(
            db, NotificationChannel.WEBHOOK, frequency
        ),
        secret=settings.webhook_signing_secret,
    )


def build_notification_sink(
    settings: Settings,
    db: Session,
    frequency: NotificationFrequency = NotificationFrequency.INSTANT,
) -> MultiSink:
    """Build a ``MultiSink`` of the channels enabled in *settings*.

    Only users whose channel setting matches *frequency* are delivered to,
    so the same builder produces the instant sink (used per run) and the
    digest sink (used by the daily digest job). Typed as the concrete
    ``MultiSink`` (not the ``NotificationSink`` protocol) so callers can
    rely on ``send()``'s per-user success/failure return value (ADR 0016).
    """
    candidates = (
        _build_email_sink(settings, db, frequency),
        _build_webhook_sink(settings, db, frequency),
    )
    sinks: list[NotificationSink] = [s for s in candidates if s is not None]
    return MultiSink(sinks)


def build_channel_sink(
    settings: Settings,
    db: Session,
    channel: NotificationChannel,
    frequency: NotificationFrequency = NotificationFrequency.INSTANT,
) -> EmailSink | WebhookSink | None:
    """The single sink for one channel, or None when it is off globally.

    Used by the instant-retry job (:mod:`pulsegraph.worker.retry`) to
    resend a failed notification on exactly the channel it failed on,
    without fanning out to the others (ADR 0016).
    """
    if channel is NotificationChannel.EMAIL:
        return _build_email_sink(settings, db, frequency)
    if channel is NotificationChannel.WEBHOOK:
        return _build_webhook_sink(settings, db, frequency)
    return None
