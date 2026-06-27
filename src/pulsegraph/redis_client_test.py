"""Tests for redis_client helpers (ADR 0022)."""

import uuid

import fakeredis
import pytest

from pulsegraph.redis_client import (
    check_rate,
    get_fetch_cache,
    get_monthly_cost,
    increment_cost,
    set_fetch_cache,
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
