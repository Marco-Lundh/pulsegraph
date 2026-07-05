"""Tests for redis_client helpers (ADR 0022)."""

import uuid

import fakeredis
import pytest

from pulsegraph.redis_client import (
    check_fixed_window,
    check_rate,
    clear_alert,
    get_fetch_cache,
    get_monthly_cost,
    increment_cost,
    set_fetch_cache,
    should_send_alert,
)

_USER = uuid.uuid4()


@pytest.fixture()
def r() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_check_rate_allows_first_call(r) -> None:
    assert check_rate(r, _USER, limit=5) is True


def test_check_rate_within_limit(r) -> None:
    for _ in range(3):
        check_rate(r, _USER, limit=5)
    assert check_rate(r, _USER, limit=5) is True


def test_check_rate_blocks_at_limit(r) -> None:
    for _ in range(3):
        check_rate(r, _USER, limit=3)
    assert check_rate(r, _USER, limit=3) is False


def test_check_rate_independent_users(r) -> None:
    other = uuid.uuid4()
    for _ in range(3):
        check_rate(r, _USER, limit=3)
    assert check_rate(r, other, limit=3) is True


def test_check_fixed_window_blocks_past_limit(r) -> None:
    key = "authrate:login:1.2.3.4"
    allowed = [
        check_fixed_window(r, key, limit=3, window_seconds=300)
        for _ in range(4)
    ]
    assert allowed == [True, True, True, False]


def test_check_fixed_window_independent_keys(r) -> None:
    for _ in range(3):
        check_fixed_window(r, "authrate:login:1.1.1.1", 3, 300)
    # A different IP has its own budget.
    assert check_fixed_window(r, "authrate:login:2.2.2.2", 3, 300) is True


# ---------------------------------------------------------------------------
# Fetch cache
# ---------------------------------------------------------------------------


def test_cache_miss_returns_none(r) -> None:
    assert get_fetch_cache(r, "fetch:jobtech:abc123") is None


def test_cache_roundtrip(r) -> None:
    data = [{"id": "1", "title": "Python dev"}]
    set_fetch_cache(r, "fetch:jobtech:abc123", data, ttl=900)
    assert get_fetch_cache(r, "fetch:jobtech:abc123") == data


def test_cache_empty_list(r) -> None:
    set_fetch_cache(r, "fetch:riksdagen:xyz", [], ttl=60)
    assert get_fetch_cache(r, "fetch:riksdagen:xyz") == []


def test_cache_different_keys_are_independent(r) -> None:
    set_fetch_cache(r, "fetch:jobtech:aaa", [{"a": 1}], ttl=60)
    assert get_fetch_cache(r, "fetch:jobtech:bbb") is None


# ---------------------------------------------------------------------------
# Cost counter
# ---------------------------------------------------------------------------


def test_monthly_cost_starts_at_zero(r) -> None:
    assert get_monthly_cost(r) == 0.0


def test_increment_cost_accumulates(r) -> None:
    increment_cost(r, 0.01)
    increment_cost(r, 0.02)
    assert abs(get_monthly_cost(r) - 0.03) < 1e-9


def test_increment_cost_returns_new_total(r) -> None:
    increment_cost(r, 1.0)
    total = increment_cost(r, 0.5)
    assert abs(total - 1.5) < 1e-9


# ---------------------------------------------------------------------------
# Alert throttle/dedup (ADR 0020)
# ---------------------------------------------------------------------------


def test_should_send_alert_true_first_time(r) -> None:
    assert should_send_alert(r, "worker_down", cooldown_seconds=3600) is True


def test_should_send_alert_false_within_cooldown(r) -> None:
    should_send_alert(r, "worker_down", cooldown_seconds=3600)
    assert should_send_alert(r, "worker_down", cooldown_seconds=3600) is False


def test_should_send_alert_independent_kinds(r) -> None:
    should_send_alert(r, "worker_down", cooldown_seconds=3600)
    assert should_send_alert(r, "queue_backlog", cooldown_seconds=3600) is True


def test_clear_alert_resets_the_cooldown(r) -> None:
    should_send_alert(r, "worker_down", cooldown_seconds=3600)
    clear_alert(r, "worker_down")
    assert should_send_alert(r, "worker_down", cooldown_seconds=3600) is True


def test_clear_alert_is_a_noop_when_nothing_is_set(r) -> None:
    clear_alert(r, "worker_down")
