"""Model-aware vector similarity over stored item embeddings (ADR 0014).

Embeddings are only comparable within one embedding model, so every
similarity query is scoped to a single ``embedding_model`` — comparing
vectors from different models would be meaningless (ADR 0014). Used for
semantic deduplication: a reworded repost of an item the user has already
seen has a different content hash but a near-identical vector, so it can be
caught here where the exact-hash dedup misses it.
"""

import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pulsegraph.db.models import Item

logger = logging.getLogger(__name__)


def find_similar_items(
    db: Session,
    *,
    user_id: uuid.UUID,
    embedding: list[float] | None,
    embedding_model: str | None,
    threshold: float,
    exclude_run_id: uuid.UUID | None = None,
    limit: int = 5,
) -> list[tuple[uuid.UUID, float]]:
    """Return the user's nearest items to *embedding*, within threshold.

    Uses pgvector cosine distance and only compares vectors produced by the
    same ``embedding_model``. Returns ``(item_id, cosine_distance)`` for
    neighbours whose cosine similarity is at least ``threshold`` (i.e.
    distance <= ``1 - threshold``), nearest first. Optionally excludes a run
    (e.g. the current one, so an item never matches itself or its batch
    siblings). Best-effort: if the query cannot run — no vector, or a
    backend without pgvector such as the in-memory test double — it returns
    ``[]`` so the caller degrades to hash-only dedup instead of crashing.
    """
    if embedding is None or embedding_model is None:
        return []
    max_distance = 1.0 - threshold
    try:
        query = db.query(
            Item.id,
            Item.embedding.cosine_distance(embedding).label("distance"),
        ).filter(
            Item.user_id == user_id,
            Item.embedding_model == embedding_model,
            Item.embedding.isnot(None),
        )
        if exclude_run_id is not None:
            query = query.filter(Item.run_id != exclude_run_id)
        rows = query.order_by("distance").limit(limit).all()
        return [
            (row.id, float(row.distance))
            for row in rows
            if row.distance <= max_distance
        ]
    except SQLAlchemyError:
        # A real database problem (e.g. pgvector missing): semantic dedup
        # silently turning off is a degradation an operator should see.
        logger.warning(
            "similarity query failed; semantic dedup skipped", exc_info=True
        )
        return []
    except Exception:  # noqa: BLE001
        # The in-memory test double can't evaluate a cosine_distance
        # expression; that's an expected offline degradation, not an alert.
        logger.debug("similarity unavailable offline; skipping", exc_info=True)
        return []
