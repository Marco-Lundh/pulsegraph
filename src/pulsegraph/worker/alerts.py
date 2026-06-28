"""Route operator alerts to an operator channel (ADR 0020).

The same operational summary that backs ``GET /admin/ops`` is evaluated
on a schedule; when any signal is firing (worker down, queue backlog,
spend near the cap, sources paused, slow runs) a single message is pushed
to the configured operator webhook. Off by default — with no webhook set
the system is poll-only.

Delivery is best-effort and signed like the user webhook channel
(ADR 0016): a transient operator-endpoint failure is logged, not raised,
so the alert job never crashes the worker.
"""

import hashlib
import hmac
import json
import logging

import httpx

from pulsegraph.api.health import collect_alerts, operational_summary
from pulsegraph.config import Settings, get_settings

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


async def run_alerts(ctx: dict) -> dict:
    """arq cron entry point: push firing operator alerts (ADR 0020)."""
    settings = get_settings()
    db = ctx["db_factory"]()
    try:
        summary = operational_summary(db, ctx["redis"], settings)
    finally:
        db.close()

    alerts = collect_alerts(summary)
    sent = False
    if alerts:
        try:
            sent = send_operator_alert(alerts, settings)
        except Exception:
            logger.exception("operator alert delivery failed")
    return {"alerts": len(alerts), "sent": sent}
