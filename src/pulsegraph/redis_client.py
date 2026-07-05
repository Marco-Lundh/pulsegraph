"""Redis helpers: rate limiting, fetch caching, cost tracking (ADR 0022)."""

import datetime
import json
import uuid

import redis as redis_lib


def make_redis(url: str) -> redis_lib.Redis:
    return redis_lib.Redis.from_url(url, decode_responses=True)


def check_rate(r: redis_lib.Redis, user_id: uuid.UUID, limit: int) -> bool:
    """Return True if the user is within quota, False otherwise.

    Atomically increments the hourly counter. The window key carries a
    TTL so old counters expire automatically — no cleanup job needed.
    """
    now = datetime.datetime.now(datetime.UTC)
    window_epoch = int(
        now.replace(minute=0, second=0, microsecond=0).timestamp()
    )
    key = f"ratelimit:{user_id}:{window_epoch}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, 3600)
    return count <= limit


def check_fixed_window(
    r: redis_lib.Redis, key: str, limit: int, window_seconds: int
) -> bool:
    """Return True if *key* is within *limit* for the current window.

    A generic fixed-window counter: atomically increments a per-window
    counter under ``{key}:{window}`` and gives it a TTL so it expires on
    its own. Used to brute-force-protect the auth endpoints keyed on the
    caller's IP (ADR 0021); ``check_rate`` is the per-user hourly variant.
    """
    now = datetime.datetime.now(datetime.UTC)
    window = int(now.timestamp()) // window_seconds
    full_key = f"{key}:{window}"
    count = r.incr(full_key)
    if count == 1:
        r.expire(full_key, window_seconds)
    return count <= limit


def get_fetch_cache(r: redis_lib.Redis, key: str) -> list | None:
    """Return the cached fetch result for *key*, or None on a miss."""
    raw = r.get(key)
    if raw is None:
        return None
    return json.loads(raw)


def set_fetch_cache(
    r: redis_lib.Redis, key: str, data: list, ttl: int
) -> None:
    """Store *data* under *key* with a TTL in seconds."""
    r.setex(key, ttl, json.dumps(data))


def increment_cost(r: redis_lib.Redis, cost_usd: float) -> float:
    """Add *cost_usd* to this month's Claude API cost counter.

    Returns the new monthly total. Key rotates naturally each month.
    """
    return float(r.incrbyfloat(_cost_key(), cost_usd))


def get_monthly_cost(r: redis_lib.Redis) -> float:
    """Return the current month's accumulated Claude API cost in USD."""
    val = r.get(_cost_key())
    return float(val) if val is not None else 0.0


def _cost_key() -> str:
    month = datetime.datetime.now(datetime.UTC).strftime("%Y-%m")
    return f"cost:claude:{month}"


def should_send_alert(
    r: redis_lib.Redis, kind: str, cooldown_seconds: int
) -> bool:
    """Atomically check-and-start an alert kind's cooldown window.

    Returns True only the first time *kind* is seen within the cooldown
    window, so a persisting condition (ADR 0020, e.g. a worker that stays
    down) is reported once per window instead of on every sweep. Uses
    ``SET ... NX EX`` so concurrent workers never both send for the same
    window.
    """
    return bool(r.set(f"alert:{kind}", "1", nx=True, ex=cooldown_seconds))


def clear_alert(r: redis_lib.Redis, kind: str) -> None:
    """Reset *kind*'s cooldown window.

    Called once a kind stops firing, so a resolved-then-recurring
    incident is treated as new and alerts immediately, instead of being
    silently swallowed by a cooldown left over from the prior incident.
    """
    r.delete(f"alert:{kind}")
