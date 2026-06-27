"""Tests for the deterministic offline adapters."""

import pytest

from pulsegraph.domain.enums import ModelKind, SourceKind
from pulsegraph.pipeline.contracts import (
    NotificationDraft,
    UnknownSourceError,
)
from pulsegraph.pipeline.local import (
    DictSourceRegistry,
    HashingEmbedder,
    InMemorySink,
    KeywordModelClient,
    StaticSourcePlugin,
)
from pulsegraph.sources.errors import SchemaValidationError


def test_embedder_is_deterministic_and_unit_norm() -> None:
    embedder = HashingEmbedder()
    a = embedder.embed("hello")
    b = embedder.embed("hello")
    assert a == b
    assert len(a) == 768
    norm = sum(value * value for value in a) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-9)


def test_embedder_differs_per_text() -> None:
    embedder = HashingEmbedder()
    assert embedder.embed("a") != embedder.embed("b")


def test_keyword_client_relevance_grows_with_length() -> None:
    client = KeywordModelClient()
    short = client.analyze("hi", ModelKind.OLLAMA)
    long = client.analyze("x" * 1000, ModelKind.OLLAMA)
    assert long.relevance > short.relevance
    assert long.relevance <= 1.0


def test_keyword_client_confidence_by_model_and_length() -> None:
    client = KeywordModelClient()
    assert client.analyze("hi", ModelKind.OLLAMA).confidence == 0.4
    assert client.analyze("x" * 80, ModelKind.OLLAMA).confidence == 0.8
    assert client.analyze("hi", ModelKind.CLAUDE).confidence == 0.95


def test_keyword_client_flags_keywords() -> None:
    client = KeywordModelClient(keywords=("python", "rust"))
    result = client.analyze("A Python and Go role", ModelKind.OLLAMA)
    assert result.labels == ("python",)


def test_keyword_client_empty_content_summary() -> None:
    result = KeywordModelClient().analyze("", ModelKind.OLLAMA)
    assert result.summary == "(empty)"


def test_sink_collects_drafts() -> None:
    sink = InMemorySink()
    draft = NotificationDraft("u1", "t", "b", "k")
    sink.send(draft)
    assert sink.delivered == [draft]


def test_registry_resolves_and_raises() -> None:
    registry = DictSourceRegistry()
    plugin = StaticSourcePlugin(SourceKind.JOBTECH, [])
    registry.register(plugin)
    assert registry.get(SourceKind.JOBTECH) is plugin
    with pytest.raises(UnknownSourceError):
        registry.get(SourceKind.RIKSDAGEN)


def test_static_plugin_fetch_validate_parse() -> None:
    record = {"id": "7", "title": "Hello", "body": "World"}
    plugin = StaticSourcePlugin(SourceKind.JOBTECH, [record])
    assert plugin.fetch("anything") == [record]
    plugin.validate_schema(record)
    item = plugin.parse(record)
    assert item.external_id == "7"
    assert item.content == "Hello\n\nWorld"


def test_static_plugin_rejects_missing_field() -> None:
    plugin = StaticSourcePlugin(SourceKind.JOBTECH, [])
    with pytest.raises(SchemaValidationError):
        plugin.validate_schema({"id": "7", "title": "Hello"})
