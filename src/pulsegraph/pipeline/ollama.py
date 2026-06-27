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

# Ask the local model for a compact, machine-readable verdict so the
# Analyzer gets the same structured shape the cloud model returns.
_ANALYZE_PROMPT = (
    "You are a content analyst. Read the item below and respond with a "
    "single JSON object and nothing else, with keys:\n"
    '  "summary": a one-line summary (string),\n'
    '  "relevance": how notable the item is, 0.0-1.0 (number),\n'
    '  "confidence": your certainty in this analysis, 0.0-1.0 (number),\n'
    '  "labels": short topical tags (array of strings).\n\n'
    "ITEM:\n{content}"
)


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

    def analyze(self, content: str) -> AnalysisResult:
        """Analyze ``content`` with the local model.

        Raises ``TimeoutError`` if the model does not answer in time, so
        the Analyzer can fall back to the cloud model (ADR 0002).
        """
        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": _ANALYZE_PROMPT.format(content=content),
                    "format": "json",
                    "stream": False,
                },
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("ollama analysis timed out") from exc
        response.raise_for_status()
        payload = json.loads(response.json()["response"])
        labels = payload.get("labels") or []
        return AnalysisResult(
            summary=str(payload.get("summary", "")) or "(empty)",
            relevance=_clamp(payload.get("relevance")),
            confidence=_clamp(payload.get("confidence")),
            model=ModelKind.OLLAMA,
            labels=tuple(str(label) for label in labels),
        )
