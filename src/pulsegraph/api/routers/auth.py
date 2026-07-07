"""Auth endpoints: register and login (ADR 0005/0021)."""

import datetime
import logging

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from pulsegraph.api.auth import (
    create_token,
    hash_password,
    verify_password,
)
from pulsegraph.api.deps import (
    get_checkpointer,
    get_current_user,
    get_db,
    get_redis,
)
from pulsegraph.api.erasure import purge_user_checkpoints
from pulsegraph.api.export import export_user_data
from pulsegraph.api.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from pulsegraph.config import get_settings
from pulsegraph.db.models import AuditLogEntry, User
from pulsegraph.domain.enums import UserRole
from pulsegraph.redis_client import check_fixed_window

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Return the caller's IP for rate-limit keying (ADR 0021).

    Uses the direct connection's address, which is not spoofable via an
    ``X-Forwarded-For`` header. NOTE: behind a reverse proxy this is the
    proxy's address, which would collapse every client into one bucket, so
    a proxied deployment MUST run uvicorn with ``--forwarded-allow-ips`` (or
    an equivalent trusted-proxy middleware) so ``request.client.host`` is
    the real client IP before this limiter is relied on.
    """
    return request.client.host if request.client else "unknown"


def _enforce_auth_rate(
    r: redis_lib.Redis, request: Request, action: str
) -> None:
    """Brute-force-guard an auth action, keyed on the caller's IP (ADR 0021).

    Raises 429 once more than ``auth_rate_limit`` attempts for this action
    come from the same IP inside the window. login and register carry
    independent budgets (distinct keys). Fails open: if the Redis check
    errors (e.g. an outage) the request is allowed rather than 500'd, so a
    Redis problem degrades brute-force protection instead of taking down
    authentication entirely.
    """
    settings = get_settings()
    key = f"authrate:{action}:{_client_ip(request)}"
    try:
        within = check_fixed_window(
            r,
            key,
            settings.auth_rate_limit,
            settings.auth_rate_window_seconds,
        )
    except Exception:
        logger.warning(
            "auth rate-limit check unavailable; allowing %s",
            action,
            exc_info=True,
        )
        return
    if not within:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts; try again later",
        )


def _audit(
    db: Session,
    action: str,
    actor_id: object = None,
    entity_id: object = None,
    meta: dict | None = None,
) -> None:
    db.add(
        AuditLogEntry(
            actor_user_id=actor_id,
            action=action,
            entity_type="user",
            entity_id=entity_id,
            meta=meta or {},
        )
    )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    body: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
) -> User:
    _enforce_auth_rate(r, request, "register")
    # FakeSession.filter() is a no-op in tests, so re-match in Python too
    # (mirrors the pattern used throughout worker/*.py and api/export.py).
    existing = next(
        (
            u
            for u in db.query(User).filter(User.email == body.email).all()
            if u.email == body.email
        ),
        None,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=UserRole.USER,
        # Record consent / lawful basis at signup (GDPR, ADR 0018).
        consented_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(user)
    db.flush()
    _audit(db, "user.register", actor_id=user.id, entity_id=user.id)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
) -> dict:
    _enforce_auth_rate(r, request, "login")
    user = next(
        (
            u
            for u in db.query(User).filter(User.email == body.email).all()
            if u.email == body.email
        ),
        None,
    )
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    _audit(db, "user.login", actor_id=user.id, entity_id=user.id)
    db.commit()
    return {"access_token": create_token(user.id), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/me/export")
def export_account(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Export all personal data for the caller (GDPR portability, ADR 0018).

    Returns a JSON document of every record keyed to the user. The export
    itself is recorded in the audit log.
    """
    _audit(db, "user.export", actor_id=user.id, entity_id=user.id)
    db.commit()
    return export_user_data(db, user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    checkpointer: object = Depends(get_checkpointer),
) -> None:
    """Erase the caller's account and all their data (GDPR, ADR 0018).

    Every user-owned row cascades via ON DELETE CASCADE. The user's graph
    checkpoints are not FK-linked, so they are purged explicitly first,
    while the runs are still queryable (ADR 0001/0018). The audit entry
    keeps the user id (``entity_id``) and email so the erasure stays
    provable after the row is gone — ``actor_user_id`` is set null when
    the user is deleted.
    """
    _audit(
        db,
        "user.delete",
        actor_id=user.id,
        entity_id=user.id,
        meta={"email": user.email},
    )
    purge_user_checkpoints(db, user.id, checkpointer)
    db.delete(user)
    db.commit()
