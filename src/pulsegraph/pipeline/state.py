"""The state object threaded through the agent graph (ADR 0001).

The pipeline is linear (Watcher -> Fetcher -> Embedder -> Analyzer ->
Evaluator -> Notifier), so each node overwrites the keys it owns and
no concurrent reducers are needed. ``total=False`` lets a node return
a partial update.
"""

from typing import TypedDict

from pulsegraph.pipeline.contracts import (
    AnalysisRecord,
    EvaluationRecord,
    NotificationDraft,
    WatchSpec,
)
from pulsegraph.sources.base import FetchedItem


class PipelineState(TypedDict, total=False):
    """Everything one watch run accumulates as it flows downstream."""

    watch: WatchSpec

    # Cross-run memory, seeded at run start (DB-backed in production).
    seen_hashes: set[str]
    sent_dedup_keys: set[str]

    # Per-stage outputs.
    raw_records: list[dict]
    items: list[FetchedItem]
    embeddings: dict[str, list[float]]
    analyses: list[AnalysisRecord]
    evaluations: list[EvaluationRecord]
    notifications: list[NotificationDraft]

    # Non-fatal problems collected without aborting the run.
    errors: list[str]
