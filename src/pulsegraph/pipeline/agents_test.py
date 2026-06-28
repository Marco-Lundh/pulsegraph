"""Tests for the six agent nodes and their helpers."""

import fakeredis
import pytest

from pulsegraph.domain.enums import EvalStatus, ModelKind, SourceKind
from pulsegraph.pipeline.agents import (
    PipelineDeps,
    _analyze_one,
    _cache_key,
    _evaluate,
    analyzer_node,
    build_notification_draft,
    embedder_node,
    evaluator_node,
    fetcher_node,
    notifier_node,
    watcher_node,
)
from pulsegraph.pipeline.contracts import (
    AnalysisRecord,
    AnalysisResult,
    CostCapExceededError,
    EvaluationRecord,
    NotificationDraft,
    UnknownSourceError,
    WatchSpec,
)
from pulsegraph.pipeline.local import (
    DictSourceRegistry,
    HashingEmbedder,
    InMemorySink,
    KeywordModelClient,
    StaticSourcePlugin,
)
from pulsegraph.redis_client import get_fetch_cache
from pulsegraph.sources.base import FetchedItem

WATCH = WatchSpec(user_id="u1", source=SourceKind.JOBTECH, query="python")


def _records() -> list[dict]:
    return [
        {"id": "1", "title": "Senior Python", "body": "x" * 700},
        {"id": "1", "title": "Senior Python", "body": "x" * 700},
        {"id": "2", "title": "Tiny", "body": "short"},
    ]


def _deps(*, cloud: bool = False, model=None, sink=None) -> PipelineDeps:
    registry = DictSourceRegistry()
    registry.register(StaticSourcePlugin(SourceKind.JOBTECH, _records()))
    return PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=model or KeywordModelClient(keywords=("python",)),
        sink=sink or InMemorySink(),
        cloud_available=cloud,
    )


def test_watcher_passes_known_source() -> None:
    out = watcher_node(_deps())({"watch": WATCH})
    assert out["errors"] == []


def test_watcher_raises_on_unknown_source() -> None:
    deps = PipelineDeps(
        registry=DictSourceRegistry(),
        embedder=HashingEmbedder(),
        model=KeywordModelClient(),
        sink=InMemorySink(),
        cloud_available=False,
    )
    with pytest.raises(UnknownSourceError):
        watcher_node(deps)({"watch": WATCH})


def test_fetcher_deduplicates_and_sanitizes() -> None:
    out = fetcher_node(_deps())({"watch": WATCH, "seen_hashes": set()})
    # Two distinct records survive; the duplicate of id=1 is dropped.
    assert len(out["items"]) == 2
    assert len(out["seen_hashes"]) == 2
    assert out["raw_records"]  # raw retained for provenance


def test_fetcher_records_schema_errors_without_aborting() -> None:
    registry = DictSourceRegistry()
    registry.register(StaticSourcePlugin(SourceKind.JOBTECH, [{"id": "1"}]))
    deps = PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(),
        sink=InMemorySink(),
        cloud_available=False,
    )
    out = fetcher_node(deps)({"watch": WATCH, "seen_hashes": set()})
    assert out["items"] == []
    assert out["errors"] and "missing" in out["errors"][0]


def test_fetcher_skips_records_already_seen() -> None:
    deps = _deps()
    first = fetcher_node(deps)({"watch": WATCH, "seen_hashes": set()})
    second = fetcher_node(deps)(
        {"watch": WATCH, "seen_hashes": first["seen_hashes"]}
    )
    assert second["items"] == []


class _CountingPlugin(StaticSourcePlugin):
    """A static plugin that records how many times ``fetch`` is hit."""

    def __init__(self, records: list[dict]) -> None:
        super().__init__(SourceKind.JOBTECH, records)
        self.fetch_calls = 0

    def fetch(self, query: str) -> list[dict]:
        self.fetch_calls += 1
        return super().fetch(query)


def _deps_with(plugin, redis_client=None, ttl: int = 900) -> PipelineDeps:
    registry = DictSourceRegistry()
    registry.register(plugin)
    return PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(keywords=("python",)),
        sink=InMemorySink(),
        cloud_available=False,
        redis_client=redis_client,
        fetch_cache_ttl=ttl,
    )


def test_fetcher_caches_raw_records_on_miss() -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    plugin = _CountingPlugin(_records())
    out = fetcher_node(_deps_with(plugin, r))(
        {"watch": WATCH, "seen_hashes": set()}
    )
    assert plugin.fetch_calls == 1
    # The raw records are now in the cache for the next run to reuse.
    cached = get_fetch_cache(r, _cache_key(str(WATCH.source), WATCH.query))
    assert cached == _records()
    assert len(out["items"]) == 2


def test_fetcher_serves_from_cache_on_hit() -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    plugin = _CountingPlugin(_records())
    node = fetcher_node(_deps_with(plugin, r))
    node({"watch": WATCH, "seen_hashes": set()})
    second = node({"watch": WATCH, "seen_hashes": set()})
    # Second run is served from cache: the source is not fetched again.
    assert plugin.fetch_calls == 1
    assert len(second["items"]) == 2


def test_fetcher_without_redis_fetches_every_run() -> None:
    plugin = _CountingPlugin(_records())
    node = fetcher_node(_deps_with(plugin, redis_client=None))
    node({"watch": WATCH, "seen_hashes": set()})
    node({"watch": WATCH, "seen_hashes": set()})
    # No Redis means no cache — each run hits the source.
    assert plugin.fetch_calls == 2


def test_embedder_keys_by_content_hash() -> None:
    item = FetchedItem(SourceKind.JOBTECH, "1", "hello world", {})
    out = embedder_node(_deps())({"items": [item]})
    assert len(out["embeddings"]) == 1
    vector = next(iter(out["embeddings"].values()))
    assert len(vector) == 768


def test_analyze_one_uses_local_model_without_cloud() -> None:
    result = _analyze_one(_deps(cloud=False), "tiny")
    assert result.model is ModelKind.OLLAMA


def test_analyze_one_falls_back_to_cloud_on_low_confidence() -> None:
    # Short content -> local confidence 0.4 < 0.6 -> fall back.
    result = _analyze_one(_deps(cloud=True), "tiny")
    assert result.model is ModelKind.CLAUDE


def test_analyze_one_falls_back_on_local_timeout() -> None:
    class TimingOutClient:
        def analyze(self, content: str, model: ModelKind) -> AnalysisResult:
            if model is ModelKind.OLLAMA:
                raise TimeoutError("slow")
            return AnalysisResult("ok", 0.9, 0.95, ModelKind.CLAUDE)

    result = _analyze_one(_deps(cloud=True, model=TimingOutClient()), "hi")
    assert result.model is ModelKind.CLAUDE


def test_analyze_one_reraises_timeout_without_fallback() -> None:
    class TimingOutClient:
        def analyze(self, content: str, model: ModelKind) -> AnalysisResult:
            raise TimeoutError("slow")

    with pytest.raises(TimeoutError):
        _analyze_one(_deps(cloud=False, model=TimingOutClient()), "hi")


class _CostCappedClient:
    """Local analyses succeed; every cloud call hits the cost cap."""

    def analyze(self, content: str, model: ModelKind) -> AnalysisResult:
        if model is ModelKind.CLAUDE:
            raise CostCapExceededError("cap reached")
        return AnalysisResult("local", 0.4, 0.4, ModelKind.OLLAMA)


def test_analyze_one_cost_cap_falls_back_to_local_on_fallback() -> None:
    # Low local confidence wants the cloud, but the cap keeps the local
    # result instead of failing the item (ADR 0008).
    result = _analyze_one(_deps(cloud=True, model=_CostCappedClient()), "hi")
    assert result.model is ModelKind.OLLAMA
    assert result.summary == "local"


def test_analyze_one_cost_cap_falls_back_on_direct_cloud() -> None:
    # Complex content routes straight to the cloud; the cap reroutes it
    # to the local model.
    result = _analyze_one(
        _deps(cloud=True, model=_CostCappedClient()), "x" * 1600
    )
    assert result.model is ModelKind.OLLAMA


def test_analyze_one_cost_cap_with_local_timeout_reraises() -> None:
    class TimeoutThenCapped:
        def analyze(self, content: str, model: ModelKind) -> AnalysisResult:
            if model is ModelKind.CLAUDE:
                raise CostCapExceededError("cap reached")
            raise TimeoutError("slow")

    deps = _deps(cloud=True, model=TimeoutThenCapped())
    with pytest.raises(TimeoutError):
        _analyze_one(deps, "hi")


def test_analyzer_node_builds_records() -> None:
    item = FetchedItem(SourceKind.JOBTECH, "1", "x" * 700, {})
    out = analyzer_node(_deps())({"items": [item]})
    record = out["analyses"][0]
    assert isinstance(record, AnalysisRecord)
    assert record.content_hash


def test_evaluate_branches() -> None:
    deps = _deps()
    low_conf = AnalysisResult("s", 0.9, 0.3, ModelKind.OLLAMA)
    low_rel = AnalysisResult("s", 0.1, 0.9, ModelKind.OLLAMA)
    good = AnalysisResult("s", 0.9, 0.9, ModelKind.OLLAMA)
    assert _evaluate(deps, low_conf)[0] is EvalStatus.REVIEW
    assert _evaluate(deps, low_rel)[0] is EvalStatus.REVIEW
    assert _evaluate(deps, good)[0] is EvalStatus.APPROVED


def test_evaluator_node_over_analyses() -> None:
    item = FetchedItem(SourceKind.JOBTECH, "1", "x", {})
    analysis = AnalysisRecord(
        item, "h", AnalysisResult("s", 0.9, 0.9, ModelKind.OLLAMA)
    )
    out = evaluator_node(_deps())({"analyses": [analysis]})
    assert out["evaluations"][0].status is EvalStatus.APPROVED


def _approved(item: FetchedItem) -> EvaluationRecord:
    analysis = AnalysisRecord(
        item, "h", AnalysisResult("Title\nbody", 0.9, 0.9, ModelKind.OLLAMA)
    )
    return EvaluationRecord(analysis, EvalStatus.APPROVED, "ok")


def test_draft_uses_external_id_and_first_line() -> None:
    item = FetchedItem(SourceKind.JOBTECH, "42", "c", {})
    draft = build_notification_draft("u1", _approved(item))
    assert draft.dedup_key == "jobtech:42"
    assert draft.title == "Title"


def test_draft_falls_back_to_hash_when_no_external_id() -> None:
    item = FetchedItem(SourceKind.JOBTECH, None, "c", {})
    draft = build_notification_draft("u1", _approved(item))
    assert draft.dedup_key == "jobtech:h"


def test_notifier_sends_only_approved_and_dedupes() -> None:
    sink = InMemorySink()
    deps = _deps(sink=sink)
    item = FetchedItem(SourceKind.JOBTECH, "42", "c", {})
    review = EvaluationRecord(
        _approved(item).analysis, EvalStatus.REVIEW, "needs review"
    )
    state = {
        "watch": WATCH,
        "evaluations": [_approved(item), review],
        "sent_dedup_keys": set(),
    }
    out = notifier_node(deps)(state)
    assert len(out["notifications"]) == 1
    assert len(sink.delivered) == 1
    # Re-running with the carried key delivers nothing more.
    again = notifier_node(deps)(
        {**state, "sent_dedup_keys": out["sent_dedup_keys"]}
    )
    assert again["notifications"] == []
    assert len(sink.delivered) == 1


def test_notification_draft_defaults_labels_empty() -> None:
    draft = NotificationDraft("u1", "t", "b", "k")
    assert draft.labels == ()
