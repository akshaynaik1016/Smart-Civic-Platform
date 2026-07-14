"""
UserService — business logic for user profile management.

Responsibilities:
  • Profile CRUD (self-service and admin)
  • Role promotion / demotion (admin only)
  • Account status management (suspend, reactivate, soft-delete)
  • Avatar upload to S3
  • Reputation score recalculation
  • Admin user listing with filters and pagination
  • Activity summary for profile page
"""

from __future__ import annotations

import io
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.models.models import (
    AuditAction,
    Complaint,
    ComplaintStatus,
    User,
    UserRole,
    UserStatus,
)
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    """Stateless service — state lives in DB via UserRepository and S3."""

    def __init__(self, db: AsyncSession, user_repo: UserRepository) -> None:
        self._db    = db
        self._users = user_repo

    # ── Profile retrieval ─────────────────────────────────────────────────────

    async def get_profile(self, user_id: str, requester: User) -> User:
        """
        Return a user profile.
        Citizens can only view their own profile;
        officers and admins can view any profile.
        """
        if (
            str(requester.id) != user_id
            and requester.role not in (UserRole.ADMIN, UserRole.OFFICER)
        ):
            raise ForbiddenError("You can only view your own profile.")

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        return user

    # ── Profile update ────────────────────────────────────────────────────────

    async def update_profile(
        self,
        user_id: str,
        requester: User,
        *,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        ward_id: Optional[int] = None,
        city: Optional[str] = None,
        pincode: Optional[str] = None,
    ) -> User:
        """
        Update mutable profile fields.
        Only self-service or admin.
        """
        if str(requester.id) != user_id and requester.role != UserRole.ADMIN:
            raise ForbiddenError("Cannot update another user's profile.")

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)

        updates: dict = {}

        if full_name is not None:
            name = full_name.strip()
            if len(name) < 2:
                raise BadRequestError("Name must be at least 2 characters.")
            updates["full_name"] = name

        if phone is not None:
            digits = "".join(c for c in phone if c.isdigit())
            if len(digits) < 10:
                raise BadRequestError("Phone must have at least 10 digits.")
            if await self._users.phone_exists(digits, exclude_id=user_id):
                raise ConflictError("This phone number is already registered.")
            updates["phone"] = digits

        if ward_id is not None:
            updates["ward_id"] = ward_id

        if city is not None:
            updates["city"] = city.strip()

        if pincode is not None:
            updates["pincode"] = pincode.strip()

        if not updates:
            return user

        updated = await self._users.update_fields(user_id, **updates)
        logger.info("Profile updated", extra={"user_id": user_id, "fields": list(updates)})
        return updated

    # ── Avatar ────────────────────────────────────────────────────────────────

    async def upload_avatar(
        self,
        user_id: str,
        image_bytes: bytes,
        content_type: str,
        requester: User,
    ) -> str:
        """
        Upload avatar image to S3 and update the user's avatar_url.
        Returns the CDN URL.
        """
        if str(requester.id) != user_id and requester.role != UserRole.ADMIN:
            raise ForbiddenError("Cannot update another user's avatar.")

        if len(image_bytes) > settings.max_upload_bytes:
            raise BadRequestError(f"Image must be under {settings.MAX_UPLOAD_SIZE_MB} MB.")

        allowed = {"image/jpeg", "image/png", "image/webp"}
        if content_type not in allowed:
            raise BadRequestError(f"Unsupported image type: {content_type}. Use JPEG, PNG, or WebP.")

        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
        s3_key = f"avatars/{user_id}/{uuid.uuid4().hex}.{ext}"

        try:
            from app.services.storage_service import StorageService
            cdn_url = await StorageService().upload_bytes(
                key=s3_key,
                data=image_bytes,
                content_type=content_type,
                public=True,
            )
        except Exception as exc:
            logger.error("Avatar upload failed", extra={"user_id": user_id, "error": str(exc)})
            raise BadRequestError("Failed to upload avatar. Please try again.")

        await self._users.update_avatar(user_id, cdn_url)
        logger.info("Avatar uploaded", extra={"user_id": user_id, "s3_key": s3_key})
        return cdn_url

    # ── Admin: status management ──────────────────────────────────────────────

    async def suspend_user(
        self,
        user_id: str,
        admin: User,
        reason: Optional[str] = None,
    ) -> User:
        """Admin-only: suspend a user account."""
        self._require_admin(admin)

        if str(admin.id) == user_id:
            raise BadRequestError("Cannot suspend your own account.")

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        if user.status == UserStatus.SUSPENDED:
            raise BadRequestError("User is already suspended.")
        if user.role == UserRole.ADMIN:
            raise ForbiddenError("Cannot suspend another admin.")

        updated = await self._users.update_status(user_id, UserStatus.SUSPENDED)
        logger.info("User suspended", extra={
            "user_id": user_id, "by": str(admin.id), "reason": reason,
        })
        return updated

    async def reactivate_user(self, user_id: str, admin: User) -> User:
        """Admin-only: restore a suspended user."""
        self._require_admin(admin)

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        if user.status not in (UserStatus.SUSPENDED, UserStatus.INACTIVE):
            raise BadRequestError("User is not suspended or inactive.")

        updated = await self._users.update_status(user_id, UserStatus.ACTIVE)
        logger.info("User reactivated", extra={"user_id": user_id, "by": str(admin.id)})
        return updated

    async def delete_user(self, user_id: str, admin: User) -> None:
        """Admin-only: soft-delete a user account."""
        self._require_admin(admin)

        if str(admin.id) == user_id:
            raise BadRequestError("Cannot delete your own account.")

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        if user.role == UserRole.ADMIN:
            raise ForbiddenError("Cannot delete another admin account.")

        await self._users.soft_delete(user_id)
        logger.info("User deleted (soft)", extra={"user_id": user_id, "by": str(admin.id)})

    async def change_user_role(
        self,
        user_id: str,
        new_role: UserRole,
        admin: User,
    ) -> User:
        """Admin-only: promote or demote a user's role."""
        self._require_admin(admin)

        if str(admin.id) == user_id:
            raise BadRequestError("Cannot change your own role.")

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)

        # Guard: removing the last admin is not allowed
        if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
            counts = await self._users.count_by_role()
            if counts.get(UserRole.ADMIN, 0) <= 1:
                raise BadRequestError("Cannot demote the last admin account.")

        updated = await self._users.update_role(user_id, new_role)
        logger.info("Role changed", extra={
            "user_id": user_id, "from": user.role, "to": new_role, "by": str(admin.id),
        })
        return updated

    # ── Listing (admin) ───────────────────────────────────────────────────────

    async def list_users(
        self,
        requester: User,
        *,
        role: Optional[str] = None,
        status: Optional[str] = None,
        ward_id: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple:
        """
        Paginated user list.
        Admins see everyone; officers see citizens in their ward only.
        """
        if requester.role not in (UserRole.ADMIN, UserRole.OFFICER):
            raise ForbiddenError("Insufficient permissions.")

        role_enum   = UserRole(role)   if role   else None
        status_enum = UserStatus(status) if status else None

        # Officers can only see their ward's citizens
        if requester.role == UserRole.OFFICER and requester.officer_profile:
            officer_wards = requester.officer_profile.ward_ids or []
            if ward_id and ward_id not in officer_wards:
                raise ForbiddenError("Ward not in your assignment.")
            role_enum = UserRole.CITIZEN

        users, total = await self._users.list_users(
            role=role_enum,
            status=status_enum,
            ward_id=ward_id,
            search=search,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        pages = math.ceil(total / page_size) if page_size else 1
        return users, total, pages

    # ── Reputation scoring ────────────────────────────────────────────────────

    async def recalculate_reputation(self, user_id: str) -> float:
        """
        Reputation formula (0–100):
          base     = min(total_complaints × 2, 40)   [activity component]
          accuracy = (resolved / total) × 40          [quality component]
          bonus    = citizen_rating_avg × 4           [satisfaction bonus]
          penalty  = duplicate_count × -2             [accuracy penalty]
        """
        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)

        total    = user.total_complaints
        resolved = user.resolved_complaints

        if total == 0:
            await self._users.update_reputation(user_id, 0.0)
            return 0.0

        # Count duplicates submitted by this user
        dup_q = select(func.count()).where(
            Complaint.citizen_id == user_id,
            Complaint.is_duplicate.is_(True),
        )
        dup_count = (await self._db.execute(dup_q)).scalar() or 0

        # Average citizen rating received on their complaints
        rating_q = select(func.avg(Complaint.citizen_rating)).where(
            Complaint.citizen_id == user_id,
            Complaint.citizen_rating.is_not(None),
        )
        avg_rating = float((await self._db.execute(rating_q)).scalar() or 0.0)

        base     = min(total * 2, 40)
        accuracy = (resolved / total) * 40
        bonus    = avg_rating * 4
        penalty  = dup_count * 2

        score = max(0.0, min(100.0, base + accuracy + bonus - penalty))

        await self._users.update_reputation(user_id, score)
        logger.debug("Reputation recalculated", extra={"user_id": user_id, "score": score})
        return score

    # ── Activity summary ──────────────────────────────────────────────────────

    async def get_activity_summary(self, user_id: str) -> dict:
        """
        Return a compact stats dict for the profile screen.
        """
        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)

        # Recent complaints
        recent_q = (
            select(Complaint)
            .where(Complaint.citizen_id == user_id)
            .order_by(Complaint.created_at.desc())
            .limit(5)
        )
        recent = (await self._db.execute(recent_q)).scalars().all()

        # Open complaint count
        open_q = select(func.count()).where(
            Complaint.citizen_id == user_id,
            Complaint.status.in_([
                ComplaintStatus.SUBMITTED, ComplaintStatus.AI_PROCESSING,
                ComplaintStatus.PENDING_REVIEW, ComplaintStatus.ASSIGNED,
                ComplaintStatus.IN_PROGRESS,
            ]),
        )
        open_count = (await self._db.execute(open_q)).scalar() or 0

        # Resolution rate
        total    = user.total_complaints
        resolved = user.resolved_complaints
        rate     = round((resolved / total) * 100, 1) if total else 0.0

        return {
            "total_complaints":    total,
            "resolved_complaints": resolved,
            "open_complaints":     open_count,
            "resolution_rate":     rate,
            "reputation_score":    float(user.reputation_score),
            "recent_complaints":   [
                {
                    "id":      c.id,
                    "number":  c.complaint_number,
                    "title":   c.title,
                    "status":  c.status,
                    "created": c.created_at.isoformat(),
                }
                for c in recent
            ],
        }

    # ── Analytics (admin) ─────────────────────────────────────────────────────

    async def get_user_analytics(self, admin: User) -> dict:
        """High-level user analytics for the admin dashboard."""
        self._require_admin(admin)

        counts = await self._users.count_by_role()
        active  = await self._users.count_active()
        top     = await self._users.top_reporters(limit=5)

        return {
            "by_role":   {k: v for k, v in counts.items()},
            "active":    active,
            "top_reporters": [
                {
                    "id":    u.id,
                    "name":  u.full_name,
                    "total": u.total_complaints,
                    "score": float(u.reputation_score),
                }
                for u in top
            ],
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _require_admin(user: User) -> None:
        if user.role != UserRole.ADMIN:
            raise ForbiddenError("Admin access required.")
