"""Tests for GDPR erasure reaching the graph checkpointer (ADR 0001/0018)."""

import uuid

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.api.deps import get_checkpointer
from pulsegraph.api.erasure import purge_user_checkpoints
from pulsegraph.db.models import PipelineRun, User, Watch
from pulsegraph.domain.enums import SourceKind, UserRole


class _RecordingCheckpointer:
    """Fake checkpointer that records the threads it is asked to delete."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


def _watch(user_id: uuid.UUID) -> Watch:
    return Watch(
        id=uuid.uuid4(),
        user_id=user_id,
        source=SourceKind.JOBTECH,
        prompt="python",
    )


def _run(watch: Watch) -> PipelineRun:
    return PipelineRun(id=uuid.uuid4(), watch_id=watch.id)


# --- purge_user_checkpoints ------------------------------------------------


def test_purge_deletes_every_run_thread_of_the_user() -> None:
    uid = uuid.uuid4()
    w1, w2 = _watch(uid), _watch(uid)
    r1, r2, r3 = _run(w1), _run(w1), _run(w2)
    db = FakeSession(w1, w2, r1, r2, r3)
    checkpointer = _RecordingCheckpointer()

    deleted = purge_user_checkpoints(db, uid, checkpointer)

    assert deleted == 3
    assert set(checkpointer.deleted) == {str(r1.id), str(r2.id), str(r3.id)}


def test_purge_only_touches_the_users_own_runs() -> None:
    # FakeSession.filter() is a no-op, so the Python re-filter must keep a
    # purge from reaching another user's run checkpoints.
    uid, other = uuid.uuid4(), uuid.uuid4()
    mine, theirs = _watch(uid), _watch(other)
    my_run, their_run = _run(mine), _run(theirs)
    db = FakeSession(mine, theirs, my_run, their_run)
    checkpointer = _RecordingCheckpointer()

    purge_user_checkpoints(db, uid, checkpointer)

    assert checkpointer.deleted == [str(my_run.id)]


def test_purge_no_checkpointer_is_a_noop() -> None:
    uid = uuid.uuid4()
    w = _watch(uid)
    db = FakeSession(w, _run(w))
    # The local-first default backend yields None; nothing to delete.
    assert purge_user_checkpoints(db, uid, None) == 0


def test_purge_returns_zero_without_watches() -> None:
    checkpointer = _RecordingCheckpointer()
    assert (
        purge_user_checkpoints(FakeSession(), uuid.uuid4(), checkpointer) == 0
    )
    assert checkpointer.deleted == []


# --- endpoint wiring -------------------------------------------------------


def test_delete_account_purges_checkpoints() -> None:
    user = User(
        id=uuid.uuid4(),
        email="erase-me@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(user.id)
    run = _run(watch)
    db = FakeSession(user, watch, run)
    client, _, _ = make_client(db=db, user=user)

    checkpointer = _RecordingCheckpointer()
    client.app.dependency_overrides[get_checkpointer] = lambda: checkpointer

    resp = client.delete("/auth/me")

    assert resp.status_code == 204
    # The run's checkpoints were purged, and the user is gone.
    assert checkpointer.deleted == [str(run.id)]
    assert db.get(User, user.id) is None


def test_admin_delete_user_purges_checkpoints() -> None:
    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash="",
        role=UserRole.ADMIN,
    )
    target = User(
        id=uuid.uuid4(),
        email="target@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(target.id)
    run = _run(watch)
    db = FakeSession(admin, target, watch, run)
    client, _, _ = make_client(db=db, user=admin)

    checkpointer = _RecordingCheckpointer()
    client.app.dependency_overrides[get_checkpointer] = lambda: checkpointer

    resp = client.delete(f"/admin/users/{target.id}")

    assert resp.status_code == 204
    assert checkpointer.deleted == [str(run.id)]
