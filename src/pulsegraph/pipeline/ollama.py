"""Real local adapters backed by Ollama (ADR 0002).

These implement the same ``Embedder`` and analysis ports as the offline
stubs in :mod:`pulsegraph.pipeline.local`, but call a running Ollama
instance. They are the local-first production default (ADR 0017): no
cloud key required, everything stays on the machine.
"""

import json

import httpx

from pulsegraph.domain.enums import ModelKind
from pulsegraph.pipeline.contracts import AnalysisResult

# The analyzer instruction lives in the versioned prompt registry (ADR
# 0011) so the row an Analysis pins matches the text actually run.
from pulsegraph.pipeline.prompts import ANALYZER_TEMPLATE


def _clamp(value: object, default: float = 0.0) -> float:
    """Coerce *value* to a float clamped to ``[0.0, 1.0]``."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


class OllamaEmbedder:
    """Embeds text with an Ollama embedding model (ADR 0014).

    Records its model name so vectors from different models are never
    mixed, exactly like the offline ``HashingEmbedder`` it replaces.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self.model_name = model
        self._timeout = timeout

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for ``text``."""
        response = httpx.post(
            f"{self._base_url}/api/embeddings",
            json={"model": self.model_name, "prompt": text},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["embedding"]


class OllamaModelClient:
    """Analyzes content with a local Ollama model (ADR 0002).

    Returns the same ``AnalysisResult`` shape as the cloud client, so the
    Analyzer's routing and fallback logic is identical for both.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def analyze(
        self, content: str, instruction: str | None = None
    ) -> AnalysisResult:
        """Analyze ``content`` with the local model.

        ``instruction`` is the active analyzer template loaded from the
        registry at runtime (ADR 0011); falls back to ``ANALYZER_TEMPLATE``
        when None. Raises ``TimeoutError`` if the model does not answer in
        time, so the Analyzer can fall back to the cloud model (ADR 0002).
        """
        system = instruction or ANALYZER_TEMPLATE
        try:
            # Instruction/data separation (ADR 0013): the analyzer
            # instruction is the system turn; the untrusted item is a
            # distinct user turn, never concatenated into the instruction,
            # mirroring the Claude client's system/user split.
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                    "format": "json",
                    "stream": False,
                },
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("ollama analysis timed out") from exc
        response.raise_for_status()
        body = response.json()
        payload = json.loads(body["message"]["content"])
        labels = payload.get("labels") or []
        return AnalysisResult(
            summary=str(payload.get("summary", "")) or "(empty)",
            relevance=_clamp(payload.get("relevance")),
            confidence=_clamp(payload.get("confidence")),
            model=ModelKind.OLLAMA,
            labels=tuple(str(label) for label in labels),
            # Token counts are recorded for the ledger (ADR 0008); the local
            # model is free, so cost stays zero.
            tokens_in=int(body.get("prompt_eval_count", 0)),
            tokens_out=int(body.get("eval_count", 0)),
        )
