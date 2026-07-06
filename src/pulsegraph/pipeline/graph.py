"""Assemble and run the agent pipeline as a LangGraph graph (ADR 0001).

The graph is linear, but expressing it as a ``StateGraph`` gives the
shared state object, per-node checkpointing, and a single place where
the agent order is defined.
"""

from itertools import pairwise

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pulsegraph.pipeline.agents import (
    PipelineDeps,
    analyzer_node,
    embedder_node,
    evaluator_node,
    fetcher_node,
    notifier_node,
    watcher_node,
)
from pulsegraph.pipeline.contracts import WatchSpec
from pulsegraph.pipeline.state import PipelineState

# The fixed agent order (ADR 0001).
_AGENTS = (
    ("watcher", watcher_node),
    ("fetcher", fetcher_node),
    ("embedder", embedder_node),
    ("analyzer", analyzer_node),
    ("evaluator", evaluator_node),
    ("notifier", notifier_node),
)


def _after_fetch(state: PipelineState) -> str:
    """Route to the paused sink on schema drift, else onward (ADR 0010)."""
    return "paused" if state.get("drift_detail") else "continue"


def build_pipeline(deps: PipelineDeps) -> CompiledStateGraph:
    """Wire the six agents into a compiled, runnable graph.

    Compiled with ``deps.checkpointer`` when one is configured (ADR 0001),
    so the graph state is persisted after each super-step; ``None`` compiles
    a plain graph exactly as before (local-first default).
    """
    graph = StateGraph(PipelineState)
    for name, factory in _AGENTS:
        graph.add_node(name, factory(deps))

    names = [name for name, _ in _AGENTS]
    graph.add_edge(START, names[0])
    for upstream, downstream in pairwise(names):
        # The Fetcher fans out: schema drift short-circuits the run to the
        # end (fail loud, ADR 0010); otherwise it flows to the Embedder.
        if upstream == "fetcher":
            graph.add_conditional_edges(
                "fetcher",
                _after_fetch,
                {"continue": downstream, "paused": END},
            )
        else:
            graph.add_edge(upstream, downstream)
    graph.add_edge(names[-1], END)

    return graph.compile(checkpointer=deps.checkpointer)


def run_pipeline(
    deps: PipelineDeps,
    watch: WatchSpec,
    *,
    seen_hashes: set[str] | None = None,
    sent_dedup_keys: set[str] | None = None,
    thread_id: str | None = None,
) -> PipelineState:
    """Run one watch end to end and return the final state.

    ``seen_hashes`` and ``sent_dedup_keys`` carry cross-run memory; in
    production they are loaded from the database so deduplication and
    delivery stay idempotent across runs (ADR 0003, ADR 0016).

    ``thread_id`` (the run id in production) namespaces the run's checkpoints
    when a checkpointer is configured (ADR 0001), so each run's persisted
    state is retrievable on its own. Ignored when no checkpointer is set.
    """
    initial: PipelineState = {
        "watch": watch,
        "seen_hashes": seen_hashes or set(),
        "sent_dedup_keys": sent_dedup_keys or set(),
        "errors": [],
    }
    # A checkpointer requires a thread id on invoke; without one, no config
    # is needed and the graph runs statelessly as before.
    config = None
    if deps.checkpointer is not None:
        config = {"configurable": {"thread_id": thread_id or "run"}}
    return build_pipeline(deps).invoke(initial, config)
