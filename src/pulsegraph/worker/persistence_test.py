"""Tests for persisting a run's provenance chain (ADR 0003/0016)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import (
    Analysis,
    CostEvent,
    Evaluation,
    Item,
    Notification,
    PipelineRun,
    Prompt,
    SourceHealth,
    Watch,
)
from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    NotificationChannel,
    NotificationStatus,
    PromptRole,
    SourceKind,
    SourceStatus,
)
from pulsegraph.pipeline.agents import build_notification_draft
from pulsegraph.pipeline.contracts import (
    AnalysisRecord,
    AnalysisResult,
    EvaluationRecord,
)
from pulsegraph.sources.base import FetchedItem
from pulsegraph.worker.persistence import (
    load_dedup_memory,
    mark_source_paused,
    persist_run_results,
)

_NOW = datetime.datetime.now(datetime.UTC)
_MODEL_VERSIONS = {
    ModelKind.OLLAMA: "llama3.1:8b",
    ModelKind.CLAUDE: "claude-opus-4-8",
}


def _watch() -> Watch:
    return Watch(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        source=SourceKind.JOBTECH,
        prompt="python",
    )


def _run(watch: Watch) -> PipelineRun:
    return PipelineRun(
        id=uuid.uuid4(),
        watch_id=watch.id,
        started_at=_NOW,
    )


def test_mark_source_paused_inserts_when_absent() -> None:
    db = FakeSession()
    mark_source_paused(db, SourceKind.JOBTECH, "schema drifted")
    rows = db.query(SourceHealth).all()
    assert len(rows) == 1
    assert rows[0].status == SourceStatus.PAUSED
    assert rows[0].drift_detail == "schema drifted"


def test_mark_source_paused_updates_existing_row() -> None:
    existing = SourceHealth(
        source=SourceKind.JOBTECH,
        status=SourceStatus.HEALTHY,
        drift_detail=None,
        last_checked_at=_NOW,
    )
    db = FakeSession(existing)
    mark_source_paused(db, SourceKind.JOBTECH, "fields dropped")
    # Updated in place, not duplicated.
    assert len(db.query(SourceHealth).all()) == 1
    assert existing.status == SourceStatus.PAUSED
    assert existing.drift_detail == "fields dropped"


def _evaluation(
    status: EvalStatus = EvalStatus.APPROVED,
    *,
    external_id: str = "42",
    content_hash: str = "h1",
) -> EvaluationRecord:
    item = FetchedItem(
        source=SourceKind.JOBTECH,
        external_id=external_id,
        content="Python engineer wanted",
        raw={"id": external_id, "title": "Python engineer"},
    )
    result = AnalysisResult(
        summary="Python engineer wanted",
        relevance=0.9,
        confidence=0.9,
        model=ModelKind.OLLAMA,
        labels=("python",),
    )
    analysis = AnalysisRecord(
        item=item, content_hash=content_hash, result=result
    )
    return EvaluationRecord(analysis, status, "ok")


def _state(evaluations, *, notify=True) -> dict:
    drafts = []
    embeddings = {}
    for ev in evaluations:
        embeddings[ev.analysis.content_hash] = [0.0] * 768
        if notify and ev.status is EvalStatus.APPROVED:
            drafts.append(build_notification_draft("ignored", ev))
    return {
        "evaluations": list(evaluations),
        "embeddings": embeddings,
        "notifications": drafts,
        "sent_dedup_keys": set(),
    }


# --- persist_run_results ---------------------------------------------------


def test_persists_full_chain_for_approved_item() -> None:
    watch = _watch()
    run = _run(watch)
    db = FakeSession(watch, run)
    ev = _evaluation(EvalStatus.APPROVED)

    count = persist_run_results(
        db,
        run,
        watch,
        _state([ev]),
        embedding_model="hashing-768-v1",
        model_versions=_MODEL_VERSIONS,
        now=_NOW,
    )

    assert count == 1
    items = db.query(Item).all()
    analyses = db.query(Analysis).all()
    evaluations = db.query(Evaluation).all()
    notifs = db.query(Notification).all()
    assert len(items) == len(analyses) == len(evaluations) == 1
    assert len(notifs) == 1

    item, analysis, notif = items[0], analyses[0], notifs[0]
    assert item.user_id == watch.user_id
    assert item.watch_id == watch.id
    assert item.run_id == run.id
    assert item.content_hash == "h1"
    assert item.embedding_model == "hashing-768-v1"
    assert analysis.item_id == item.id
    assert analysis.model_used == ModelKind.OLLAMA
    assert analysis.model_version == "llama3.1:8b"
    assert notif.analysis_id == analysis.id
    assert notif.channel == NotificationChannel.DASHBOARD
    assert notif.status == NotificationStatus.SENT
    assert notif.delivered_at == _NOW
    assert notif.dedup_key == "jobtech:42"


def test_persists_prompt_id_and_params_on_analysis() -> None:
    # The active analyzer prompt is pinned and the model's sampling params
    # are recorded on the Analysis for reproducibility (ADR 0011).
    watch = _watch()
    run = _run(watch)
    prompt = Prompt(
        id=uuid.uuid4(),
        name="analyzer",
        role=PromptRole.ANALYZER,
        version=1,
        template="...",
        is_active=True,
    )
    db = FakeSession(watch, run, prompt)

    item = FetchedItem(
        source=SourceKind.JOBTECH,
        external_id="8",
        content="Analyzed with params",
        raw={"id": "8", "title": "Params item"},
    )
    result = AnalysisResult(
        summary="Params item",
        relevance=0.9,
        confidence=0.95,
        model=ModelKind.CLAUDE,
        labels=(),
        params={"max_tokens": 512},
    )
    ev = EvaluationRecord(
        AnalysisRecord(item=item, content_hash="c8", result=result),
        EvalStatus.REVIEW,
        "needs review",
    )

    persist_run_results(
        db,
        run,
        watch,
        _state([ev], notify=False),
        embedding_model="hashing-768-v1",
        model_versions=_MODEL_VERSIONS,
        now=_NOW,
    )

    analysis = db.query(Analysis).all()[0]
    assert analysis.prompt_id == prompt.id
    assert analysis.params == {"max_tokens": 512}


def test_persists_cost_event_per_analysis() -> None:
    # Every model call is recorded in the per-user, per-run ledger (ADR
    # 0008), whether or not the item is ultimately notified.
    watch = _watch()
    run = _run(watch)
    db = FakeSession(watch, run)

    item = FetchedItem(
        source=SourceKind.JOBTECH,
        external_id="7",
        content="Cloud-analyzed item",
        raw={"id": "7", "title": "Cloud item"},
    )
    result = AnalysisResult(
        summary="Cloud item",
        relevance=0.9,
        confidence=0.95,
        model=ModelKind.CLAUDE,
        labels=(),
        tokens_in=1200,
        tokens_out=300,
        cost_usd=0.0135,
    )
    ev = EvaluationRecord(
        AnalysisRecord(item=item, content_hash="c7", result=result),
        EvalStatus.REVIEW,
        "needs review",
    )

    persist_run_results(
        db,
        run,
        watch,
        _state([ev], notify=False),
        embedding_model="hashing-768-v1",
        model_versions=_MODEL_VERSIONS,
        now=_NOW,
    )

    costs = db.query(CostEvent).all()
    assert len(costs) == 1
    cost = costs[0]
    assert cost.user_id == watch.user_id
    assert cost.run_id == run.id
    assert cost.model == ModelKind.CLAUDE
    assert cost.tokens_in == 1200
    assert cost.tokens_out == 300
    assert cost.cost_usd == 0.0135


def test_digest_mode_writes_pending_notification() -> None:
    watch = _watch()
    run = _run(watch)
    db = FakeSession(watch, run)
    ev = _evaluation(EvalStatus.APPROVED)

    count = persist_run_results(
        db,
        run,
        watch,
        _state([ev]),
        embedding_model="hashing-768-v1",
        model_versions=_MODEL_VERSIONS,
        now=_NOW,
        digest=True,
    )

    assert count == 1
    notif = db.query(Notification).all()[0]
    assert notif.status == NotificationStatus.PENDING
    assert notif.delivered_at is None


def test_persists_provenance_but_no_notification_for_review() -> None:
    watch = _watch()
    run = _run(watch)
    db = FakeSession(watch, run)
    ev = _evaluation(EvalStatus.REVIEW)

    count = persist_run_results(
        db,
        run,
        watch,
        _state([ev]),
        embedding_model="hashing-768-v1",
        model_versions=_MODEL_VERSIONS,
        now=_NOW,
    )

    assert count == 0
    assert len(db.query(Item).all()) == 1
    assert len(db.query(Analysis).all()) == 1
    assert len(db.query(Evaluation).all()) == 1
    assert db.query(Notification).all() == []


def test_no_notification_when_draft_absent_from_state() -> None:
    # An approved item already delivered in a prior run: the notifier did
    # not re-emit it, so no dashboard row should be written either.
    watch = _watch()
    run = _run(watch)
    db = FakeSession(watch, run)
    ev = _evaluation(EvalStatus.APPROVED)

    count = persist_run_results(
        db,
        run,
        watch,
        _state([ev], notify=False),
        embedding_model="hashing-768-v1",
        model_versions=_MODEL_VERSIONS,
        now=_NOW,
    )

    assert count == 0
    assert len(db.query(Analysis).all()) == 1
    assert db.query(Notification).all() == []


# --- load_dedup_memory -----------------------------------------------------


def test_load_dedup_memory_returns_existing_hashes_and_keys() -> None:
    user_id = uuid.uuid4()
    item = Item(
        id=uuid.uuid4(),
        user_id=user_id,
        watch_id=uuid.uuid4(),
        source=SourceKind.JOBTECH,
        raw_payload={},
        content_hash="seen-hash",
    )
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        analysis_id=uuid.uuid4(),
        dedup_key="jobtech:7",
    )
    db = FakeSession(item, notif)

    seen, sent = load_dedup_memory(db, user_id)

    assert seen == {"seen-hash"}
    assert sent == {"jobtech:7"}
