"""End-to-end tests for the assembled agent graph."""

from dataclasses import replace

from langgraph.checkpoint.memory import MemorySaver

from pulsegraph.domain.enums import EvalStatus, ModelKind, SourceKind
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.checkpointer import checkpoint_history
from pulsegraph.pipeline.contracts import WatchSpec
from pulsegraph.pipeline.graph import build_pipeline, run_pipeline
from pulsegraph.pipeline.local import (
    DictSourceRegistry,
    HashingEmbedder,
    InMemorySink,
    KeywordModelClient,
    StaticSourcePlugin,
)

WATCH = WatchSpec(user_id="u1", source=SourceKind.JOBTECH, query="python")


def _records() -> list[dict]:
    return [
        {"id": "1", "title": "Senior Python", "body": "x" * 700},
        {"id": "2", "title": "Tiny", "body": "short"},
        {"id": "1", "title": "Senior Python", "body": "x" * 700},
    ]


def _deps(sink: InMemorySink) -> PipelineDeps:
    registry = DictSourceRegistry()
    registry.register(StaticSourcePlugin(SourceKind.JOBTECH, _records()))
    return PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(keywords=("python",)),
        sink=sink,
        cloud_available=False,
    )


def test_pipeline_runs_end_to_end() -> None:
    sink = InMemorySink()
    state = run_pipeline(_deps(sink), WATCH)

    assert len(state["items"]) == 2  # duplicate dropped
    assert all(len(v) == 768 for v in state["embeddings"].values())
    statuses = {e.status for e in state["evaluations"]}
    assert EvalStatus.APPROVED in statuses
    assert EvalStatus.REVIEW in statuses
    # Only the long, relevant item is delivered.
    assert len(sink.delivered) == 1
    assert sink.delivered[0].dedup_key == "jobtech:1"
    assert sink.delivered[0].labels == ("python",)


def test_pipeline_is_idempotent_across_runs() -> None:
    sink = InMemorySink()
    deps = _deps(sink)
    first = run_pipeline(deps, WATCH)
    # Carry the cross-run memory back in, as the DB would in production.
    second = run_pipeline(
        deps,
        WATCH,
        seen_hashes=first["seen_hashes"],
        sent_dedup_keys=first["sent_dedup_keys"],
    )
    assert second["items"] == []  # everything already seen
    assert second["notifications"] == []
    assert len(sink.delivered) == 1  # no re-delivery


def test_pipeline_uses_cloud_when_available() -> None:
    sink = InMemorySink()
    registry = DictSourceRegistry()
    registry.register(
        StaticSourcePlugin(
            SourceKind.JOBTECH,
            [{"id": "9", "title": "Tiny", "body": "short"}],
        )
    )
    deps = PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(),
        sink=sink,
        cloud_available=True,
    )
    state = run_pipeline(deps, WATCH)
    # Short item: local confidence is low, so it falls back to Claude.
    assert state["analyses"][0].result.model is ModelKind.CLAUDE


def test_build_pipeline_returns_compiled_graph() -> None:
    graph = build_pipeline(_deps(InMemorySink()))
    # A compiled LangGraph exposes an invoke method.
    assert hasattr(graph, "invoke")


def test_pipeline_checkpoints_state_when_checkpointer_configured() -> None:
    # ADR 0001: with a checkpointer the graph persists its state at each
    # super-step, retrievable by the run's thread id (time-travel).
    checkpointer = MemorySaver()
    deps = replace(_deps(InMemorySink()), checkpointer=checkpointer)

    run_pipeline(deps, WATCH, thread_id="run-abc")

    history = checkpoint_history(checkpointer, "run-abc")
    assert len(history) > 0
    # A different run's checkpoints are namespaced separately.
    assert checkpoint_history(checkpointer, "other-run") == []


def test_pipeline_short_circuits_on_schema_drift() -> None:
    # A record missing a required field drifts the schema: the graph must
    # stop at the Fetcher (ADR 0010), never analyzing or notifying.
    sink = InMemorySink()
    registry = DictSourceRegistry()
    registry.register(StaticSourcePlugin(SourceKind.JOBTECH, [{"id": "1"}]))
    deps = PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(),
        sink=sink,
        cloud_available=False,
    )
    state = run_pipeline(deps, WATCH)

    assert state["drift_detail"]
    assert state["items"] == []
    assert "analyses" not in state or state["analyses"] == []
    assert sink.delivered == []
