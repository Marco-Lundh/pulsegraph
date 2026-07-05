"""Tests for the Claude client, cost metering, and the cost cap."""

import json
from dataclasses import dataclass

import fakeredis
import pytest

from pulsegraph.domain.enums import ModelKind
from pulsegraph.pipeline.anthropic_client import ClaudeModelClient
from pulsegraph.pipeline.contracts import CostCapExceededError
from pulsegraph.redis_client import get_monthly_cost, increment_cost


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _Message:
    content: list
    usage: _Usage


class _FakeMessages:
    def __init__(self, message: _Message) -> None:
        self._message = message
        self.calls = 0

    def create(self, **kwargs) -> _Message:
        self.calls += 1
        self.kwargs = kwargs
        return self._message


class _FakeAnthropic:
    def __init__(self, message: _Message) -> None:
        self.messages = _FakeMessages(message)


def _message(payload: dict, *, inp: int = 1000, out: int = 200) -> _Message:
    return _Message(
        content=[_Block(json.dumps(payload))],
        usage=_Usage(input_tokens=inp, output_tokens=out),
    )


@pytest.fixture()
def r() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def test_analyze_parses_structured_output() -> None:
    payload = {
        "summary": "Notable",
        "relevance": 0.8,
        "confidence": 0.95,
        "labels": ["energy"],
    }
    client = ClaudeModelClient(_FakeAnthropic(_message(payload)), "m")
    result = client.analyze("content")

    assert result.model is ModelKind.CLAUDE
    assert result.summary == "Notable"
    assert result.confidence == 0.95
    assert result.labels == ("energy",)


def test_analyze_meters_cost_into_redis(r) -> None:
    payload = {"summary": "s", "relevance": 0.5, "confidence": 0.9}
    fake = _FakeAnthropic(_message(payload, inp=1_000_000, out=1_000_000))
    client = ClaudeModelClient(
        fake,
        "m",
        redis_client=r,
        cost_cap_usd=100.0,
        input_cost_per_token=5.0 / 1_000_000,
        output_cost_per_token=25.0 / 1_000_000,
    )

    client.analyze("content")

    # 1M input @ $5/1M + 1M output @ $25/1M = $30.
    assert get_monthly_cost(r) == pytest.approx(30.0)


def test_analyze_returns_tokens_and_cost_on_result() -> None:
    # The per-call ledger (ADR 0008) is fed from the result: token counts
    # and the priced USD cost travel with the analysis, even with no Redis.
    payload = {"summary": "s", "relevance": 0.5, "confidence": 0.9}
    client = ClaudeModelClient(
        _FakeAnthropic(_message(payload, inp=1_000_000, out=1_000_000)),
        "m",
        input_cost_per_token=5.0 / 1_000_000,
        output_cost_per_token=25.0 / 1_000_000,
    )

    result = client.analyze("content")

    assert result.tokens_in == 1_000_000
    assert result.tokens_out == 1_000_000
    assert result.cost_usd == pytest.approx(30.0)
    # Sampling params travel with the result for provenance (ADR 0011).
    assert result.params == {"max_tokens": 1024}


def test_cost_cap_blocks_call_before_request(r) -> None:
    increment_cost(r, 10.0)  # already at the cap
    fake = _FakeAnthropic(_message({"summary": "s"}))
    client = ClaudeModelClient(fake, "m", redis_client=r, cost_cap_usd=10.0)

    with pytest.raises(CostCapExceededError):
        client.analyze("content")
    assert fake.messages.calls == 0  # no API call was made


def test_no_redis_skips_metering_and_cap() -> None:
    payload = {"summary": "s", "relevance": 0.5, "confidence": 0.5}
    client = ClaudeModelClient(_FakeAnthropic(_message(payload)), "m")
    # Without Redis the cap is not enforced and nothing is metered.
    assert client.analyze("content").summary == "s"
