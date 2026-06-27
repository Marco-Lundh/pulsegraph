"""FastAPI dependency functions (ADR 0005/0021)."""

from collections.abc import Generator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pulsegraph.api.auth import decode_token
from pulsegraph.config import get_settings
from pulsegraph.db.models import User

_bearer = HTTPBearer()

_engine = None
_SessionLocal = None


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
        )
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
