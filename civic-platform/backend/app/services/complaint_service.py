"""
ComplaintService
================
All business logic for the complaint lifecycle.

Coordinates:
  ComplaintRepository  — DB reads/writes
  StorageService       — S3 image upload
  NotificationService  — push + in-app
  AuditService         — audit trail
  UserRepository       — citizen stat updates
  OfficerRepository    — workload tracking

Status machine:
  submitted → ai_processing → pending_review → assigned
            → in_progress → resolved → verified
            ↘ closed (admin) / rejected (admin)
"""

from __future__ import annotations

import csv
import io
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

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
    Category,
    Complaint,
    ComplaintImage,
    ComplaintStatus,
    IssueCategory,
    Officer,
    SeverityLevel,
    User,
    UserRole,
)
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


# ─── Allowed status transitions ───────────────────────────────────────────────

_CITIZEN_TRANSITIONS: dict[ComplaintStatus, set[ComplaintStatus]] = {
    ComplaintStatus.RESOLVED: {ComplaintStatus.VERIFIED},
}

_OFFICER_TRANSITIONS: dict[ComplaintStatus, set[ComplaintStatus]] = {
    ComplaintStatus.ASSIGNED:       {ComplaintStatus.IN_PROGRESS},
    ComplaintStatus.IN_PROGRESS:    {ComplaintStatus.RESOLVED},
    ComplaintStatus.PENDING_REVIEW: {ComplaintStatus.ASSIGNED, ComplaintStatus.REJECTED},
}

_ADMIN_TRANSITIONS: dict[ComplaintStatus, set[ComplaintStatus]] = {
    ComplaintStatus.SUBMITTED:      {ComplaintStatus.PENDING_REVIEW, ComplaintStatus.CLOSED},
    ComplaintStatus.AI_PROCESSING:  {ComplaintStatus.PENDING_REVIEW},
    ComplaintStatus.PENDING_REVIEW: {ComplaintStatus.ASSIGNED, ComplaintStatus.REJECTED, ComplaintStatus.CLOSED},
    ComplaintStatus.ASSIGNED:       {ComplaintStatus.IN_PROGRESS, ComplaintStatus.REJECTED, ComplaintStatus.CLOSED},
    ComplaintStatus.IN_PROGRESS:    {ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED, ComplaintStatus.CLOSED},
    ComplaintStatus.RESOLVED:       {ComplaintStatus.VERIFIED, ComplaintStatus.CLOSED},
}

_ALL_TRANSITIONS: dict[ComplaintStatus, set[ComplaintStatus]] = {}
for _d in (_CITIZEN_TRANSITIONS, _OFFICER_TRANSITIONS, _ADMIN_TRANSITIONS):
    for _k, _v in _d.items():
        _ALL_TRANSITIONS.setdefault(_k, set()).update(_v)


class ComplaintService:
    def __init__(
        self,
        db:         AsyncSession,
        repo:       ComplaintRepository,
        user_repo:  UserRepository,
        storage:    StorageService,
        notifier:   NotificationService,
        audit:      AuditService,
    ) -> None:
        self._db      = db
        self._repo    = repo
        self._users   = user_repo
        self._storage = storage
        self._notifier= notifier
        self._audit   = audit

    # ── Submit ────────────────────────────────────────────────────────────────

    async def submit_complaint(
        self,
        citizen: User,
        title: str,
        description: str,
        category: IssueCategory,
        severity: SeverityLevel,
        latitude: float,
        longitude: float,
        address: Optional[str] = None,
        ward_id: Optional[int] = None,
        landmark: Optional[str] = None,
        tags: Optional[list[str]] = None,
        client_ip: Optional[str] = None,
    ) -> Complaint:
        """
        Create and persist a new complaint.
        Immediately transitions to ai_processing when the AI pipeline is available.
        """
        # Validate category is active
        cat = await self._repo.get_category_by_name(category)
        if not cat or not cat.is_active:
            raise BadRequestError(f"Issue category '{category}' is not available.")

        # Compute SLA deadline (severity shortens it)
        sla_hours = self._sla_hours(cat, severity)
        sla_deadline = datetime.now(timezone.utc) + timedelta(hours=sla_hours)

        # Complaint number
        complaint_number = await self._repo.next_complaint_number()

        complaint = await self._repo.create(
            complaint_number=complaint_number,
            citizen_id=str(citizen.id),
            category_id=cat.id,
            status=ComplaintStatus.SUBMITTED,
            severity=severity,
            latitude=latitude,
            longitude=longitude,
            address=address,
            ward_id=ward_id,
            landmark=landmark,
            title=title,
            description=description,
            tags=tags,
            sla_deadline=sla_deadline,
        )

        # Status history — initial entry
        await self._repo.add_status_history(
            complaint_id=str(complaint.id),
            changed_by_id=str(citizen.id),
            from_status=None,
            to_status=ComplaintStatus.SUBMITTED,
            notes="Complaint submitted by citizen.",
        )

        # Update citizen stats
        await self._users.increment_complaint_counts(str(citizen.id))

        # Audit
        await self._audit.log_create(
            user_id=str(citizen.id),
            resource_type="complaint",
            resource_id=str(complaint.id),
            new_values={"number": complaint_number, "category": category, "severity": severity},
            ip=client_ip,
        )

        # Push notification
        await self._notifier.notify_complaint_submitted(complaint, citizen)

        # Calculate initial priority score
        await self._repo.recalculate_priority(str(complaint.id))

        logger.info(
            "Complaint submitted",
            extra={"id": str(complaint.id), "number": complaint_number, "citizen": str(citizen.id)},
        )
        return complaint

    # ── Get / list ────────────────────────────────────────────────────────────

    async def get_complaint(self, complaint_id: str, requester: User) -> Complaint:
        complaint = await self._repo.get_by_id(complaint_id, detail=True)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)
        self._assert_can_view(complaint, requester)
        return complaint

    async def list_complaints(
        self,
        requester: User,
        *,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        ward_id: Optional[int] = None,
        officer_id: Optional[str] = None,
        citizen_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        is_duplicate: Optional[bool] = None,
        sla_breached: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[Sequence[Complaint], int, int]:
        """Returns (complaints, total, pages)."""

        # Scope constraints
        if requester.role == UserRole.CITIZEN:
            citizen_id = str(requester.id)   # citizens only see their own

        elif requester.role == UserRole.OFFICER:
            if officer_id and officer_id != str(requester.officer_profile.id if requester.officer_profile else ""):
                raise ForbiddenError("Cannot view another officer's complaints.")
            if not officer_id:
                officer_id = str(requester.officer_profile.id) if requester.officer_profile else None

        rows, total = await self._repo.list_complaints(
            status=ComplaintStatus(status) if status else None,
            severity=SeverityLevel(severity) if severity else None,
            category=IssueCategory(category) if category else None,
            ward_id=ward_id,
            officer_id=officer_id,
            citizen_id=citizen_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
            is_duplicate=is_duplicate,
            sla_breached=sla_breached,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        pages = math.ceil(total / page_size) if page_size else 1
        return rows, total, pages

    async def get_nearby(
        self,
        lat: float,
        lng: float,
        radius_km: float = 5.0,
        requester: Optional[User] = None,
    ) -> Sequence[Complaint]:
        return await self._repo.find_nearby(lat, lng, radius_km)

    # ── Update (citizen) ──────────────────────────────────────────────────────

    async def update_complaint(
        self,
        complaint_id: str,
        requester: User,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        severity: Optional[SeverityLevel] = None,
        address: Optional[str] = None,
        ward_id: Optional[int] = None,
        landmark: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Complaint:
        complaint = await self._repo.get_by_id(complaint_id, detail=True)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        # Only the citizen or admin can update
        if (
            str(complaint.citizen_id) != str(requester.id)
            and requester.role != UserRole.ADMIN
        ):
            raise ForbiddenError("You can only edit your own complaints.")

        # Cannot edit a closed/rejected complaint
        if complaint.status in (
            ComplaintStatus.CLOSED,
            ComplaintStatus.REJECTED,
            ComplaintStatus.VERIFIED,
        ):
            raise BadRequestError(f"Cannot edit a complaint in '{complaint.status}' status.")

        updates: dict = {}
        if title is not None:
            updates["title"] = title.strip()
        if description is not None:
            updates["description"] = description.strip()
        if severity is not None:
            updates["severity"] = severity
        if address is not None:
            updates["address"] = address
        if ward_id is not None:
            updates["ward_id"] = ward_id
        if landmark is not None:
            updates["landmark"] = landmark
        if tags is not None:
            updates["tags"] = tags

        if not updates:
            return complaint

        updated = await self._repo.update_fields(complaint_id, **updates)

        if "severity" in updates:
            await self._repo.recalculate_priority(complaint_id)

        await self._audit.log_update(
            user_id=str(requester.id),
            resource_type="complaint",
            resource_id=complaint_id,
            old_values={k: getattr(complaint, k) for k in updates},
            new_values=updates,
        )
        return updated

    # ── Status transitions ────────────────────────────────────────────────────

    async def update_status(
        self,
        complaint_id: str,
        new_status: ComplaintStatus,
        requester: User,
        notes: Optional[str] = None,
        officer_id: Optional[str] = None,
    ) -> Complaint:
        """
        Transition complaint status.
        Validates the transition is allowed for the requester's role.
        """
        complaint = await self._repo.get_by_id(complaint_id, detail=True)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        old_status = complaint.status
        self._assert_transition_allowed(old_status, new_status, requester)

        extra: dict = {}
        if new_status == ComplaintStatus.RESOLVED:
            extra["resolved_at"] = datetime.now(timezone.utc)
            if notes:
                extra["resolution_notes"] = notes

        if officer_id and requester.role == UserRole.ADMIN:
            extra["officer_id"] = officer_id

        updated = await self._repo.update_status(complaint_id, new_status, **extra)

        # History
        await self._repo.add_status_history(
            complaint_id=complaint_id,
            changed_by_id=str(requester.id),
            from_status=old_status,
            to_status=new_status,
            notes=notes,
            officer_id=officer_id or (str(complaint.officer_id) if complaint.officer_id else None),
        )

        # Notifications
        await self._notifier.notify_status_changed(updated, old_status, new_status, notes)
        if new_status == ComplaintStatus.RESOLVED:
            await self._notifier.notify_resolved(updated)

        # If resolved, update citizen resolved count + recalculate reputation
        if new_status in (ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED):
            await self._users.increment_complaint_counts(str(complaint.citizen_id), resolved=True)

        await self._repo.recalculate_priority(complaint_id)

        await self._audit.log_update(
            user_id=str(requester.id),
            resource_type="complaint",
            resource_id=complaint_id,
            old_values={"status": old_status},
            new_values={"status": new_status, "notes": notes},
        )
        return updated

    # ── Officer assignment ────────────────────────────────────────────────────

    async def assign_officer(
        self,
        complaint_id: str,
        officer_id: str,
        admin: User,
    ) -> Complaint:
        self._require_admin_or_officer(admin)

        complaint = await self._repo.get_by_id(complaint_id, detail=True)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        if complaint.status in (ComplaintStatus.CLOSED, ComplaintStatus.REJECTED, ComplaintStatus.VERIFIED):
            raise BadRequestError("Cannot assign a closed or rejected complaint.")

        # Verify officer exists
        from sqlalchemy import select
        from app.models.models import Officer as OfficerModel

        officer_row = (
            await self._db.execute(
                select(OfficerModel)
                .where(OfficerModel.id == officer_id, OfficerModel.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not officer_row:
            raise NotFoundError("Officer", officer_id)

        # Workload check
        if officer_row.total_assigned >= officer_row.max_complaints:
            raise BadRequestError(
                f"Officer has reached their maximum workload "
                f"({officer_row.max_complaints} complaints)."
            )

        old_officer_id = str(complaint.officer_id) if complaint.officer_id else None
        updated = await self._repo.assign_officer(complaint_id, officer_id)

        await self._repo.add_status_history(
            complaint_id=complaint_id,
            changed_by_id=str(admin.id),
            from_status=complaint.status,
            to_status=ComplaintStatus.ASSIGNED,
            notes=f"Assigned to officer {officer_row.badge_number}",
            officer_id=officer_id,
        )

        # Update officer stats
        from sqlalchemy import update as sqla_update
        await self._db.execute(
            sqla_update(OfficerModel)
            .where(OfficerModel.id == officer_id)
            .values(total_assigned=OfficerModel.total_assigned + 1)
        )

        # Notify citizen
        officer_user = officer_row.user if hasattr(officer_row, "user") else None
        if officer_user:
            await self._notifier.notify_complaint_assigned(updated, officer_user)

        await self._audit.log_complaint_assigned(
            admin_id=str(admin.id),
            complaint_id=complaint_id,
            officer_id=officer_id,
        )
        return updated

    async def bulk_assign(
        self,
        complaint_ids: list[str],
        officer_id: str,
        admin: User,
    ) -> int:
        self._require_admin_or_officer(admin)

        count = await self._repo.bulk_assign(complaint_ids, officer_id)

        for cid in complaint_ids:
            await self._repo.add_status_history(
                complaint_id=cid,
                changed_by_id=str(admin.id),
                from_status=None,
                to_status=ComplaintStatus.ASSIGNED,
                notes=f"Bulk assigned by {admin.email}",
                officer_id=officer_id,
            )
        return count

    # ── Citizen verify resolution ─────────────────────────────────────────────

    async def verify_resolution(
        self,
        complaint_id: str,
        citizen: User,
        is_resolved: bool,
        feedback: Optional[str] = None,
        rating: Optional[int] = None,
    ) -> Complaint:
        complaint = await self._repo.get_by_id(complaint_id, detail=True)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        if str(complaint.citizen_id) != str(citizen.id):
            raise ForbiddenError("Only the reporting citizen can verify resolution.")

        if complaint.status != ComplaintStatus.RESOLVED:
            raise BadRequestError("Complaint is not in 'resolved' status.")

        if complaint.citizen_verified:
            raise BadRequestError("You have already verified this complaint.")

        if is_resolved:
            new_status = ComplaintStatus.VERIFIED
            updates = {
                "citizen_verified":    True,
                "citizen_verified_at": datetime.now(timezone.utc),
                "citizen_rating":      rating,
                "status":              ComplaintStatus.VERIFIED,
            }
        else:
            # Citizen says it's not fixed — reopen
            new_status = ComplaintStatus.IN_PROGRESS
            updates = {"status": ComplaintStatus.IN_PROGRESS}

        updated = await self._repo.update_fields(complaint_id, **updates)

        # Update resolution feedback
        if feedback or rating:
            res = await self._repo.get_resolution(complaint_id)
            if res:
                await self._repo.update_resolution(
                    complaint_id,
                    citizen_feedback=feedback,
                    citizen_rating=rating,
                    citizen_rated_at=datetime.now(timezone.utc),
                )

        await self._repo.add_status_history(
            complaint_id=complaint_id,
            changed_by_id=str(citizen.id),
            from_status=ComplaintStatus.RESOLVED,
            to_status=new_status,
            notes=f"Citizen {'verified' if is_resolved else 'disputed'} resolution. "
                  f"Rating: {rating}/5" if rating else "",
        )
        return updated

    # ── Image management ──────────────────────────────────────────────────────

    async def upload_image(
        self,
        complaint_id: str,
        requester: User,
        image_bytes: bytes,
        content_type: str,
        original_filename: str = "",
        is_resolution: bool = False,
        caption: Optional[str] = None,
    ) -> ComplaintImage:
        """Upload an image to S3 and attach it to the complaint."""
        complaint = await self._repo.get_by_id(complaint_id)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        self._assert_can_view(complaint, requester)

        if len(image_bytes) > settings.max_upload_bytes:
            raise BadRequestError(
                f"Image must be under {settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        # Max 5 images per complaint
        existing = await self._repo.get_images(complaint_id)
        if len(existing) >= 5:
            raise BadRequestError("Maximum 5 images per complaint.")

        result = await self._storage.upload_complaint_image(
            complaint_id=complaint_id,
            image_bytes=image_bytes,
            content_type=content_type,
            original_filename=original_filename,
            is_resolution=is_resolution,
        )

        is_primary = len(existing) == 0   # first image is primary

        img = await self._repo.add_image(
            complaint_id=complaint_id,
            uploader_id=str(requester.id),
            is_primary=is_primary,
            is_resolution=is_resolution,
            caption=caption,
            **result,
        )
        return img

    async def delete_image(
        self,
        complaint_id: str,
        image_id: str,
        requester: User,
    ) -> None:
        complaint = await self._repo.get_by_id(complaint_id)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)
        if (
            str(complaint.citizen_id) != str(requester.id)
            and requester.role != UserRole.ADMIN
        ):
            raise ForbiddenError("Cannot delete another user's image.")

        img = await self._repo.get_image_by_id(image_id)
        if not img or str(img.complaint_id) != complaint_id:
            raise NotFoundError("Image", image_id)

        await self._storage.delete_object(img.s3_key)
        if img.thumbnail_url:
            thumb_key = img.s3_key.replace(".jpg", "_thumb.jpg")
            await self._storage.delete_object(thumb_key)

        await self._repo.delete_image(image_id)

    # ── Support / upvote ──────────────────────────────────────────────────────

    async def toggle_support(
        self,
        complaint_id: str,
        user: User,
    ) -> dict:
        """Add or remove support. Returns {"supported": bool, "count": int}."""
        complaint = await self._repo.get_by_id(complaint_id)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        if str(complaint.citizen_id) == str(user.id):
            raise BadRequestError("You cannot support your own complaint.")

        already = await self._repo.is_supporter(complaint_id, str(user.id))
        if already:
            await self._repo.remove_supporter(complaint_id, str(user.id))
            supported = False
        else:
            await self._repo.add_supporter(complaint_id, str(user.id))
            supported = True

        # Refresh count
        refreshed = await self._repo.get_by_id(complaint_id)
        count = refreshed.support_count if refreshed else 0
        await self._repo.recalculate_priority(complaint_id)

        return {"supported": supported, "count": count}

    async def add_support(self, complaint_id: str, user: User) -> dict:
        """
        Explicit, idempotent-checked add — used by POST /support. Raises
        BadRequestError if the user is already supporting, rather than
        silently toggling it off (which is what calling toggle_support
        blindly from a POST endpoint would incorrectly do).
        """
        complaint = await self._repo.get_by_id(complaint_id)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)
        if str(complaint.citizen_id) == str(user.id):
            raise BadRequestError("You cannot support your own complaint.")
        if await self._repo.is_supporter(complaint_id, str(user.id)):
            raise BadRequestError("You are already supporting this complaint.")

        await self._repo.add_supporter(complaint_id, str(user.id))
        refreshed = await self._repo.get_by_id(complaint_id)
        await self._repo.recalculate_priority(complaint_id)
        return {"supported": True, "count": refreshed.support_count if refreshed else 0}

    async def remove_support(self, complaint_id: str, user: User) -> dict:
        """Explicit, idempotent-checked remove — used by DELETE /support."""
        complaint = await self._repo.get_by_id(complaint_id)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)
        if not await self._repo.is_supporter(complaint_id, str(user.id)):
            raise BadRequestError("You were not supporting this complaint.")

        await self._repo.remove_supporter(complaint_id, str(user.id))
        refreshed = await self._repo.get_by_id(complaint_id)
        await self._repo.recalculate_priority(complaint_id)
        return {"supported": False, "count": refreshed.support_count if refreshed else 0}

    # ── Soft delete ───────────────────────────────────────────────────────────

    async def delete_complaint(self, complaint_id: str, admin: User) -> None:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError("Admin access required.")

        complaint = await self._repo.get_by_id(complaint_id)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        await self._repo.soft_delete(complaint_id)
        await self._audit.log_delete(
            user_id=str(admin.id), resource_type="complaint", resource_id=complaint_id
        )

    # ── Resolution record ─────────────────────────────────────────────────────

    async def submit_resolution(
        self,
        complaint_id: str,
        officer: User,
        work_done: str,
        resolution_type: Optional[str] = None,
        materials_used: Optional[str] = None,
        contractor_name: Optional[str] = None,
        estimated_cost: Optional[float] = None,
        actual_cost: Optional[float] = None,
    ) -> Complaint:
        """Officer submits resolution details and marks complaint resolved."""
        complaint = await self._repo.get_by_id(complaint_id, detail=True)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        if officer.role not in (UserRole.OFFICER, UserRole.ADMIN):
            raise ForbiddenError("Officer or admin access required.")

        if complaint.status not in (ComplaintStatus.IN_PROGRESS, ComplaintStatus.ASSIGNED):
            raise BadRequestError(
                f"Complaint must be 'in_progress' or 'assigned' to submit resolution. "
                f"Current: {complaint.status}."
            )

        # Get officer profile
        officer_profile = None
        if hasattr(officer, "officer_profile") and officer.officer_profile:
            officer_profile = officer.officer_profile

        if not officer_profile:
            raise BadRequestError("User does not have an officer profile.")

        # Create or update resolution record
        existing_res = await self._repo.get_resolution(complaint_id)
        if existing_res:
            await self._repo.update_resolution(
                complaint_id,
                work_done=work_done,
                resolution_type=resolution_type,
                materials_used=materials_used,
                contractor_name=contractor_name,
                estimated_cost=estimated_cost,
                actual_cost=actual_cost,
                completed_at=datetime.now(timezone.utc),
            )
        else:
            await self._repo.create_resolution(
                complaint_id=complaint_id,
                officer_id=str(officer_profile.id),
                work_done=work_done,
                resolution_type=resolution_type,
                materials_used=materials_used,
                contractor_name=contractor_name,
                estimated_cost=estimated_cost,
                actual_cost=actual_cost,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )

        # Transition to resolved
        updated = await self.update_status(
            complaint_id=complaint_id,
            new_status=ComplaintStatus.RESOLVED,
            requester=officer,
            notes=work_done[:200] if work_done else None,
        )

        # Update officer resolved count
        from sqlalchemy import update as sqla_update
        from app.models.models import Officer as OfficerModel

        await self._db.execute(
            sqla_update(OfficerModel)
            .where(OfficerModel.id == str(officer_profile.id))
            .values(total_resolved=OfficerModel.total_resolved + 1)
        )

        return updated

    # ── CSV export ────────────────────────────────────────────────────────────

    async def export_csv(
        self,
        requester: User,
        filters: dict,
    ) -> io.StringIO:
        """Stream complaint data as CSV for admin/officer downloads."""
        self._require_admin_or_officer(requester)

        rows = await self._repo.export_rows(filters, limit=50_000)
        buf = io.StringIO()
        writer = csv.writer(buf)

        writer.writerow([
            "Complaint Number", "Title", "Category", "Severity", "Status",
            "Latitude", "Longitude", "Address", "Ward", "Citizen Email",
            "Officer Badge", "Support Count", "SLA Breached",
            "AI Confidence", "Submitted At", "Resolved At",
        ])

        for c in rows:
            officer_badge = ""
            if hasattr(c, "officer") and c.officer:
                officer_badge = c.officer.badge_number

            writer.writerow([
                c.complaint_number,
                c.title,
                c.category,
                c.severity,
                c.status,
                float(c.latitude),
                float(c.longitude),
                c.address or "",
                c.ward_id or "",
                c.citizen.email if hasattr(c, "citizen") and c.citizen else "",
                officer_badge,
                c.support_count,
                c.sla_breached,
                float(c.ai_confidence) if c.ai_confidence else "",
                c.created_at.isoformat(),
                c.resolved_at.isoformat() if c.resolved_at else "",
            ])

        buf.seek(0)
        return buf

    # ── Analytics pass-through ────────────────────────────────────────────────

    async def get_dashboard_stats(self, requester: User) -> dict:
        """Aggregate KPIs for the admin dashboard."""
        self._require_admin_or_officer(requester)

        by_status     = await self._repo.count_by_status()
        total         = sum(by_status.values())
        open_statuses = {
            ComplaintStatus.SUBMITTED, ComplaintStatus.AI_PROCESSING,
            ComplaintStatus.PENDING_REVIEW, ComplaintStatus.ASSIGNED,
            ComplaintStatus.IN_PROGRESS,
        }
        open_count    = sum(v for k, v in by_status.items() if k in open_statuses)
        resolved_today= await self._repo.count_resolved_today()
        avg_days      = await self._repo.avg_resolution_days()

        return {
            "total_complaints":   total,
            "open_complaints":    open_count,
            "resolved_today":     resolved_today,
            "avg_resolution_days":avg_days,
            "by_status":          {k: v for k, v in by_status.items()},
        }

    async def get_category_analytics(self) -> list[dict]:
        return await self._repo.count_by_category()

    async def get_ward_summary(self) -> list[dict]:
        return await self._repo.count_by_ward()

    async def get_monthly_trend(self, months: int = 6) -> list[dict]:
        return await self._repo.monthly_trend(months)

    async def get_heatmap(self) -> list[dict]:
        return await self._repo.heatmap_points()

    async def get_severity_distribution(self) -> list[dict]:
        return await self._repo.severity_distribution()

    # ── SLA monitoring ────────────────────────────────────────────────────────

    async def check_sla_breaches(self) -> int:
        """
        Called periodically (e.g. by Celery beat every 15 min).
        Marks overdue complaints and notifies officers.
        Returns the number of newly breached complaints.
        """
        at_risk = await self._repo.get_sla_at_risk(hours_threshold=0)
        count = 0
        for c in at_risk:
            if not c.sla_breached:
                await self._repo.mark_sla_breached(str(c.id))
                await self._repo.update_fields(str(c.id), sla_breached=True)
                count += 1
                # Notify assigned officer
                if c.officer and hasattr(c.officer, "user"):
                    await self._notifier.notify_sla_breach(c, c.officer.user)
        return count

    # ── Guards ────────────────────────────────────────────────────────────────

    def _assert_can_view(self, complaint: Complaint, user: User) -> None:
        if user.role == UserRole.ADMIN:
            return
        if user.role == UserRole.OFFICER:
            return
        if str(complaint.citizen_id) == str(user.id):
            return
        raise ForbiddenError("You do not have access to this complaint.")

    def _assert_transition_allowed(
        self,
        current: ComplaintStatus,
        target: ComplaintStatus,
        user: User,
    ) -> None:
        if user.role == UserRole.ADMIN:
            allowed = _ADMIN_TRANSITIONS.get(current, set())
        elif user.role == UserRole.OFFICER:
            allowed = _OFFICER_TRANSITIONS.get(current, set()) | _ADMIN_TRANSITIONS.get(current, set())
        else:
            allowed = _CITIZEN_TRANSITIONS.get(current, set())

        if target not in allowed:
            raise BadRequestError(
                f"Cannot transition from '{current}' to '{target}' "
                f"with role '{user.role}'."
            )

    @staticmethod
    def _require_admin_or_officer(user: User) -> None:
        if user.role not in (UserRole.ADMIN, UserRole.OFFICER):
            raise ForbiddenError("Officer or admin access required.")

    @staticmethod
    def _sla_hours(category: Category, severity: SeverityLevel) -> int:
        base = category.sla_hours
        if severity == SeverityLevel.CRITICAL:
            return max(base // 2, 4)
        if severity == SeverityLevel.HIGH:
            return max(int(base * 0.75), 8)
        return base
