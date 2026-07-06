"""Tests for the graph state checkpointer backends (ADR 0001).

The Postgres backend is exercised by the e2e verification against real
Postgres; here we cover backend selection and the in-memory history helper.
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from pulsegraph.config import Settings
from pulsegraph.pipeline.checkpointer import (
    build_checkpointer,
    checkpoint_history,
)


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)


def test_backend_none_returns_no_checkpointer() -> None:
    checkpointer, close = build_checkpointer(_settings())  # default "none"
    assert checkpointer is None
    close()  # no-op, must not raise


def test_backend_memory_returns_memory_saver() -> None:
    checkpointer, close = build_checkpointer(
        _settings(CHECKPOINTER_BACKEND="memory")
    )
    assert isinstance(checkpointer, MemorySaver)
    close()


def test_unknown_backend_raises() -> None:
    # The Literal config type rejects a bad value at load time; this covers
    # build_checkpointer's own defensive guard directly.
    class _BadSettings:
        checkpointer_backend = "bogus"

    with pytest.raises(ValueError, match="checkpointer_backend"):
        build_checkpointer(_BadSettings())


def test_checkpoint_history_empty_without_checkpointer() -> None:
    assert checkpoint_history(None, "t1") == []
