"""The six agent nodes of the pipeline (ADR 0001).

Each agent is a small factory: it takes the injected dependencies and
returns a node callable ``(state) -> partial state``. Nodes stay thin,
delegating to the already-tested pure logic in this package (dedup,
sanitize, routing) and to the ports in :mod:`contracts`.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace

import redis as redis_lib

from pulsegraph.domain.enums import EvalStatus, ModelKind
from pulsegraph.pipeline.contracts import (
    AnalysisRecord,
    AnalysisResult,
    CostCapExceededError,
    Embedder,
    EvaluationRecord,
    ModelClient,
    NotificationDraft,
    NotificationSink,
    SourceRegistry,
)
from pulsegraph.pipeline.dedup import content_hash, is_duplicate
from pulsegraph.pipeline.routing import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    choose_model,
    classify_complexity,
    should_fallback,
)
from pulsegraph.pipeline.sanitize import sanitize_text
from pulsegraph.pipeline.state import PipelineState
from pulsegraph.redis_client import get_fetch_cache, set_fetch_cache
from pulsegraph.sources.errors import SchemaValidationError

# An item is worth notifying about only above this relevance (ADR 0006).
RELEVANCE_NOTIFY_THRESHOLD = 0.5

Node = Callable[[PipelineState], dict]


@dataclass(frozen=True, slots=True)
class PipelineDeps:
    """External ports the agents need, resolved once per run."""

    registry: SourceRegistry
    embedder: Embedder
    model: ModelClient
    sink: NotificationSink
    cloud_available: bool
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    relevance_threshold: float = RELEVANCE_NOTIFY_THRESHOLD
    redis_client: redis_lib.Redis | None = None
    fetch_cache_ttl: int = 900


def watcher_node(deps: PipelineDeps) -> Node:
    """Validate the watch and confirm its source is registered."""

    def _run(state: PipelineState) -> dict:
        watch = state["watch"]
        # Raises UnknownSourceError early if the source is unknown.
        deps.registry.get(watch.source)
        return {"errors": list(state.get("errors", []))}

    return _run


def _cache_key(source: str, query: str) -> str:
    qhash = hashlib.sha1(query.encode()).hexdigest()[:16]
    return f"fetch:{source}:{qhash}"


def fetcher_node(deps: PipelineDeps) -> Node:
    """Fetch, validate, sanitize, and deduplicate source records."""

    def _run(state: PipelineState) -> dict:
        watch = state["watch"]
        plugin = deps.registry.get(watch.source)

        raw: list[dict] | None = None
        cache_key = _cache_key(str(watch.source), watch.query)
        if deps.redis_client is not None:
            raw = get_fetch_cache(deps.redis_client, cache_key)

        if raw is None:
            raw = plugin.fetch(watch.query)
            if deps.redis_client is not None:
                set_fetch_cache(
                    deps.redis_client,
                    cache_key,
                    raw,
                    deps.fetch_cache_ttl,
                )

        seen = set(state.get("seen_hashes", set()))
        errors = list(state.get("errors", []))
        items = []
        for record in raw:
            try:
                plugin.validate_schema(record)
            except SchemaValidationError as exc:
                errors.append(str(exc))
                continue
            item = plugin.parse(record)
            clean = sanitize_text(item.content)
            digest = content_hash(clean)
            if is_duplicate(digest, seen):
                continue
            seen.add(digest)
            items.append(replace(item, content=clean))

        return {
            "raw_records": raw,
            "items": items,
            "seen_hashes": seen,
            "errors": errors,
        }

    return _run


def embedder_node(deps: PipelineDeps) -> Node:
    """Embed each new item, keyed by its content hash (ADR 0014)."""

    def _run(state: PipelineState) -> dict:
        embeddings: dict[str, list[float]] = {}
        for item in state.get("items", []):
            digest = content_hash(item.content)
            embeddings[digest] = deps.embedder.embed(item.content)
        return {"embeddings": embeddings}

    return _run


def _analyze_one(deps: PipelineDeps, content: str) -> AnalysisResult:
    """Route one item, falling back to the cloud model if needed.

    Cloud calls may be paused by the monthly cost cap (ADR 0008); when
    that happens we degrade to the local model instead of failing.
    """
    complexity = classify_complexity(content)
    model = choose_model(complexity, deps.cloud_available)

    if model is ModelKind.CLAUDE:
        # Complex item routed straight to the cloud; on a cost cap, fall
        # back to the local model rather than dropping the item.
        try:
            return deps.model.analyze(content, ModelKind.CLAUDE)
        except CostCapExceededError:
            return deps.model.analyze(content, ModelKind.OLLAMA)

    timed_out = False
    try:
        result = deps.model.analyze(content, ModelKind.OLLAMA)
    except TimeoutError:
        result = None
        timed_out = True

    confidence = result.confidence if result else 0.0
    if should_fallback(
        confidence,
        timed_out,
        deps.cloud_available,
        deps.confidence_threshold,
    ):
        try:
            return deps.model.analyze(content, ModelKind.CLAUDE)
        except CostCapExceededError:
            if result is not None:
                return result
            raise TimeoutError(
                "local analysis timed out and cloud cost cap reached"
            ) from None

    if result is None:
        # Local timed out with no cloud fallback available.
        raise TimeoutError("local analysis timed out without a fallback")
    return result


def analyzer_node(deps: PipelineDeps) -> Node:
    """Produce a structured analysis for each item (ADR 0011)."""

    def _run(state: PipelineState) -> dict:
        analyses = []
        for item in state.get("items", []):
            result = _analyze_one(deps, item.content)
            analyses.append(
                AnalysisRecord(
                    item=item,
                    content_hash=content_hash(item.content),
                    result=result,
                )
            )
        return {"analyses": analyses}

    return _run


def _evaluate(
    deps: PipelineDeps, result: AnalysisResult
) -> tuple[EvalStatus, str]:
    """Gate an analysis on confidence and relevance (ADR 0006)."""
    if result.confidence < deps.confidence_threshold:
        return EvalStatus.REVIEW, "confidence below threshold"
    if result.relevance < deps.relevance_threshold:
        return EvalStatus.REVIEW, "relevance below notify threshold"
    return EvalStatus.APPROVED, "passed evaluation gate"


def evaluator_node(deps: PipelineDeps) -> Node:
    """Approve or route each analysis to human review (ADR 0006)."""

    def _run(state: PipelineState) -> dict:
        evaluations = [
            EvaluationRecord(analysis, *_evaluate(deps, analysis.result))
            for analysis in state.get("analyses", [])
        ]
        return {"evaluations": evaluations}

    return _run


def build_notification_draft(
    watch_user: str, record: EvaluationRecord
) -> NotificationDraft:
    """Build a deduplicated notification from an approved analysis.

    The single source of truth for the dedup identity, reused by the
    persistence layer so the dashboard channel shares the same key as
    email and webhook (ADR 0016).
    """
    item = record.analysis.item
    result = record.analysis.result
    key = item.external_id or record.analysis.content_hash
    title = result.summary.splitlines()[0] if result.summary else "Update"
    return NotificationDraft(
        user_id=watch_user,
        title=title,
        body=result.summary,
        dedup_key=f"{item.source}:{key}",
        labels=result.labels,
    )


def notifier_node(deps: PipelineDeps) -> Node:
    """Deliver notifications for approved items, idempotently (ADR 0016)."""

    def _run(state: PipelineState) -> dict:
        sent = set(state.get("sent_dedup_keys", set()))
        watch = state["watch"]
        drafts = []
        for record in state.get("evaluations", []):
            if record.status is not EvalStatus.APPROVED:
                continue
            draft = build_notification_draft(watch.user_id, record)
            if draft.dedup_key in sent:
                continue
            sent.add(draft.dedup_key)
            deps.sink.send(draft)
            drafts.append(draft)
        return {"notifications": drafts, "sent_dedup_keys": sent}

    return _run
