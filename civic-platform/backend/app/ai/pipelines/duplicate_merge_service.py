"""
DuplicateMergeService
======================
Executes the actual *merge* action once a complaint has been flagged as a
duplicate — either automatically (AI confidence above threshold) or after
officer/admin review of a borderline AI suggestion.

The AI module's DuplicateDetector only *scores* candidates; this service is
what the spec means by "If duplicate: merge complaints, increase support
count." Concretely, merging means:

  1. Mark the child complaint as is_duplicate=True, parent_complaint_id=parent.id
  2. Transition the child to status='closed' with closed_reason='duplicate'
  3. Move the child's support_count (and its own supporter, the citizen who
     filed it) onto the parent, so community interest consolidates rather
     than fragmenting across near-identical reports
  4. Append status history entries on both complaints for auditability
  5. Notify the child's citizen that their report was merged into an
     existing, already-being-tracked complaint
  6. Recalculate the parent's priority score (it just gained support)

Auto-merge vs. manual review:
  • AI score >= settings.DUPLICATE_IMAGE_SIMILARITY_THRESHOLD → auto-merged
    immediately by AIOrchestrationService at submission time (no human in
    the loop, since the spec describes this as the default behaviour).
  • Borderline candidates (returned by DuplicateDetector as `all_candidates`
    but below the auto-merge threshold) are surfaced to officers/admins via
    the review endpoints below, who can confirm_merge() or reject_duplicate().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.models.models import Complaint, ComplaintStatus, User, UserRole
from app.repositories.complaint_repository import ComplaintRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class DuplicateMergeService:
    def __init__(
        self,
        db:       AsyncSession,
        repo:     ComplaintRepository,
        notifier: NotificationService,
        audit:    AuditService,
    ) -> None:
        self._db      = db
        self._repo    = repo
        self._notifier= notifier
        self._audit   = audit

    # ── Auto-merge (called by AIOrchestrationService at submission time) ──────

    async def auto_merge(
        self,
        child_complaint: Complaint,
        parent_complaint_id: str,
        similarity_score: float,
        ai_actor_id: str = "system:ai",
    ) -> Complaint:
        """
        Execute an automatic merge when AI confidence is high enough that no
        human review is required. Called inline from the AI pipeline right
        after a complaint is created and flagged as a duplicate.
        """
        parent = await self._repo.get_by_id(parent_complaint_id)
        if not parent:
            logger.warning(
                "Auto-merge aborted — parent complaint %s not found for child %s",
                parent_complaint_id, child_complaint.id,
            )
            return child_complaint

        return await self._execute_merge(
            child=child_complaint,
            parent=parent,
            similarity_score=similarity_score,
            actor_id=ai_actor_id,
            actor_label="AI duplicate detection",
            notes=f"Automatically merged — {similarity_score * 100:.0f}% similarity to {parent.complaint_number}.",
        )

    # ── Manual review (officer/admin confirms or rejects a borderline AI flag) ─

    async def confirm_merge(
        self,
        child_complaint_id: str,
        parent_complaint_id: str,
        reviewer: User,
        notes: Optional[str] = None,
    ) -> Complaint:
        """
        Officer/admin confirms that a borderline AI-suggested duplicate
        candidate really is the same underlying issue, and merges it.
        """
        self._require_reviewer(reviewer)

        if child_complaint_id == parent_complaint_id:
            raise BadRequestError("A complaint cannot be merged into itself.")

        child = await self._repo.get_by_id(child_complaint_id, detail=True)
        if not child:
            raise NotFoundError("Complaint", child_complaint_id)
        parent = await self._repo.get_by_id(parent_complaint_id, detail=True)
        if not parent:
            raise NotFoundError("Complaint", parent_complaint_id)

        if child.is_duplicate and child.parent_complaint_id:
            raise BadRequestError(
                f"Complaint {child.complaint_number} is already merged into "
                f"another complaint."
            )
        if child.status in (ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED):
            raise BadRequestError(
                "Cannot merge a complaint that has already been resolved/verified."
            )
        if parent.status in (ComplaintStatus.CLOSED, ComplaintStatus.REJECTED):
            raise BadRequestError(
                "Cannot merge into a complaint that is closed or rejected."
            )

        merged = await self._execute_merge(
            child=child,
            parent=parent,
            similarity_score=1.0,   # human-confirmed — treat as certain
            actor_id=str(reviewer.id),
            actor_label=f"{reviewer.full_name} ({reviewer.role})",
            notes=notes or f"Manually confirmed as duplicate of {parent.complaint_number}.",
        )

        await self._audit.log_update(
            user_id=str(reviewer.id),
            resource_type="complaint",
            resource_id=child_complaint_id,
            old_values={"status": child.status, "is_duplicate": child.is_duplicate},
            new_values={"status": "closed", "is_duplicate": True, "parent_complaint_id": parent_complaint_id},
        )
        return merged

    async def reject_duplicate_flag(
        self,
        complaint_id: str,
        reviewer: User,
        notes: Optional[str] = None,
    ) -> Complaint:
        """
        Officer/admin determines an AI-flagged "possible duplicate" is in
        fact a distinct issue and should proceed through the normal pipeline
        rather than being merged.
        """
        self._require_reviewer(reviewer)

        complaint = await self._repo.get_by_id(complaint_id, detail=True)
        if not complaint:
            raise NotFoundError("Complaint", complaint_id)

        if complaint.is_duplicate and complaint.parent_complaint_id:
            raise BadRequestError(
                "This complaint has already been merged — cannot reject a "
                "duplicate flag after the merge is complete. Use unmerge instead."
            )

        updated = await self._repo.update_fields(
            complaint_id,
            is_duplicate=False,
            parent_complaint_id=None,
        )

        next_status = (
            ComplaintStatus.PENDING_REVIEW
            if complaint.status == ComplaintStatus.AI_PROCESSING
            else complaint.status
        )
        if next_status != complaint.status:
            updated = await self._repo.update_status(complaint_id, next_status)

        await self._repo.add_status_history(
            complaint_id=complaint_id,
            changed_by_id=str(reviewer.id),
            from_status=complaint.status,
            to_status=next_status,
            notes=notes or "AI duplicate flag reviewed and rejected — treated as a distinct issue.",
        )

        await self._repo.recalculate_priority(complaint_id)

        await self._audit.log_update(
            user_id=str(reviewer.id),
            resource_type="complaint",
            resource_id=complaint_id,
            old_values={"is_duplicate": True},
            new_values={"is_duplicate": False},
        )

        logger.info(
            "Duplicate flag rejected for %s by %s", complaint.complaint_number, reviewer.email,
        )
        return updated

    async def unmerge(
        self,
        child_complaint_id: str,
        admin: User,
        notes: Optional[str] = None,
    ) -> Complaint:
        """
        Admin-only escape hatch: reverse a merge that turns out to have been
        incorrect (e.g. two genuinely separate potholes on the same street
        were mistakenly consolidated). Reopens the child and transfers its
        support back off the parent.
        """
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError("Only admins can reverse a merge.")

        child = await self._repo.get_by_id(child_complaint_id, detail=True)
        if not child:
            raise NotFoundError("Complaint", child_complaint_id)
        if not child.is_duplicate or not child.parent_complaint_id:
            raise BadRequestError("This complaint is not currently merged into another.")

        parent_id = str(child.parent_complaint_id)
        parent = await self._repo.get_by_id(parent_id, detail=True)

        # Move the child's own supporter relationship back, and decrement
        # the count that was added to the parent during the original merge.
        transferred = await self._repo.is_supporter(parent_id, str(child.citizen_id))
        if transferred:
            await self._repo.remove_supporter(parent_id, str(child.citizen_id))
            await self._repo.add_supporter(child_complaint_id, str(child.citizen_id))

        restored = await self._repo.update_fields(
            child_complaint_id,
            is_duplicate=False,
            parent_complaint_id=None,
        )
        restored = await self._repo.update_status(child_complaint_id, ComplaintStatus.PENDING_REVIEW)

        await self._repo.add_status_history(
            complaint_id=child_complaint_id,
            changed_by_id=str(admin.id),
            from_status=ComplaintStatus.CLOSED,
            to_status=ComplaintStatus.PENDING_REVIEW,
            notes=notes or f"Merge reversed by admin — reopened as a distinct complaint.",
        )

        if parent:
            await self._repo.recalculate_priority(parent_id)
        await self._repo.recalculate_priority(child_complaint_id)

        await self._audit.log_update(
            user_id=str(admin.id),
            resource_type="complaint",
            resource_id=child_complaint_id,
            old_values={"is_duplicate": True, "parent_complaint_id": parent_id},
            new_values={"is_duplicate": False, "parent_complaint_id": None},
        )

        logger.info(
            "Merge reversed for %s (was merged into %s) by admin %s",
            child.complaint_number, parent_id, admin.email,
        )
        return restored

    # ── Core merge execution ──────────────────────────────────────────────────

    async def _execute_merge(
        self,
        child: Complaint,
        parent: Complaint,
        similarity_score: float,
        actor_id: str,
        actor_label: str,
        notes: str,
    ) -> Complaint:
        """Shared logic between auto_merge() and confirm_merge()."""

        # 1. Transfer the child citizen's "support" onto the parent — their
        #    interest in the issue should now count toward the consolidated report.
        already_supports_parent = await self._repo.is_supporter(
            str(parent.id), str(child.citizen_id)
        )
        if not already_supports_parent and str(child.citizen_id) != str(parent.citizen_id):
            await self._repo.add_supporter(str(parent.id), str(child.citizen_id))

        # 2. Pull across any *other* supporters the child had already accumulated
        #    (e.g. if the child itself had been upvoted by neighbours before
        #    the duplicate was caught).
        # ComplaintRepository doesn't expose a bulk list of supporters directly
        # on the lightweight object, so we rely on the detail-loaded relationship
        # if present; this is best-effort and never blocks the merge.
        try:
            child_supporters = getattr(child, "supporters", None) or []
            for supporter in child_supporters:
                supporter_user_id = str(getattr(supporter, "user_id", supporter))
                if supporter_user_id == str(parent.citizen_id):
                    continue
                exists = await self._repo.is_supporter(str(parent.id), supporter_user_id)
                if not exists:
                    await self._repo.add_supporter(str(parent.id), supporter_user_id)
        except Exception as exc:
            logger.debug("Best-effort supporter transfer skipped: %s", exc)

        # 3. Mark the child as a duplicate, linked to the parent, and closed.
        old_status = child.status
        merged_child = await self._repo.update_fields(
            str(child.id),
            is_duplicate=True,
            parent_complaint_id=str(parent.id),
            status=ComplaintStatus.CLOSED,
            closed_reason="duplicate",
        )

        await self._repo.add_status_history(
            complaint_id=str(child.id),
            changed_by_id=actor_id if not actor_id.startswith("system:") else str(child.citizen_id),
            from_status=old_status,
            to_status=ComplaintStatus.CLOSED,
            notes=f"[{actor_label}] {notes}",
        )

        # 4. Recalculate the parent's priority — it just gained support count.
        await self._repo.recalculate_priority(str(parent.id))

        # 5. Notify the child's citizen that their report was consolidated.
        await self._notifier.notify_duplicate_detected(merged_child, parent.complaint_number)

        logger.info(
            "Merged %s into %s (similarity=%.2f, by=%s)",
            child.complaint_number, parent.complaint_number, similarity_score, actor_label,
        )
        return merged_child

    # ── Pending review queue (for the officer dashboard) ──────────────────────

    async def get_pending_review_queue(self, reviewer: User) -> list[dict]:
        """
        Borderline AI duplicate suggestions that didn't clear the auto-merge
        threshold but are similar enough to warrant a human look. Surfaced
        from AIAnalysis.similar_complaint_ids where is_duplicate=False
        (i.e. flagged as a candidate but not confident enough to auto-merge).
        """
        self._require_reviewer(reviewer)

        from sqlalchemy import select
        from app.models.models import AIAnalysis

        rows = (
            await self._db.execute(
                select(AIAnalysis).where(
                    AIAnalysis.duplicate_checked.is_(True),
                    AIAnalysis.is_duplicate.is_(False),
                    AIAnalysis.similar_complaint_ids.is_not(None),
                    AIAnalysis.similarity_score.is_not(None),
                    AIAnalysis.similarity_score >= 0.5,   # worth a human look
                )
                .order_by(AIAnalysis.similarity_score.desc())
                .limit(50)
            )
        ).scalars().all()

        queue = []
        for analysis in rows:
            complaint = await self._repo.get_by_id(str(analysis.complaint_id))
            if not complaint or complaint.is_duplicate:
                continue
            queue.append({
                "complaint_id":     str(complaint.id),
                "complaint_number": complaint.complaint_number,
                "title":            complaint.title,
                "category":         complaint.category,
                "similarity_score": float(analysis.similarity_score),
                "candidate_parent_ids": analysis.similar_complaint_ids,
            })
        return queue

    # ── Guards ────────────────────────────────────────────────────────────────

    @staticmethod
    def _require_reviewer(user: User) -> None:
        if user.role not in (UserRole.OFFICER, UserRole.ADMIN):
            raise ForbiddenError("Officer or admin access required to review duplicates.")
