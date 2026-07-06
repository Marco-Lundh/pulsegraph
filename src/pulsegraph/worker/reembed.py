"""Re-embed items whose vectors are stale for the current model (ADR 0014).

Embedding vectors are only comparable when produced by the same model, so
changing the embedding model is an explicit, versioned migration: the new
model is introduced, then affected items are re-embedded in the background
before comparisons switch over. This job drains that backlog — it finds
items whose recorded ``embedding_model`` differs from the current embedder
(or whose vector is missing), reconstructs their content from the stored
raw payload via the source plugin, and re-embeds them. It is bounded to a
batch per call so a scheduled cron can catch up over time without a long
blocking pass.
"""

import asyncio
import logging

from sqlalchemy import or_
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import Item
from pulsegraph.domain.constants import EMBEDDING_DIM
from pulsegraph.pipeline.contracts import Embedder, SourceRegistry
from pulsegraph.pipeline.sanitize import sanitize_text

logger = logging.getLogger(__name__)


def reembed_stale_items(
    db: Session,
    registry: SourceRegistry,
    embedder: Embedder,
    *,
    batch_size: int = 200,
) -> dict:
    """Re-embed up to *batch_size* items stale for the current model.

    An item is stale when its ``embedding_model`` differs from the
    embedder's ``model_name``, OR its vector is missing — including a vector
    dropped for a dimension mismatch (which keeps the current model name),
    so the dimension guard's promise that the re-embed job backfills it
    later actually holds (ADR 0014). Content is rebuilt from ``raw_payload``
    through the source plugin and sanitized exactly as the pipeline does, so
    the content hash is unchanged and only the vector + model are updated.
    The stale filter is applied in the query and again in Python, so it is
    correct under the FakeSession test double (mirrors ``worker.scheduler``).
    """
    current = embedder.model_name
    stale = [
        item
        for item in db.query(Item)
        .filter(
            or_(
                Item.embedding_model != current,
                Item.embedding_model.is_(None),
                Item.embedding.is_(None),
            )
        )
        .limit(batch_size)
        .all()
        if item.embedding_model != current or item.embedding is None
    ]

    reembedded = 0
    for item in stale:
        try:
            plugin = registry.get(item.source)
            content = sanitize_text(plugin.parse(item.raw_payload).content)
            vector = embedder.embed(content)
        except Exception:  # noqa: BLE001
            # A missing plugin or a transient embed failure must not abort
            # the whole batch; log and leave the item for the next run.
            logger.exception("re-embed failed for item %s", item.id)
            continue
        if len(vector) != EMBEDDING_DIM:
            logger.warning(
                "re-embed produced dim %d for item %s (expected %d); skip",
                len(vector),
                item.id,
                EMBEDDING_DIM,
            )
            continue
        item.embedding = vector
        item.embedding_model = current
        reembedded += 1

    db.commit()
    return {"scanned": len(stale), "reembedded": reembedded}


async def run_reembed(ctx: dict) -> dict:
    """arq cron entry: re-embed a batch of stale-model items (ADR 0014).

    The batch does up to ``batch_size`` blocking embed calls, so it runs in
    a worker thread to keep the arq event loop responsive (like ``run_watch``).
    """
    settings = get_settings()
    db: Session = ctx["db_factory"]()
    try:
        deps = ctx["pipeline_deps"]
        return await asyncio.to_thread(
            reembed_stale_items,
            db,
            deps.registry,
            deps.embedder,
            batch_size=settings.reembed_batch_size,
        )
    finally:
        db.close()
