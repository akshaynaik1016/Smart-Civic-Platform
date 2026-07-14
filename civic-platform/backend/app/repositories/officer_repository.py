"""
OfficerRepository — every database operation that touches the `officers` table.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Officer, User


class OfficerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, officer_id: str, *, include_deleted: bool = False) -> Optional[Officer]:
        q = select(Officer).options(selectinload(Officer.user)).where(Officer.id == officer_id)
        if not include_deleted:
            q = q.where(Officer.deleted_at.is_(None))
        return (await self._db.execute(q)).scalar_one_or_none()

    async def get_by_user_id(self, user_id: str) -> Optional[Officer]:
        q = (
            select(Officer)
            .options(selectinload(Officer.user))
            .where(Officer.user_id == user_id, Officer.deleted_at.is_(None))
        )
        return (await self._db.execute(q)).scalar_one_or_none()

    async def get_by_badge_number(self, badge_number: str) -> Optional[Officer]:
        q = select(Officer).where(Officer.badge_number == badge_number)
        return (await self._db.execute(q)).scalar_one_or_none()

    async def badge_number_exists(self, badge_number: str, exclude_id: Optional[str] = None) -> bool:
        q = select(func.count()).where(Officer.badge_number == badge_number)
        if exclude_id:
            q = q.where(Officer.id != exclude_id)
        return ((await self._db.execute(q)).scalar() or 0) > 0

    async def create(self, **kwargs) -> Officer:
        officer = Officer(**kwargs)
        self._db.add(officer)
        await self._db.flush()
        await self._db.refresh(officer)
        return officer

    async def update_fields(self, officer_id: str, **kwargs) -> Optional[Officer]:
        await self._db.execute(update(Officer).where(Officer.id == officer_id).values(**kwargs))
        return await self.get_by_id(officer_id)

    async def soft_delete(self, officer_id: str) -> None:
        from datetime import datetime, timezone
        await self._db.execute(
            update(Officer).where(Officer.id == officer_id).values(deleted_at=datetime.now(timezone.utc))
        )

    async def list_officers(
        self,
        *,
        department: Optional[str] = None,
        ward_id: Optional[int] = None,
        is_available: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Officer], int]:
        filters = [Officer.deleted_at.is_(None)]
        if department:
            filters.append(Officer.department == department)
        if ward_id is not None:
            filters.append(Officer.ward_ids.any(ward_id))
        if is_available is not None:
            filters.append(Officer.is_available == is_available)

        q = select(Officer).options(selectinload(Officer.user)).where(and_(*filters))
        count_q = select(func.count()).select_from(Officer).where(and_(*filters))

        if search:
            term = f"%{search.lower()}%"
            q = q.join(User, Officer.user_id == User.id).where(
                or_(func.lower(User.full_name).like(term), Officer.badge_number.ilike(term))
            )
            count_q = count_q.join(User, Officer.user_id == User.id).where(
                or_(func.lower(User.full_name).like(term), Officer.badge_number.ilike(term))
            )

        total = (await self._db.execute(count_q)).scalar() or 0
        rows = (
            await self._db.execute(
                q.order_by(Officer.performance_score.desc())
                 .limit(page_size).offset((page - 1) * page_size)
            )
        ).scalars().all()
        return rows, total

    async def find_available_for_assignment(
        self, ward_id: Optional[int] = None, category_id: Optional[int] = None, limit: int = 10,
    ) -> Sequence[Officer]:
        """Officers with capacity, optionally scoped to a ward/category, sorted by lightest workload first."""
        filters = [
            Officer.deleted_at.is_(None),
            Officer.is_available.is_(True),
            Officer.total_assigned < Officer.max_complaints,
        ]
        if ward_id is not None:
            filters.append(Officer.ward_ids.any(ward_id))
        if category_id is not None:
            filters.append(Officer.category_ids.any(category_id))

        q = (
            select(Officer).options(selectinload(Officer.user))
            .where(and_(*filters))
            .order_by(Officer.total_assigned.asc())
            .limit(limit)
        )
        return (await self._db.execute(q)).scalars().all()

    async def update_availability(self, officer_id: str, is_available: bool) -> Optional[Officer]:
        return await self.update_fields(officer_id, is_available=is_available)

    async def update_assignment_scope(
        self, officer_id: str, ward_ids: Optional[list[int]] = None, category_ids: Optional[list[int]] = None,
    ) -> Optional[Officer]:
        updates = {}
        if ward_ids is not None:
            updates["ward_ids"] = ward_ids
        if category_ids is not None:
            updates["category_ids"] = category_ids
        if not updates:
            return await self.get_by_id(officer_id)
        return await self.update_fields(officer_id, **updates)

    async def recalculate_performance_score(self, officer_id: str) -> float:
        """
        Performance score (0-100):
          resolution_rate component (60 pts) = (resolved/assigned) * 60
          speed component (40 pts)            = faster avg_resolution_days scores higher,
                                                  capped at 40, scaled against a 7-day baseline
        """
        officer = await self.get_by_id(officer_id)
        if not officer or officer.total_assigned == 0:
            return 0.0

        resolution_rate = officer.total_resolved / officer.total_assigned
        rate_score = resolution_rate * 60

        speed_score = 0.0
        if officer.avg_resolution_days is not None and float(officer.avg_resolution_days) > 0:
            baseline_days = 7.0
            speed_score = max(0.0, min(40.0, (baseline_days / float(officer.avg_resolution_days)) * 40))

        score = round(min(100.0, rate_score + speed_score), 2)
        await self.update_fields(officer_id, performance_score=score)
        return score

    async def get_workload_summary(self, officer_id: str) -> dict:
        officer = await self.get_by_id(officer_id)
        if not officer:
            return {}
        return {
            "total_assigned": officer.total_assigned,
            "max_complaints": officer.max_complaints,
            "available_capacity": max(0, officer.max_complaints - officer.total_assigned),
            "workload_pct": round((officer.total_assigned / officer.max_complaints) * 100, 1)
                            if officer.max_complaints else 0,
        }
