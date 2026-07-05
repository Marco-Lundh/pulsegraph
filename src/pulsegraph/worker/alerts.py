"""Route operator alerts to an operator channel (ADR 0020).

The same operational summary that backs ``GET /admin/ops`` is evaluated
on a schedule; when any signal is firing (worker down, queue backlog,
spend near the cap, sources paused, slow runs) a message is pushed to
the configured operator webhook. Off by default — with no webhook set
the system is poll-only.

Delivery is best-effort and signed like the user webhook channel
(ADR 0016): a transient operator-endpoint failure is logged, not raised,
so the alert job never crashes the worker.

**Throttle/dedup:** each alert kind (see ``AlertSignal.kind``) is pushed
at most once per ``Settings.alert_throttle_seconds`` window, tracked in
Redis (``should_send_alert``/``clear_alert``). Without this, a condition
that stays firing (e.g. a worker that stays down) would re-alert on
every 15-minute sweep indefinitely. A kind that stops firing has its
window cleared immediately, so a resolved-then-recurring incident is
treated as new rather than suppressed by a stale window.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from pulsegraph.api.health import (
    ALERT_KINDS,
    collect_alerts,
    operational_summary,
)
from pulsegraph.config import Settings, get_settings
from pulsegraph.redis_client import clear_alert, should_send_alert

logger = logging.getLogger(__name__)


def send_operator_alert(
    messages: list[str],
    settings: Settings,
    *,
    post=httpx.post,
) -> bool:
    """POST firing alerts to the operator webhook; return whether sent.

    A no-op (returns False) when there is nothing to send or no operator
    webhook is configured. Signs the body with an
    ``X-PulseGraph-Signature`` header when a secret is set.
    """
    if not messages or not settings.operator_webhook_url:
        return False
    body = json.dumps({"source": "pulsegraph", "alerts": messages}).encode(
        "utf-8"
    )
    headers = {"Content-Type": "application/json"}
    if settings.operator_webhook_secret:
        signature = hmac.new(
            settings.operator_webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        headers["X-PulseGraph-Signature"] = f"sha256={signature}"
    response = post(
        settings.operator_webhook_url,
        content=body,
        headers=headers,
        timeout=10.0,
    )
    response.raise_for_status()
    return True


def push_operator_alerts(db: Any, redis: Any, settings: Settings) -> dict:
    """Evaluate operator alerts and push whichever aren't throttled.

    Each firing kind is checked against its own cooldown window
    (``should_send_alert``); a kind that isn't firing this sweep has its
    window cleared (``clear_alert``) so a later recurrence isn't silently
    swallowed by a stale window from a prior, since-resolved incident.
    Returns counts of alerts firing, alerts throttled (firing but
    suppressed this sweep), and whether a push was sent.

    A cooldown window is only spent once delivery is actually attempted
    for it; if ``send_operator_alert`` raises (a transient operator-
    endpoint outage), every claimed kind's window is cleared again so the
    next sweep retries instead of the incident going unreported for a
    full ``alert_throttle_seconds`` window with no sign anything failed.
    """
    summary = operational_summary(db, redis, settings)
    firing = collect_alerts(summary)
    firing_kinds = {alert.kind for alert in firing}
    for kind in ALERT_KINDS:
        if kind not in firing_kinds:
            clear_alert(redis, kind)

    claimed = [
        alert
        for alert in firing
        if should_send_alert(
            redis, alert.kind, settings.alert_throttle_seconds
        )
    ]
    sent = False
    if claimed:
        try:
            sent = send_operator_alert(
                [alert.message for alert in claimed], settings
            )
        except Exception:
            logger.exception("operator alert delivery failed")
            for alert in claimed:
                clear_alert(redis, alert.kind)
    return {
        "alerts": len(firing),
        "throttled": len(firing) - len(claimed),
        "sent": sent,
    }


async def run_alerts(ctx: dict) -> dict:
    """arq cron entry point: push firing operator alerts (ADR 0020)."""
    settings = get_settings()
    db = ctx["db_factory"]()
    try:
        return push_operator_alerts(db, ctx["redis"], settings)
    finally:
        db.close()
