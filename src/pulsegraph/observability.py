"""LangSmith tracing wiring (ADR 0007) — local-first and opt-in.

Tracing is off unless ``LANGSMITH_ENABLED`` is set and an API key is
present. When on, the LangGraph execution is auto-traced to LangSmith via
environment variables, and each run's root trace id is captured so a
``PipelineRun`` can be linked back to its trace in the dashboard.
"""

import os
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager

from pulsegraph.config import Settings


def configure_tracing(
    settings: Settings,
    env: MutableMapping[str, str] | None = None,
) -> bool:
    """Enable LangSmith tracing via environment variables when configured.

    Returns whether tracing is active. A no-op unless
    ``settings.langsmith_active`` (keeping the local-first default,
    ADR 0017) and idempotent — safe to call on every worker startup.
    """
    target = os.environ if env is None else env
    if not settings.langsmith_active:
        return False
    target["LANGSMITH_TRACING"] = "true"
    target["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    target["LANGSMITH_PROJECT"] = settings.langsmith_project
    return True


class TraceHandle:
    """Carries the captured root trace id out of a :func:`traced_run`."""

    def __init__(self) -> None:
        self.trace_id: str | None = None


@contextmanager
def traced_run(settings: Settings) -> Iterator[TraceHandle]:
    """Capture the root LangSmith trace id of the work done in the block.

    When tracing is disabled the handle's ``trace_id`` stays ``None`` and
    no tracing machinery is engaged. The id is captured even when the
    block raises, so a failed run still links to its trace (ADR 0007).
    """
    handle = TraceHandle()
    if not settings.langsmith_active:
        yield handle
        return

    from langchain_core.tracers.context import collect_runs

    with collect_runs() as collector:
        try:
            yield handle
        finally:
            if collector.traced_runs:
                handle.trace_id = str(collector.traced_runs[0].id)
