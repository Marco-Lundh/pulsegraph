#!/usr/bin/env python
"""Re-embed items stale for the current embedding model (ADR 0014).

Thin CLI over :func:`pulsegraph.worker.reembed.reembed_stale_items` for an
operator to drain the re-embed backlog on demand after changing
``OLLAMA_EMBEDDING_MODEL`` — the same work the daily cron does, but run
until nothing is left rather than one batch. Idempotent: re-running once
every item carries the current model's vector re-embeds nothing.

    uv run python scripts/reembed.py
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.pipeline.local import DictSourceRegistry
from pulsegraph.pipeline.ollama import OllamaEmbedder
from pulsegraph.sources.entsoe import EntsoePlugin
from pulsegraph.sources.jobtech import JobTechPlugin
from pulsegraph.sources.riksdagen import RiksdagenPlugin
from pulsegraph.worker.reembed import reembed_stale_items


def main() -> int:
    settings = get_settings()
    registry = DictSourceRegistry()
    registry.register(JobTechPlugin())
    registry.register(RiksdagenPlugin())
    registry.register(EntsoePlugin(settings.entsoe_api_token))
    embedder = OllamaEmbedder(
        settings.ollama_base_url,
        settings.ollama_embedding_model,
        timeout=settings.ollama_timeout_seconds,
    )

    engine = create_engine(settings.database_url)
    total = 0
    with Session(engine) as db:
        # Drain the backlog batch by batch until a pass re-embeds nothing.
        while True:
            result = reembed_stale_items(
                db,
                registry,
                embedder,
                batch_size=settings.reembed_batch_size,
            )
            total += result["reembedded"]
            if result["reembedded"] == 0:
                break
            print(
                f"re-embedded {result['reembedded']} (running total {total})"
            )

    print(f"Done. Re-embedded {total} item(s) to {embedder.model_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
