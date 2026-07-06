"""Tests for the hybrid model client routing."""

import pytest

from pulsegraph.domain.enums import ModelKind
from pulsegraph.pipeline.contracts import AnalysisResult
from pulsegraph.pipeline.hybrid import HybridModelClient


class _StubClient:
    def __init__(self, model: ModelKind) -> None:
        self._model = model
        self.instruction_seen: str | None = None

    def analyze(
        self, content: str, instruction: str | None = None
    ) -> AnalysisResult:
        self.instruction_seen = instruction
        return AnalysisResult("s", 0.5, 0.5, self._model)


def test_routes_ollama_to_local() -> None:
    hybrid = HybridModelClient(
        _StubClient(ModelKind.OLLAMA), _StubClient(ModelKind.CLAUDE)
    )
    assert hybrid.analyze("x", ModelKind.OLLAMA).model is ModelKind.OLLAMA


def test_routes_claude_to_cloud() -> None:
    hybrid = HybridModelClient(
        _StubClient(ModelKind.OLLAMA), _StubClient(ModelKind.CLAUDE)
    )
    assert hybrid.analyze("x", ModelKind.CLAUDE).model is ModelKind.CLAUDE


def test_forwards_runtime_instruction_to_client() -> None:
    # ADR 0011: the active analyzer instruction is forwarded to the client.
    local = _StubClient(ModelKind.OLLAMA)
    hybrid = HybridModelClient(local)
    hybrid.analyze("x", ModelKind.OLLAMA, instruction="RUNTIME PROMPT")
    assert local.instruction_seen == "RUNTIME PROMPT"


def test_claude_without_cloud_raises() -> None:
    hybrid = HybridModelClient(_StubClient(ModelKind.OLLAMA))
    with pytest.raises(RuntimeError):
        hybrid.analyze("x", ModelKind.CLAUDE)
