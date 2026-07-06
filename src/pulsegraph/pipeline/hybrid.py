"""Hybrid model client that routes by model kind (ADR 0002).

Implements the single ``ModelClient`` port the Analyzer depends on,
dispatching local-model calls to Ollama and cloud calls to Claude. This
mirrors the offline ``KeywordModelClient``, which also answers for both
``ModelKind`` values, so the Analyzer's routing code is unchanged.
"""

from pulsegraph.domain.enums import ModelKind
from pulsegraph.pipeline.anthropic_client import ClaudeModelClient
from pulsegraph.pipeline.contracts import AnalysisResult
from pulsegraph.pipeline.ollama import OllamaModelClient


class HybridModelClient:
    """Routes an analysis to the local or cloud client by model kind."""

    def __init__(
        self,
        local: OllamaModelClient,
        cloud: ClaudeModelClient | None = None,
    ) -> None:
        self._local = local
        self._cloud = cloud

    def analyze(
        self,
        content: str,
        model: ModelKind,
        instruction: str | None = None,
    ) -> AnalysisResult:
        """Analyze ``content`` with the client for ``model``.

        Forwards the runtime analyzer ``instruction`` (ADR 0011) to the
        chosen client.
        """
        if model is ModelKind.CLAUDE:
            if self._cloud is None:
                raise RuntimeError("cloud model requested but not configured")
            return self._cloud.analyze(content, instruction)
        return self._local.analyze(content, instruction)
