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
from pulsegraph.domain.enums import NotificationChannel
from pulsegraph.pipeline.contracts import NotificationSink
from pulsegraph.pipeline.delivery import (
    EmailSink,
    MultiSink,
    Resolver,
    SmtpTransport,
    WebhookSink,
)


def _destination_resolver(
    db: Session, channel: NotificationChannel
) -> Resolver:
    """Resolve a user's destination for ``channel`` from their settings.

    Returns ``None`` when the user has no active setting for the channel,
    so the sink skips them. An email setting with no explicit destination
    falls back to the user's account email (ADR 0016).
    """

    def resolve(user_id: str) -> str | None:
        uid = uuid.UUID(user_id)
        setting = (
            db.query(NotificationSetting)
            .filter(
                NotificationSetting.user_id == uid,
                NotificationSetting.channel == channel,
                NotificationSetting.is_active.is_(True),
            )
            .first()
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


def build_notification_sink(
    settings: Settings, db: Session
) -> NotificationSink:
    """Build a ``MultiSink`` of the channels enabled in *settings*."""
    sinks: list[NotificationSink] = []
    if settings.email_enabled:
        sinks.append(
            EmailSink(
                sender=settings.email_from,
                transport=SmtpTransport(
                    settings.smtp_host,
                    settings.smtp_port,
                    username=settings.smtp_username,
                    password=settings.smtp_password,
                    use_tls=settings.smtp_use_tls,
                ),
                resolve=_destination_resolver(db, NotificationChannel.EMAIL),
            )
        )
    if settings.webhook_enabled:
        sinks.append(
            WebhookSink(
                resolve=_destination_resolver(db, NotificationChannel.WEBHOOK),
                secret=settings.webhook_signing_secret,
            )
        )
    return MultiSink(sinks)
