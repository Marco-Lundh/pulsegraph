"""Guard tests for the similarity query (ADR 0014).

The pgvector cosine query itself needs a real Postgres and is exercised by
the e2e verification; here we only cover the best-effort guards that make it
safe to call from the persist path under the in-memory test double.
"""

import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.worker.similarity import find_similar_items

_USER = uuid.uuid4()


def test_returns_empty_without_embedding() -> None:
    assert (
        find_similar_items(
            FakeSession(),
            user_id=_USER,
            embedding=None,
            embedding_model="m",
            threshold=0.95,
        )
        == []
    )


def test_returns_empty_without_model() -> None:
    assert (
        find_similar_items(
            FakeSession(),
            user_id=_USER,
            embedding=[0.1, 0.2],
            embedding_model=None,
            threshold=0.95,
        )
        == []
    )


def test_degrades_to_empty_without_pgvector() -> None:
    # The in-memory double can't evaluate a cosine_distance expression, so
    # the query degrades to [] rather than crashing the persist path.
    assert (
        find_similar_items(
            FakeSession(),
            user_id=_USER,
            embedding=[0.1, 0.2, 0.3],
            embedding_model="nomic-embed-text",
            threshold=0.95,
        )
        == []
    )
