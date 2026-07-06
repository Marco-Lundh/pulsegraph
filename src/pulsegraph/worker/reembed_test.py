"""Tests for the re-embedding job (ADR 0014)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import Item
from pulsegraph.domain.constants import EMBEDDING_DIM
from pulsegraph.domain.enums import SourceKind
from pulsegraph.pipeline.local import DictSourceRegistry, StaticSourcePlugin
from pulsegraph.worker.reembed import reembed_stale_items

_NOW = datetime.datetime.now(datetime.UTC)
_CURRENT = "nomic-embed-text-v2"


class _StubEmbedder:
    def __init__(
        self, model: str = _CURRENT, dim: int = EMBEDDING_DIM
    ) -> None:
        self.model_name = model
        self._dim = dim
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        return [0.1] * self._dim


def _item(
    embedding_model: str | None,
    *,
    source: SourceKind = SourceKind.JOBTECH,
    embedding: list[float] | None = None,
) -> Item:
    return Item(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        watch_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        source=source,
        external_id="1",
        raw_payload={"id": "1", "title": "Python dev", "body": "a role"},
        content_hash="hash-1",
        embedding=embedding,
        embedding_model=embedding_model,
        fetched_at=_NOW,
    )


def _registry() -> DictSourceRegistry:
    reg = DictSourceRegistry()
    reg.register(StaticSourcePlugin(SourceKind.JOBTECH, []))
    return reg


def test_reembed_updates_stale_items() -> None:
    item = _item("old-embed-model")
    db = FakeSession(item)
    embedder = _StubEmbedder()

    result = reembed_stale_items(db, _registry(), embedder)

    assert result == {"scanned": 1, "reembedded": 1}
    assert item.embedding_model == _CURRENT
    assert item.embedding == [0.1] * EMBEDDING_DIM
    assert embedder.calls == 1


def test_reembed_skips_current_model_items_with_a_vector() -> None:
    # Current model AND a stored vector -> genuinely up to date, skipped.
    item = _item(_CURRENT, embedding=[0.2] * EMBEDDING_DIM)
    db = FakeSession(item)
    embedder = _StubEmbedder()

    result = reembed_stale_items(db, _registry(), embedder)

    assert result == {"scanned": 0, "reembedded": 0}
    assert embedder.calls == 0


def test_reembed_backfills_null_vector_for_current_model() -> None:
    # A vector dropped for a dimension mismatch keeps the current model name
    # but has no vector; the re-embed job must still pick it up (ADR 0014).
    item = _item(_CURRENT, embedding=None)
    db = FakeSession(item)

    result = reembed_stale_items(db, _registry(), _StubEmbedder())

    assert result == {"scanned": 1, "reembedded": 1}
    assert item.embedding == [0.1] * EMBEDDING_DIM


def test_reembed_treats_null_model_as_stale() -> None:
    item = _item(None)
    db = FakeSession(item)

    result = reembed_stale_items(db, _registry(), _StubEmbedder())

    assert result["reembedded"] == 1
    assert item.embedding_model == _CURRENT


def test_reembed_skips_wrong_dimension_vector() -> None:
    # A model that returns a mismatched dimension is not stored (the item
    # stays stale for the next attempt) rather than corrupting the column.
    item = _item("old-embed-model")
    db = FakeSession(item)
    embedder = _StubEmbedder(dim=EMBEDDING_DIM + 16)

    result = reembed_stale_items(db, _registry(), embedder)

    assert result == {"scanned": 1, "reembedded": 0}
    assert item.embedding_model == "old-embed-model"
    assert item.embedding is None


def test_reembed_skips_item_with_unknown_source() -> None:
    # No plugin registered for the item's source -> skipped, batch survives.
    item = _item("old-embed-model", source=SourceKind.ENTSOE)
    db = FakeSession(item)

    result = reembed_stale_items(db, _registry(), _StubEmbedder())

    assert result == {"scanned": 1, "reembedded": 0}
    assert item.embedding_model == "old-embed-model"
