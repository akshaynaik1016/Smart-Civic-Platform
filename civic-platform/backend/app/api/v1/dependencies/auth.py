"""FastAPI dependency injection — auth guards, role checks, pagination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import (
    ForbiddenError,
    TokenExpiredError,
    TokenRevokedError,
    UnauthorizedError,
)
from app.core.security import decode_token
from app.models.models import User, UserRole, UserStatus


# ---------------------------------------------------------------------
# Common dependencies
# ---------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------
# JWT token validation
# ---------------------------------------------------------------------

async def _get_token_claims(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
        Depends(bearer_scheme),
    ],
    request: Request,
) -> dict:

    print("\n========== AUTH DEBUG ==========")
    print("Authorization header:", request.headers.get("authorization"))
    print("Credentials object:", credentials)

    if not credentials or not credentials.credentials:
        print("No credentials received")
        raise UnauthorizedError("Missing Bearer token")

    token = credentials.credentials

    try:
        claims = decode_token(token)
        print("Decoded claims:", claims)
    except Exception as e:
        print("JWT ERROR:", e)
        raise

    return claims


# ---------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------

async def get_current_user(
    claims: Annotated[dict, Depends(_get_token_claims)],
    db: DbDep,
) -> User:
    user_id = claims.get("sub")

    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
    )

    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedError("User not found")

    if user.status == UserStatus.SUSPENDED:
        raise ForbiddenError("Account suspended")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------
# Role dependencies
# ---------------------------------------------------------------------

def require_roles(*roles: UserRole):
    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError(
                f"Requires role: {', '.join(role.value for role in roles)}"
            )
        return user

    return Annotated[User, Depends(_check)]


AdminRequired = require_roles(UserRole.ADMIN)

OfficerRequired = require_roles(
    UserRole.OFFICER,
    UserRole.ADMIN,
)


# ---------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------

@dataclass
class PaginationParams:
    page: int
    page_size: int
    sort_by: str
    sort_order: str

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


async def get_pagination(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
) -> PaginationParams:
    return PaginationParams(
        page=page,
        page_size=min(page_size, settings.MAX_PAGE_SIZE),
        sort_by=sort_by,
        sort_order=sort_order.lower(),
    )


PaginationDep = Annotated[
    PaginationParams,
    Depends(get_pagination),
]


# ---------------------------------------------------------------------
# Client IP
# ---------------------------------------------------------------------

async def get_client_ip(request: Request) -> str:
    """
    Best-effort client IP extraction.
    """

    forwarded = request.headers.get("X-Forwarded-For")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else None


ClientIp = Annotated[str, Depends(get_client_ip)]