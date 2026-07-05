"""Real notification delivery channels: email and webhook (ADR 0016).

These implement the same ``NotificationSink`` port as the offline
``InMemorySink``, so the Notifier node delivers over real channels
without changing a line. Each sink resolves the recipient for a draft's
user through an injected resolver and skips silently when that user has
not configured the channel (``resolve`` returns ``None``). A delivery
that is attempted but fails raises, honoring the port contract.

``MultiSink`` fans one draft out to several channels and isolates a
per-channel failure so a single channel outage never blocks another or
fails the whole pipeline run.
"""

import hashlib
import hmac
import json
import logging
import smtplib
from collections.abc import Callable, Sequence
from email.message import EmailMessage
from typing import NamedTuple

import httpx

from pulsegraph.pipeline.contracts import NotificationDraft, NotificationSink

logger = logging.getLogger(__name__)

# Maps a draft's ``user_id`` to its destination for one channel (an email
# address or a webhook URL), or ``None`` when the user has not enabled it.
Resolver = Callable[[str], str | None]


class SmtpTransport:
    """Sends an :class:`EmailMessage` over SMTP (ADR 0016).

    Kept separate from :class:`EmailSink` so the message-building logic
    can be tested without opening a socket: tests inject a fake transport
    with the same ``send`` method.
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        *,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout = timeout

    def send(self, message: EmailMessage) -> None:
        """Deliver ``message`` through the configured SMTP server."""
        with smtplib.SMTP(
            self._host, self._port, timeout=self._timeout
        ) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)


class _Transport:  # pragma: no cover - structural typing helper
    def send(self, message: EmailMessage) -> None: ...


class EmailSink:
    """Delivers a notification as an email (ADR 0016)."""

    def __init__(
        self,
        *,
        sender: str,
        transport: _Transport,
        resolve: Resolver,
    ) -> None:
        self._sender = sender
        self._transport = transport
        self._resolve = resolve

    def send(self, draft: NotificationDraft) -> None:
        """Email ``draft`` to the user, or skip if no address is set."""
        recipient = self._resolve(draft.user_id)
        if not recipient:
            return
        self._transport.send(self._build(recipient, draft))

    def _build(self, recipient: str, draft: NotificationDraft) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = recipient
        message["Subject"] = draft.title
        body = draft.body
        if draft.labels:
            body = f"{body}\n\nLabels: {', '.join(draft.labels)}"
        message.set_content(body)
        return message


# A poster has httpx.post's keyword-only contract; injectable for tests.
Poster = Callable[..., httpx.Response]


class WebhookSink:
    """Delivers a notification as a signed JSON webhook (ADR 0016).

    When a shared ``secret`` is configured each request carries an
    ``X-PulseGraph-Signature`` header (``sha256=<hex hmac>`` of the body)
    so the receiver can verify the call came from PulseGraph.
    """

    def __init__(
        self,
        *,
        resolve: Resolver,
        post: Poster = httpx.post,
        secret: str = "",
        timeout: float = 10.0,
    ) -> None:
        self._resolve = resolve
        self._post = post
        self._secret = secret
        self._timeout = timeout

    def send(self, draft: NotificationDraft) -> None:
        """POST ``draft`` to the user's webhook, or skip if none is set."""
        url = self._resolve(draft.user_id)
        if not url:
            return
        body = json.dumps(
            {
                "user_id": draft.user_id,
                "title": draft.title,
                "body": draft.body,
                "dedup_key": draft.dedup_key,
                "labels": list(draft.labels),
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._secret:
            signature = hmac.new(
                self._secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
            headers["X-PulseGraph-Signature"] = f"sha256={signature}"
        response = self._post(
            url, content=body, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()


class DeliveryResult(NamedTuple):
    """Per-channel outcome of one :meth:`MultiSink.send_detailed` call."""

    all_ok: bool
    any_ok: bool


class MultiSink:
    """Fans one draft out to several channels, isolating failures.

    A channel that raises is logged and skipped so a single channel
    outage never blocks the others or fails the pipeline run. The
    analysis is already persisted by the time the Notifier runs, so a
    transient delivery error should not undo a successful run (ADR 0016).
    """

    def __init__(self, sinks: Sequence[NotificationSink]) -> None:
        self._sinks = tuple(sinks)

    def send(self, draft: NotificationDraft) -> bool:
        """Deliver ``draft`` over every channel, best-effort.

        Returns whether every channel succeeded. The per-run instant path
        (the Notifier node) ignores this: one channel failing must never
        fail the run. See :meth:`send_detailed` for the digest job, which
        also needs to know whether *any* channel got through.
        """
        return self.send_detailed(draft).all_ok

    def send_detailed(self, draft: NotificationDraft) -> DeliveryResult:
        """Deliver ``draft`` over every channel, reporting both outcomes.

        ``all_ok`` mirrors :meth:`send`. ``any_ok`` is also ``True`` when
        there are no channels at all (vacuously, same as ``all_ok``). The
        digest job (ADR 0016) uses ``any_ok`` to tell "one of several
        channels is broken" (destination still reachable overall, so keep
        retrying) apart from "every channel is broken" (destination is
        genuinely dead, eligible for the retry-cap dead-letter).
        """
        all_ok = True
        any_ok = not self._sinks
        for sink in self._sinks:
            try:
                sink.send(draft)
                any_ok = True
            except Exception:
                all_ok = False
                logger.exception(
                    "notification delivery failed on %s for user %s",
                    type(sink).__name__,
                    draft.user_id,
                )
        return DeliveryResult(all_ok=all_ok, any_ok=any_ok)
