"""Tests for the Ollama embedder and model client."""

import json

import httpx
import pytest

from pulsegraph.domain.enums import ModelKind
from pulsegraph.pipeline import ollama
from pulsegraph.pipeline.ollama import OllamaEmbedder, OllamaModelClient


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


# --- embedder ---


def test_embedder_returns_vector(monkeypatch) -> None:
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _Resp({"embedding": [0.1, 0.2, 0.3]})

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    embedder = OllamaEmbedder("http://x:11434/", "nomic-embed-text")

    assert embedder.model_name == "nomic-embed-text"
    assert embedder.embed("hello") == [0.1, 0.2, 0.3]
    assert captured["url"] == "http://x:11434/api/embeddings"
    assert captured["json"]["prompt"] == "hello"


# --- model client ---


def _analysis_response(payload: dict) -> _Resp:
    return _Resp({"response": json.dumps(payload)})


def test_model_client_parses_structured_output(monkeypatch) -> None:
    payload = {
        "summary": "A senior Python role",
        "relevance": 0.7,
        "confidence": 0.9,
        "labels": ["python", "senior"],
    }
    monkeypatch.setattr(
        ollama.httpx, "post", lambda *a, **k: _analysis_response(payload)
    )
    result = OllamaModelClient("http://x", "llama3.1:8b").analyze("text")

    assert result.model is ModelKind.OLLAMA
    assert result.summary == "A senior Python role"
    assert result.relevance == 0.7
    assert result.labels == ("python", "senior")


def test_model_client_clamps_out_of_range_scores(monkeypatch) -> None:
    payload = {"summary": "x", "relevance": 5, "confidence": -1, "labels": []}
    monkeypatch.setattr(
        ollama.httpx, "post", lambda *a, **k: _analysis_response(payload)
    )
    result = OllamaModelClient("http://x", "m").analyze("text")

    assert result.relevance == 1.0
    assert result.confidence == 0.0


def test_model_client_raises_timeout(monkeypatch) -> None:
    def fake_post(*a, **k):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    with pytest.raises(TimeoutError):
        OllamaModelClient("http://x", "m").analyze("text")
