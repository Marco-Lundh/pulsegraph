"""FastAPI dependency functions (ADR 0005/0021)."""

from collections.abc import Generator

import jwt
import redis as redis_lib
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pulsegraph.api.auth import decode_token
from pulsegraph.config import get_settings
from pulsegraph.db.models import User
from pulsegraph.pipeline.checkpointer import build_checkpointer
from pulsegraph.redis_client import make_redis

_bearer = HTTPBearer()

_engine = None
_SessionLocal = None
_redis: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    """Return a process-wide Redis client (ADR 0021/0022).

    Used by the auth endpoints for IP-based rate limiting. Overridden in
    tests with an in-memory fake so unit tests need no live Redis.
    """
    global _redis
    if _redis is None:
        _redis = make_redis(get_settings().redis_url)
    return _redis


def get_db() -> Generator[Session, None, None]:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = create_engine(get_settings().database_url)
        _SessionLocal = sessionmaker(bind=_engine)
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_checkpointer() -> Generator[object, None, None]:
    """Yield a graph checkpointer for the request, then release it.

    Used by the GDPR erasure endpoints to purge a user's run checkpoints
    (ADR 0001/0018). Built per request and closed after: erasure is rare,
    and for the local-first default backend (``none``) this is a cheap
    ``(None, no-op)``. Overridden in tests to inject a fake checkpointer.
    """
    checkpointer, close = build_checkpointer(get_settings())
    try:
        yield checkpointer
    finally:
        close()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        user_id = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    from pulsegraph.domain.enums import UserRole

    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
