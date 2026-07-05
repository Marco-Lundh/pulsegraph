"""Tests for the versioned prompt registry (ADR 0011)."""

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import Prompt
from pulsegraph.domain.enums import PromptRole
from pulsegraph.pipeline.prompts import (
    ANALYZER_PROMPT_NAME,
    ANALYZER_TEMPLATE,
    active_prompt_id,
    ensure_default_prompts,
)


def test_ensure_default_prompts_seeds_analyzer_and_evaluator() -> None:
    db = FakeSession()
    added = ensure_default_prompts(db)
    assert added == 2
    prompts = db.query(Prompt).all()
    names = {p.name for p in prompts}
    assert ANALYZER_PROMPT_NAME in names
    # The seeded analyzer template is the exact text the local client runs.
    analyzer = next(p for p in prompts if p.name == ANALYZER_PROMPT_NAME)
    assert analyzer.template == ANALYZER_TEMPLATE
    assert analyzer.is_active is True
    assert analyzer.version == 1


def test_ensure_default_prompts_is_idempotent() -> None:
    db = FakeSession()
    ensure_default_prompts(db)
    added_again = ensure_default_prompts(db)
    assert added_again == 0
    assert len(db.query(Prompt).all()) == 2


def test_active_prompt_id_returns_seeded_analyzer() -> None:
    db = FakeSession()
    ensure_default_prompts(db)
    prompt_id = active_prompt_id(db, PromptRole.ANALYZER)
    assert prompt_id is not None


def test_active_prompt_id_none_when_unseeded() -> None:
    assert active_prompt_id(FakeSession(), PromptRole.ANALYZER) is None
