"""Operational health checks and spend signal (ADR 0020).

Infrastructure liveness — database, Redis/queue, Ollama — kept distinct
from the product eval-health metric (ADR 0006). Each check is a small,
dependency-injected function returning a :class:`CheckResult`, so the
readiness probe is testable without real infrastructure.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from sqlalchemy import text


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The outcome of one dependency check."""

    name: str
    ok: bool
    detail: str | None = None


class _Pingable(Protocol):
    def ping(self) -> Any: ...


def check_database(db: Any) -> CheckResult:
    """Verify the database answers a trivial query."""
    try:
        db.execute(text("SELECT 1"))
        return CheckResult("database", True)
    except Exception as exc:  # noqa: BLE001 - report any failure, never raise
        return CheckResult("database", False, str(exc))


def check_redis(client: _Pingable) -> CheckResult:
    """Verify Redis (the arq queue backend) responds to PING."""
    try:
        client.ping()
        return CheckResult("redis", True)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("redis", False, str(exc))


def check_ollama(
    base_url: str,
    *,
    get: Callable[..., httpx.Response] = httpx.get,
    timeout: float = 2.0,
) -> CheckResult:
    """Verify the local Ollama instance is reachable."""
    try:
        response = get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        return CheckResult("ollama", True)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("ollama", False, str(exc))


def summarize(results: list[CheckResult]) -> dict:
    """Fold per-dependency results into a readiness summary.

    ``status`` is ``ok`` only when every check passed, otherwise
    ``degraded`` — the signal a load balancer or operator alerts on.
    """
    healthy = all(r.ok for r in results)
    return {
        "status": "ok" if healthy else "degraded",
        "checks": {r.name: {"ok": r.ok, "detail": r.detail} for r in results},
    }


def spend_status(spend_usd: float, cap_usd: float, alert_ratio: float) -> dict:
    """Report cloud-model spend against the monthly cap (ADR 0008/0020).

    ``near_cap`` is the operator alert signal; ``over_cap`` means the cap
    is already reached and cloud calls are being refused.
    """
    ratio = spend_usd / cap_usd if cap_usd > 0 else 0.0
    return {
        "spend_usd": round(spend_usd, 6),
        "cap_usd": cap_usd,
        "ratio": round(ratio, 4),
        "near_cap": ratio >= alert_ratio,
        "over_cap": spend_usd >= cap_usd,
    }
