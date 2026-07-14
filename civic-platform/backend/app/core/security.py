"""JWT token creation/verification and bcrypt password hashing."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def _build_claims(subject: str, extra: dict, expires_delta: timedelta) -> dict:
    now = datetime.now(timezone.utc)
    return {"sub": subject, "jti": str(uuid.uuid4()), "iat": now, "exp": now + expires_delta, **extra}

def create_access_token(user_id: str, role: str, email: str) -> tuple[str, str]:
    claims = _build_claims(user_id, {"role": role, "email": email, "type": "access"},
                           timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), claims["jti"]

def create_refresh_token(user_id: str) -> tuple[str, str]:
    claims = _build_claims(user_id, {"type": "refresh"},
                           timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS))
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), claims["jti"]

def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

def get_token_expiry_seconds(token: str) -> int:
    try:
        claims = decode_token(token)
        exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
        return max(int((exp - datetime.now(timezone.utc)).total_seconds()), 0)
    except JWTError:
        return 0
