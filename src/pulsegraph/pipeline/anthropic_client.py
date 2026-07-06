"""Real cloud analyzer backed by the Claude API (ADR 0002, ADR 0008).

The Analyzer routes complex or low-confidence items here. Every call is
metered against a global monthly cost counter in Redis, and calls are
paused once the configured cap is reached so a burst of cloud traffic can
never run away with the budget (ADR 0008).
"""

import json

import anthropic
import redis as redis_lib

from pulsegraph.domain.enums import ModelKind
from pulsegraph.pipeline.contracts import (
    AnalysisResult,
    CostCapExceededError,
)
from pulsegraph.redis_client import get_monthly_cost, increment_cost

# JSON Schema constraining the model's output so parsing never guesses.
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "relevance": {"type": "number"},
        "confidence": {"type": "number"},
        "labels": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "relevance", "confidence", "labels"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a content analyst. Summarize the item, rate how notable it "
    "is (relevance) and your certainty (confidence) on a 0.0-1.0 scale, "
    "and tag it with short topical labels."
)


def _clamp(value: object, default: float = 0.0) -> float:
    """Coerce *value* to a float clamped to ``[0.0, 1.0]``."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


class ClaudeModelClient:
    """Analyzes content with Claude, metered against the cost cap.

    When a Redis client is supplied, each call's cost is added to the
    month's counter and calls are refused once ``cost_cap_usd`` is hit
    (raising ``CostCapExceededError``). With no Redis client (offline /
    tests) the cap is not enforced and nothing is metered.
    """

    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str,
        *,
        redis_client: redis_lib.Redis | None = None,
        cost_cap_usd: float = 10.0,
        input_cost_per_token: float = 5.0 / 1_000_000,
        output_cost_per_token: float = 25.0 / 1_000_000,
        max_tokens: int = 1024,
    ) -> None:
        self._client = client
        self._model = model
        self._redis = redis_client
        self._cost_cap = cost_cap_usd
        self._input_cost = input_cost_per_token
        self._output_cost = output_cost_per_token
        self._max_tokens = max_tokens

    def analyze(
        self, content: str, instruction: str | None = None
    ) -> AnalysisResult:
        """Analyze ``content`` with Claude.

        ``instruction`` is the active analyzer template loaded from the
        registry at runtime (ADR 0011), sent as the system prompt; falls
        back to ``_SYSTEM`` when None. Raises ``CostCapExceededError``
        before making any request once the monthly cost cap is reached
        (ADR 0008).
        """
        if (
            self._redis is not None
            and get_monthly_cost(self._redis) >= self._cost_cap
        ):
            raise CostCapExceededError(
                f"monthly Claude cost cap of ${self._cost_cap:.2f} reached"
            )

        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=instruction or _SYSTEM,
            output_config={
                "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}
            },
            messages=[{"role": "user", "content": content}],
        )

        tokens_in, tokens_out, cost = self._meter(message)

        text = next(
            block.text for block in message.content if block.type == "text"
        )
        payload = json.loads(text)
        labels = payload.get("labels") or []
        return AnalysisResult(
            summary=str(payload.get("summary", "")) or "(empty)",
            relevance=_clamp(payload.get("relevance")),
            confidence=_clamp(payload.get("confidence")),
            model=ModelKind.CLAUDE,
            labels=tuple(str(label) for label in labels),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            # The sampling params actually sent, recorded for reproducibility
            # (ADR 0011); temperature/top_p are left at the API defaults.
            params={"max_tokens": self._max_tokens},
        )

    def _meter(self, message: object) -> tuple[int, int, float]:
        """Price this call and add its USD cost to the monthly counter.

        Returns ``(tokens_in, tokens_out, cost_usd)`` so the caller can
        record a per-call ledger entry (ADR 0008). The monthly Redis
        counter is only incremented when a Redis client is configured.
        """
        usage = message.usage  # type: ignore[attr-defined]
        tokens_in = usage.input_tokens
        tokens_out = usage.output_tokens
        cost = tokens_in * self._input_cost + tokens_out * self._output_cost
        if self._redis is not None:
            increment_cost(self._redis, cost)
        return tokens_in, tokens_out, cost
