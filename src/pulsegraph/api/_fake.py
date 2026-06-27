"""In-memory test doubles for the FastAPI dependency layer."""

import datetime
import uuid
from collections.abc import Generator
from typing import Any

_DATETIME_ATTRS = (
    "created_at",
    "updated_at",
    "evaluated_at",
    "last_checked_at",
    "next_run_at",
    "decided_at",
)

from fastapi.testclient import TestClient

from pulsegraph.api.app import create_app
from pulsegraph.api.auth import create_token
from pulsegraph.api.deps import get_current_user, get_db
from pulsegraph.db.models import User
from pulsegraph.domain.enums import UserRole

# ---------------------------------------------------------------------------
# FakeSession
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, items: list) -> None:
        self._items = list(items)

    # Filters are intentionally ignored; callers pre-load only relevant rows.
    def filter(self, *_args: Any) -> "_FakeQuery":
        return self

    def filter_by(self, **_kw: Any) -> "_FakeQuery":
        return self

    def order_by(self, *_args: Any) -> "_FakeQuery":
        return self

    def all(self) -> list:
        return self._items

    def first(self) -> Any:
        return self._items[0] if self._items else None

    def count(self) -> int:
        return len(self._items)

    def in_(self, _values: Any) -> "_FakeQuery":  # noqa: D401
        return self


class FakeSession:
    """Minimal SQLAlchemy Session stand-in for unit tests."""

    def __init__(self, *seed: Any) -> None:
        self._store: dict[type, list] = {}
        self.added: list = []
        for obj in seed:
            self._put(obj)

    def _put(self, obj: Any) -> None:
        self._store.setdefault(type(obj), []).append(obj)

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        self._put(obj)

    def _apply_defaults(self, obj: Any) -> None:
        now = datetime.datetime.now(datetime.UTC)
        for attr in _DATETIME_ATTRS:
            if hasattr(obj, attr) and getattr(obj, attr) is None:
                setattr(obj, attr, now)
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()

    def flush(self) -> None:
        for obj in self.added:
            self._apply_defaults(obj)
        self.added.clear()

    def commit(self) -> None:
        pass

    def refresh(self, _obj: Any) -> None:
        pass

    def close(self) -> None:
        pass

    def get(self, model: type, pk: Any) -> Any:
        return next(
            (o for o in self._store.get(model, []) if o.id == pk), None
        )

    def query(self, *models: Any) -> "_FakeQuery":
        # Support query(Model.column) by resolving the parent class.
        resolved = []
        for m in models:
            cls = m if isinstance(m, type) else getattr(m, "class_", None)
            if cls:
                resolved.extend(self._store.get(cls, []))
        return _FakeQuery(resolved)


# ---------------------------------------------------------------------------
# Helpers to build TestClient with optional auth
# ---------------------------------------------------------------------------


def _make_user(role: UserRole = UserRole.USER) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{role}@example.com",
        password_hash="",
        role=role,
    )


def make_client(
    db: FakeSession | None = None,
    user: User | None = None,
) -> tuple[TestClient, User, str]:
    """Return (client, user, bearer_token) with all deps overridden."""
    app = create_app()
    _user = user or _make_user()
    _db = db or FakeSession(_user)
    token = create_token(_user.id)

    def _fake_db() -> Generator:
        yield _db

    def _fake_user() -> User:
        return _user

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app), _user, token
