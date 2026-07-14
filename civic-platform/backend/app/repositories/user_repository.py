"""
UserRepository — every database operation that touches the `users` table.

All methods accept an AsyncSession and return ORM objects or None.
No business logic here — only data access.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import AuditLog, Officer, User, UserRole, UserStatus


class UserRepository:
    """Async data-access object for the users table."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Lookups ──────────────────────────────────────────────────────────────

    async def get_by_id(self, user_id: str, *, include_deleted: bool = False) -> Optional[User]:
        """Fetch a user by primary key."""
        q = select(User).where(User.id == user_id)
        if not include_deleted:
            q = q.where(User.deleted_at.is_(None))
        result = await self._db.execute(q)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str, *, include_deleted: bool = False) -> Optional[User]:
        """Fetch a user by (lower-cased) email."""
        q = select(User).where(User.email == email.lower().strip())
        if not include_deleted:
            q = q.where(User.deleted_at.is_(None))
        result = await self._db.execute(q)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str, *, include_deleted: bool = False) -> Optional[User]:
        q = select(User).where(User.phone == phone)
        if not include_deleted:
            q = q.where(User.deleted_at.is_(None))
        result = await self._db.execute(q)
        return result.scalar_one_or_none()

    async def get_with_officer_profile(self, user_id: str) -> Optional[User]:
        """Fetch user eagerly loading officer_profile relationship."""
        q = (
            select(User)
            .options(selectinload(User.officer_profile))
            .where(User.id == user_id, User.deleted_at.is_(None))
        )
        result = await self._db.execute(q)
        return result.scalar_one_or_none()

    # ── Existence checks ─────────────────────────────────────────────────────

    async def email_exists(self, email: str, exclude_id: Optional[str] = None) -> bool:
        q = select(func.count()).where(
            User.email == email.lower(), User.deleted_at.is_(None)
        )
        if exclude_id:
            q = q.where(User.id != exclude_id)
        result = await self._db.execute(q)
        return (result.scalar() or 0) > 0

    async def phone_exists(self, phone: str, exclude_id: Optional[str] = None) -> bool:
        q = select(func.count()).where(
            User.phone == phone, User.deleted_at.is_(None)
        )
        if exclude_id:
            q = q.where(User.id != exclude_id)
        result = await self._db.execute(q)
        return (result.scalar() or 0) > 0

    # ── Create ───────────────────────────────────────────────────────────────

    async def create(self, **kwargs) -> User:
        """Insert a new user row and flush to get the generated ID."""
        user = User(**kwargs)
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    # ── Update ───────────────────────────────────────────────────────────────

    async def update_fields(self, user_id: str, **kwargs) -> Optional[User]:
        """Patch specific columns and return the refreshed object."""
        await self._db.execute(
            update(User).where(User.id == user_id).values(**kwargs)
        )
        return await self.get_by_id(user_id)

    async def mark_email_verified(self, user_id: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                email_verified=True,
                email_verified_at=datetime.now(timezone.utc),
                status=UserStatus.ACTIVE,
            )
        )

    async def mark_phone_verified(self, user_id: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                phone_verified=True,
                phone_verified_at=datetime.now(timezone.utc),
            )
        )

    async def update_password(self, user_id: str, password_hash: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash)
        )

    async def update_last_login(self, user_id: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )

    async def update_status(self, user_id: str, status: UserStatus) -> Optional[User]:
        return await self.update_fields(user_id, status=status)

    async def update_role(self, user_id: str, role: UserRole) -> Optional[User]:
        return await self.update_fields(user_id, role=role)

    async def update_avatar(self, user_id: str, avatar_url: str) -> Optional[User]:
        return await self.update_fields(user_id, avatar_url=avatar_url)

    async def update_reputation(self, user_id: str, score: float) -> None:
        # Clamp to [0, 100]
        clamped = max(0.0, min(100.0, score))
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(reputation_score=clamped)
        )

    async def increment_complaint_counts(
        self, user_id: str, *, resolved: bool = False
    ) -> None:
        values: dict = {"total_complaints": User.total_complaints + 1}
        if resolved:
            values["resolved_complaints"] = User.resolved_complaints + 1
        await self._db.execute(update(User).where(User.id == user_id).values(**values))

    # ── Soft delete ───────────────────────────────────────────────────────────

    async def soft_delete(self, user_id: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(deleted_at=datetime.now(timezone.utc), status=UserStatus.INACTIVE)
        )

    # ── List / search ─────────────────────────────────────────────────────────

    async def list_users(
        self,
        *,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        ward_id: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[Sequence[User], int]:
        """
        Return (users, total_count) with filtering, search, and pagination.
        """
        filters = [User.deleted_at.is_(None)]

        if role:
            filters.append(User.role == role)
        if status:
            filters.append(User.status == status)
        if ward_id is not None:
            filters.append(User.ward_id == ward_id)
        if search:
            term = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(User.full_name).like(term),
                    func.lower(User.email).like(term),
                    User.phone.like(term),
                )
            )

        # Count query
        count_q = select(func.count()).where(and_(*filters))
        total = (await self._db.execute(count_q)).scalar() or 0

        # Data query with sorting and pagination
        safe_sort_cols = {"created_at", "full_name", "email", "reputation_score", "total_complaints"}
        sort_col = getattr(User, sort_by) if sort_by in safe_sort_cols else User.created_at
        if sort_order == "desc":
            sort_col = sort_col.desc()

        data_q = (
            select(User)
            .where(and_(*filters))
            .order_by(sort_col)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = (await self._db.execute(data_q)).scalars().all()
        return rows, total

    # ── Analytics ─────────────────────────────────────────────────────────────

    async def count_by_role(self) -> dict[str, int]:
        q = (
            select(User.role, func.count().label("cnt"))
            .where(User.deleted_at.is_(None))
            .group_by(User.role)
        )
        rows = (await self._db.execute(q)).all()
        return {row.role: row.cnt for row in rows}

    async def count_active(self) -> int:
        q = select(func.count()).where(
            User.deleted_at.is_(None),
            User.status == UserStatus.ACTIVE,
        )
        return (await self._db.execute(q)).scalar() or 0

    async def top_reporters(self, limit: int = 10) -> Sequence[User]:
        q = (
            select(User)
            .where(User.deleted_at.is_(None), User.role == UserRole.CITIZEN)
            .order_by(User.total_complaints.desc())
            .limit(limit)
        )
        return (await self._db.execute(q)).scalars().all()
