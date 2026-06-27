"""Auth endpoints: register and login (ADR 0005/0021)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.auth import (
    create_token,
    hash_password,
    verify_password,
)
from pulsegraph.api.deps import get_db
from pulsegraph.api.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from pulsegraph.db.models import AuditLogEntry, User
from pulsegraph.domain.enums import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


def _audit(
    db: Session, action: str, actor_id: object = None, entity_id: object = None
) -> None:
    db.add(
        AuditLogEntry(
            actor_user_id=actor_id,
            action=action,
            entity_type="user",
            entity_id=entity_id,
            meta={},
        )
    )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=UserRole.USER,
    )
    db.add(user)
    db.flush()
    _audit(db, "user.register", actor_id=user.id, entity_id=user.id)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    _audit(db, "user.login", actor_id=user.id, entity_id=user.id)
    db.commit()
    return {"access_token": create_token(user.id), "token_type": "bearer"}
