"""Tests for /watches CRUD."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.db.models import Watch
from pulsegraph.domain.enums import SourceKind

_NOW = datetime.datetime.now(datetime.UTC)


def _watch(user_id: uuid.UUID) -> Watch:
    return Watch(
        id=uuid.uuid4(),
        user_id=user_id,
        source=SourceKind.JOBTECH,
        prompt="python jobs",
        config={},
        is_active=True,
        schedule_interval=datetime.timedelta(hours=1),
        next_run_at=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )


# --- list ---


def test_list_watches_empty() -> None:
    client, _, _ = make_client()
    resp = client.get("/watches")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_watches_returns_own() -> None:
    client, user, _ = make_client()
    watch = _watch(user.id)
    db = FakeSession(user, watch)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.get("/watches")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_watches_excludes_other_users_watch() -> None:
    # FakeSession.filter() is a no-op, so list_watches must re-filter by
    # owner in Python too, or a foreign watch leaks into the response.
    client, user, _ = make_client()
    other_watch = _watch(uuid.uuid4())
    db = FakeSession(user, other_watch)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.get("/watches")
    assert resp.status_code == 200
    assert resp.json() == []


# --- create ---


def test_create_watch_returns_201() -> None:
    client, _, _ = make_client()
    resp = client.post(
        "/watches",
        json={
            "source": "jobtech",
            "prompt": "data engineer",
            "schedule_interval_seconds": 3600,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "jobtech"
    assert body["schedule_interval_seconds"] == 3600


def test_create_watch_interval_too_short_returns_422() -> None:
    client, _, _ = make_client()
    resp = client.post(
        "/watches",
        json={
            "source": "jobtech",
            "prompt": "x",
            "schedule_interval_seconds": 10,
        },
    )
    assert resp.status_code == 422


def test_create_watch_over_limit_returns_429() -> None:
    client, user, _ = make_client()
    watches = [_watch(user.id) for _ in range(20)]
    db = FakeSession(user, *watches)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.post(
        "/watches",
        json={
            "source": "jobtech",
            "prompt": "x",
            "schedule_interval_seconds": 3600,
        },
    )
    assert resp.status_code == 429


def test_create_watch_limit_ignores_other_users_watches() -> None:
    # Same FakeSession.filter()-is-a-no-op gotcha: the active-watch count
    # must re-filter by owner in Python, or other users' active watches
    # count against this user's limit.
    client, user, _ = make_client()
    other_watches = [_watch(uuid.uuid4()) for _ in range(20)]
    db = FakeSession(user, *other_watches)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.post(
        "/watches",
        json={
            "source": "jobtech",
            "prompt": "x",
            "schedule_interval_seconds": 3600,
        },
    )
    assert resp.status_code == 201


# --- get single ---


def test_get_watch_own_returns_200() -> None:
    client, user, _ = make_client()
    watch = _watch(user.id)
    db = FakeSession(user, watch)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.get(f"/watches/{watch.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(watch.id)


def test_get_watch_other_user_returns_404() -> None:
    client, user, _ = make_client()
    other_watch = _watch(uuid.uuid4())
    db = FakeSession(user, other_watch)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.get(f"/watches/{other_watch.id}")
    assert resp.status_code == 404


# --- update ---


def test_patch_watch_updates_prompt() -> None:
    client, user, _ = make_client()
    watch = _watch(user.id)
    db = FakeSession(user, watch)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.patch(f"/watches/{watch.id}", json={"prompt": "new prompt"})
    assert resp.status_code == 200
    assert watch.prompt == "new prompt"


# --- delete (soft) ---


def test_delete_watch_deactivates() -> None:
    client, user, _ = make_client()
    watch = _watch(user.id)
    db = FakeSession(user, watch)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.delete(f"/watches/{watch.id}")
    assert resp.status_code == 204
    assert watch.is_active is False
