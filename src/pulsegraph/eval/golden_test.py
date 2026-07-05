"""Tests for golden dataset loading and growth (ADR 0012)."""

import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import (
    Analysis,
    Evaluation,
    Item,
    ReviewDecision,
)
from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    SourceKind,
)
from pulsegraph.domain.enums import (
    ReviewDecision as Decision,
)
from pulsegraph.eval.golden import (
    GOLDEN_DIR,
    GoldenExample,
    dump_golden,
    golden_from_decisions,
    grow_golden,
    load_all_golden,
    load_golden_file,
)

# --- loading bundled datasets ----------------------------------------------


def test_load_golden_file_parses_examples() -> None:
    examples = load_golden_file(GOLDEN_DIR / "jobtech.jsonl")
    assert examples
    assert all(e.source is SourceKind.JOBTECH for e in examples)
    assert any(e.should_notify for e in examples)
    assert any(not e.should_notify for e in examples)


def test_load_all_golden_groups_by_source() -> None:
    grouped = load_all_golden()
    assert set(grouped) == {
        SourceKind.JOBTECH,
        SourceKind.RIKSDAGEN,
        SourceKind.ENTSOE,
    }


def test_dump_and_reload_round_trip(tmp_path) -> None:
    examples = [
        GoldenExample(SourceKind.RIKSDAGEN, "A motion.", True, "n"),
        GoldenExample(SourceKind.RIKSDAGEN, "A notice.", False),
    ]
    path = tmp_path / "out.jsonl"
    dump_golden(examples, path)
    assert load_golden_file(path) == examples


# --- growing the dataset from review verdicts ------------------------------


def _decision_chain(decision: Decision) -> FakeSession:
    item = Item(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        watch_id=uuid.uuid4(),
        source=SourceKind.JOBTECH,
        raw_payload={"title": "Python role", "body": "Build pipelines."},
        content_hash="h1",
    )
    analysis = Analysis(
        id=uuid.uuid4(),
        item_id=item.id,
        model_used=ModelKind.OLLAMA,
        model_version="llama3.1:8b",
        result="Python role",
        confidence=0.9,
    )
    evaluation = Evaluation(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        relevance_score=0.8,
        confidence=0.9,
        status=EvalStatus.REVIEW,
    )
    review = ReviewDecision(
        id=uuid.uuid4(),
        evaluation_id=evaluation.id,
        decision=decision,
    )
    return FakeSession(item, analysis, evaluation, review)


def test_golden_from_decisions_labels_approved_as_notify() -> None:
    db = _decision_chain(Decision.APPROVED)
    examples = golden_from_decisions(db)
    assert len(examples) == 1
    assert examples[0].should_notify is True
    assert examples[0].source is SourceKind.JOBTECH
    assert "Python role" in examples[0].content
    assert "Build pipelines." in examples[0].content


def test_golden_from_decisions_labels_rejected_as_not_notify() -> None:
    db = _decision_chain(Decision.REJECTED)
    examples = golden_from_decisions(db)
    assert examples[0].should_notify is False


# --- growing the datasets on disk from review verdicts ---------------------


def test_grow_golden_appends_review_example(tmp_path) -> None:
    db = _decision_chain(Decision.APPROVED)
    added = grow_golden(db, tmp_path)

    assert added == {SourceKind.JOBTECH: 1}
    examples = load_golden_file(tmp_path / "jobtech.jsonl")
    assert len(examples) == 1
    assert examples[0].should_notify is True
    assert "Python role" in examples[0].content


def test_grow_golden_is_idempotent(tmp_path) -> None:
    db = _decision_chain(Decision.APPROVED)
    grow_golden(db, tmp_path)
    # A second run finds the same content already present and adds nothing.
    assert grow_golden(db, tmp_path) == {}
    assert len(load_golden_file(tmp_path / "jobtech.jsonl")) == 1


def test_grow_golden_no_decisions_writes_nothing(tmp_path) -> None:
    assert grow_golden(FakeSession(), tmp_path) == {}
    assert not list(tmp_path.glob("*.jsonl"))
