"""Tests for /auth/register and /auth/login."""

import datetime
import uuid

import fakeredis
from fastapi.testclient import TestClient

from pulsegraph import redis_client
from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.api.app import create_app
from pulsegraph.api.auth import decode_token, hash_password
from pulsegraph.api.deps import get_db, get_redis
from pulsegraph.db.models import AuditLogEntry, User
from pulsegraph.domain.enums import UserRole

# A fixed instant so a rate-limit burst never straddles a fixed-window
# boundary (which would reset the counter mid-burst — a real, rare flake).
_FROZEN = datetime.datetime(2026, 7, 7, 12, 0, tzinfo=datetime.UTC)


def _client(db: FakeSession) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: (yield db)
    # A fresh in-memory Redis so the auth rate limiter (ADR 0021) runs
    # without a live server; a per-client counter keeps tests independent.
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    return TestClient(app)


def _existing_user(email: str = "alice@example.com") -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("secret"),
        role=UserRole.USER,
    )


# --- register ---


def test_register_creates_user() -> None:
    db = FakeSession()
    resp = _client(db).post(
        "/auth/register",
        json={"email": "new@example.com", "password": "pw123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "user"
    assert "id" in body


def test_register_records_consent_timestamp() -> None:
    # GDPR (ADR 0018): consent / lawful basis is captured at signup.
    db = FakeSession()
    resp = _client(db).post(
        "/auth/register",
        json={"email": "consent@example.com", "password": "pw123"},
    )
    assert resp.status_code == 201
    user = db.query(User).all()[0]
    assert user.consented_at is not None


def test_register_duplicate_email_returns_409() -> None:
    user = _existing_user()
    db = FakeSession(user)
    resp = _client(db).post(
        "/auth/register",
        json={"email": user.email, "password": "anything"},
    )
    assert resp.status_code == 409


def test_register_new_email_with_other_users_seeded_succeeds() -> None:
    # FakeSession.filter() is a no-op, so the duplicate-email check must
    # re-match in Python, not just take the first stored User.
    other = _existing_user("someone-else@example.com")
    db = FakeSession(other)
    resp = _client(db).post(
        "/auth/register",
        json={"email": "brand-new@example.com", "password": "pw123"},
    )
    assert resp.status_code == 201


# --- login ---


def test_login_returns_bearer_token() -> None:
    user = _existing_user()
    db = FakeSession(user)
    resp = _client(db).post(
        "/auth/login",
        json={"email": user.email, "password": "secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 10


def test_login_wrong_password_returns_401() -> None:
    user = _existing_user()
    db = FakeSession(user)
    resp = _client(db).post(
        "/auth/login",
        json={"email": user.email, "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_email_returns_401() -> None:
    db = FakeSession()
    resp = _client(db).post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "x"},
    )
    assert resp.status_code == 401


def test_login_matches_correct_user_among_several() -> None:
    # Same FakeSession.filter()-is-a-no-op gotcha: login must re-match by
    # email in Python, not just take the first stored User. Both fixture
    # users share the same password, so a stale-match bug returns 200 with
    # the WRONG user's token rather than a visible 401 — decode it.
    first = _existing_user("first@example.com")
    second = _existing_user("second@example.com")
    db = FakeSession(first, second)
    resp = _client(db).post(
        "/auth/login",
        json={"email": second.email, "password": "secret"},
    )
    assert resp.status_code == 200
    assert decode_token(resp.json()["access_token"]) == second.id


# --- rate limiting (ADR 0021) ---


def test_login_rate_limited_after_burst(monkeypatch) -> None:
    # Default limit is 10 attempts per window per IP; the 11th is refused.
    # Freeze the clock so all 11 attempts fall in the same fixed window.
    monkeypatch.setattr(redis_client, "_now", lambda: _FROZEN)
    user = _existing_user()
    client = _client(FakeSession(user))

    last = None
    for _ in range(11):
        last = client.post(
            "/auth/login",
            json={"email": user.email, "password": "wrong"},
        )

    # The first 10 are the normal 401; the burst then trips the limiter.
    assert last.status_code == 429


def test_register_rate_limited_after_burst(monkeypatch) -> None:
    # Freeze the clock so all 11 attempts fall in the same fixed window.
    monkeypatch.setattr(redis_client, "_now", lambda: _FROZEN)
    client = _client(FakeSession())

    last = None
    for i in range(11):
        last = client.post(
            "/auth/register",
            json={"email": f"user{i}@example.com", "password": "pw123"},
        )

    assert last.status_code == 429


def test_login_fails_open_when_redis_unavailable() -> None:
    # A Redis outage must not take down auth: the rate-limit check fails
    # open, so a wrong-password login still returns its normal 401 (not 500).
    class _BrokenRedis:
        def incr(self, *args, **kwargs):
            raise ConnectionError("redis down")

        def expire(self, *args, **kwargs):  # pragma: no cover
            pass

    user = _existing_user()
    app = create_app()
    db = FakeSession(user)
    app.dependency_overrides[get_db] = lambda: (yield db)
    app.dependency_overrides[get_redis] = lambda: _BrokenRedis()
    resp = TestClient(app).post(
        "/auth/login",
        json={"email": user.email, "password": "wrong"},
    )

    assert resp.status_code == 401


# --- get current user ---


def test_get_me_returns_current_user() -> None:
    user = _existing_user()
    user.created_at = datetime.datetime.now(datetime.UTC)
    db = FakeSession(user)
    client, _, _ = make_client(db=db, user=user)

    resp = client.get("/auth/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user.email
    assert body["role"] == user.role


# --- delete account (GDPR erasure) ---


def test_delete_account_erases_user_and_audits() -> None:
    user = _existing_user()
    db = FakeSession(user)
    client, _, _ = make_client(db=db, user=user)

    resp = client.delete("/auth/me")

    assert resp.status_code == 204
    assert db.query(User).all() == []
    audits = db.query(AuditLogEntry).all()
    assert audits[-1].action == "user.delete"
    assert audits[-1].entity_id == user.id
    assert audits[-1].meta["email"] == user.email


# --- token decode ---


def test_missing_token_returns_403() -> None:
    # A fresh app with no dependency overrides; the bearer dep rejects it.
    plain_client = TestClient(create_app(), raise_server_exceptions=False)
    resp = plain_client.get("/watches")
    assert resp.status_code in (401, 403)
