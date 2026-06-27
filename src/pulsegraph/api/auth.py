"""Password hashing and JWT utilities (ADR 0005/0021)."""

import datetime
import uuid

import bcrypt
import jwt

from pulsegraph.config import get_settings

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    exp = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=settings.jwt_expire_hours
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": exp},
        settings.jwt_secret_key,
        algorithm=_ALGORITHM,
    )


def decode_token(token: str) -> uuid.UUID:
    settings = get_settings()
    payload = jwt.decode(
        token, settings.jwt_secret_key, algorithms=[_ALGORITHM]
    )
    return uuid.UUID(payload["sub"])
