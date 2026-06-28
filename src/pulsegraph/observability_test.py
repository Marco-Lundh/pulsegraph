"""Tests for LangSmith tracing wiring (ADR 0007)."""

import uuid

from langchain_core.runnables import RunnableLambda

from pulsegraph.config import Settings
from pulsegraph.observability import configure_tracing, traced_run


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)


def _enabled() -> Settings:
    return _settings(LANGSMITH_ENABLED="true", LANGSMITH_API_KEY="k")


# --- configure_tracing ---


def test_configure_tracing_disabled_by_default() -> None:
    env: dict[str, str] = {}
    assert configure_tracing(_settings(), env) is False
    assert env == {}


def test_configure_tracing_enabled_but_unkeyed_is_off() -> None:
    env: dict[str, str] = {}
    settings = _settings(LANGSMITH_ENABLED="true", LANGSMITH_API_KEY="")
    assert configure_tracing(settings, env) is False
    assert env == {}


def test_configure_tracing_enabled_sets_env() -> None:
    env: dict[str, str] = {}
    assert configure_tracing(_enabled(), env) is True
    assert env["LANGSMITH_TRACING"] == "true"
    assert env["LANGSMITH_API_KEY"] == "k"
    assert env["LANGSMITH_PROJECT"] == "pulsegraph"


def test_configure_tracing_uses_configured_project() -> None:
    env: dict[str, str] = {}
    settings = _settings(
        LANGSMITH_ENABLED="true",
        LANGSMITH_API_KEY="k",
        LANGSMITH_PROJECT="custom",
    )
    configure_tracing(settings, env)
    assert env["LANGSMITH_PROJECT"] == "custom"


# --- traced_run ---


def test_traced_run_disabled_yields_no_trace_id() -> None:
    with traced_run(_settings()) as trace:
        RunnableLambda(lambda x: x).invoke(1)
    assert trace.trace_id is None


def test_traced_run_enabled_captures_trace_id() -> None:
    with traced_run(_enabled()) as trace:
        RunnableLambda(lambda x: x + 1).invoke(1)
    assert trace.trace_id is not None
    uuid.UUID(trace.trace_id)  # a well-formed run id


def test_traced_run_captures_trace_id_on_error() -> None:
    def _boom(_: int) -> int:
        raise ValueError("boom")

    try:
        with traced_run(_enabled()) as trace:
            RunnableLambda(_boom).invoke(1)
    except ValueError:
        pass
    assert trace.trace_id is not None
