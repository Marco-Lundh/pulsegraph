"""Auth endpoints: register and login (ADR 0005/0021)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.auth import (
    create_token,
    hash_password,
    verify_password,
)
from pulsegraph.api.deps import get_current_user, get_db
from pulsegraph.api.export import export_user_data
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
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> User:
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
    )
    db.add(user)
    db.flush()
    _audit(db, "user.register", actor_id=user.id, entity_id=user.id)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
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
) -> None:
    """Erase the caller's account and all their data (GDPR, ADR 0018).

    Every user-owned row cascades via ON DELETE CASCADE. The audit entry
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
    db.delete(user)
    db.commit()
