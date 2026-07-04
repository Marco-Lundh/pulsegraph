"""Tests for /auth/register and /auth/login."""

import datetime
import uuid

from fastapi.testclient import TestClient

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.api.app import create_app
from pulsegraph.api.auth import hash_password
from pulsegraph.api.deps import get_db
from pulsegraph.db.models import AuditLogEntry, User
from pulsegraph.domain.enums import UserRole


def _client(db: FakeSession) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: (yield db)
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


def test_register_duplicate_email_returns_409() -> None:
    user = _existing_user()
    db = FakeSession(user)
    resp = _client(db).post(
        "/auth/register",
        json={"email": user.email, "password": "anything"},
    )
    assert resp.status_code == 409


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
