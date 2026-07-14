"""
OfficerService
===============
Business logic for officer management, distinct from AuthService.register_officer
(which only creates the User+Officer rows at onboarding). This service owns
the operational lifecycle afterward: availability toggling, ward/category
reassignment, performance recalculation, and workload-aware assignment
suggestions for the admin dashboard's "assign complaint" flow.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.models import Officer, User, UserRole
from app.repositories.officer_repository import OfficerRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class OfficerService:
    def __init__(
        self, db: AsyncSession, officer_repo: OfficerRepository, user_repo: UserRepository,
    ) -> None:
        self._db = db
        self._officers = officer_repo
        self._users = user_repo

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def get_officer(self, officer_id: str, requester: User) -> Officer:
        officer = await self._officers.get_by_id(officer_id)
        if not officer:
            raise NotFoundError("Officer", officer_id)

        is_self = officer.user_id == requester.id
        if not is_self and requester.role != UserRole.ADMIN:
            raise ForbiddenError("You can only view your own officer profile.")
        return officer

    async def get_my_officer_profile(self, user: User) -> Officer:
        officer = await self._officers.get_by_user_id(str(user.id))
        if not officer:
            raise NotFoundError("Officer profile", str(user.id))
        return officer

    async def list_officers(
        self, requester: User, *, department: Optional[str] = None, ward_id: Optional[int] = None,
        is_available: Optional[bool] = None, search: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple:
        if requester.role not in (UserRole.ADMIN, UserRole.OFFICER):
            raise ForbiddenError("Insufficient permissions.")
        officers, total = await self._officers.list_officers(
            department=department, ward_id=ward_id, is_available=is_available,
            search=search, page=page, page_size=page_size,
        )
        import math
        pages = math.ceil(total / page_size) if page_size else 1
        return officers, total, pages

    # ── Self-service updates ─────────────────────────────────────────────────

    async def update_my_availability(self, user: User, is_available: bool) -> Officer:
        officer = await self._officers.get_by_user_id(str(user.id))
        if not officer:
            raise NotFoundError("Officer profile", str(user.id))
        return await self._officers.update_availability(str(officer.id), is_available)

    # ── Admin actions ─────────────────────────────────────────────────────────

    async def update_assignment_scope(
        self, officer_id: str, admin: User,
        ward_ids: Optional[list[int]] = None, category_ids: Optional[list[int]] = None,
    ) -> Officer:
        self._require_admin(admin)
        officer = await self._officers.get_by_id(officer_id)
        if not officer:
            raise NotFoundError("Officer", officer_id)
        return await self._officers.update_assignment_scope(officer_id, ward_ids, category_ids)

    async def update_max_complaints(self, officer_id: str, admin: User, max_complaints: int) -> Officer:
        self._require_admin(admin)
        if max_complaints < 1 or max_complaints > 200:
            raise BadRequestError("max_complaints must be between 1 and 200.")
        officer = await self._officers.get_by_id(officer_id)
        if not officer:
            raise NotFoundError("Officer", officer_id)
        if max_complaints < officer.total_assigned:
            raise BadRequestError(
                f"Cannot set max_complaints ({max_complaints}) below the officer's "
                f"current workload ({officer.total_assigned}). Reassign complaints first."
            )
        return await self._officers.update_fields(officer_id, max_complaints=max_complaints)

    async def deactivate_officer(self, officer_id: str, admin: User) -> None:
        """
        Soft-delete an officer profile (e.g. transfer/resignation). Does NOT
        touch their already-assigned complaints — those remain assigned
        until an admin explicitly reassigns them via the complaints API,
        since silently orphaning active complaints would be worse than
        leaving them visibly assigned to a now-inactive officer.
        """
        self._require_admin(admin)
        officer = await self._officers.get_by_id(officer_id)
        if not officer:
            raise NotFoundError("Officer", officer_id)
        if officer.total_assigned > 0:
            logger.warning(
                "Deactivating officer %s with %d active complaints still assigned — "
                "these will need manual reassignment.",
                officer.badge_number, officer.total_assigned,
            )
        await self._officers.soft_delete(officer_id)

    # ── Smart assignment suggestions ─────────────────────────────────────────

    async def suggest_officers_for_complaint(
        self, requester: User, ward_id: Optional[int] = None,
        category_id: Optional[int] = None, limit: int = 5,
    ) -> list[dict]:
        """
        Powers the "suggested officers" panel in the admin assign-complaint
        drawer: officers scoped to the right ward/category, with spare
        capacity, sorted lightest-workload-first so assignments stay balanced
        rather than always landing on whoever's listed first alphabetically.
        """
        if requester.role not in (UserRole.ADMIN, UserRole.OFFICER):
            raise ForbiddenError("Insufficient permissions.")

        candidates = await self._officers.find_available_for_assignment(
            ward_id=ward_id, category_id=category_id, limit=limit,
        )
        return [
            {
                "officer_id":     str(o.id),
                "name":           o.user.full_name if o.user else None,
                "badge_number":   o.badge_number,
                "department":     o.department,
                "current_load":   o.total_assigned,
                "max_complaints": o.max_complaints,
                "performance_score": float(o.performance_score),
            }
            for o in candidates
        ]

    # ── Performance ───────────────────────────────────────────────────────────

    async def recalculate_performance(self, officer_id: str) -> float:
        return await self._officers.recalculate_performance_score(officer_id)

    async def get_workload(self, officer_id: str, requester: User) -> dict:
        officer = await self.get_officer(officer_id, requester)
        return await self._officers.get_workload_summary(officer_id)

    # ── Guards ────────────────────────────────────────────────────────────────

    @staticmethod
    def _require_admin(user: User) -> None:
        if user.role != UserRole.ADMIN:
            raise ForbiddenError("Admin access required.")
