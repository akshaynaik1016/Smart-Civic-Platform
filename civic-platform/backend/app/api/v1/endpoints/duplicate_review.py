"""
Duplicate Review API
======================
GET    /duplicates/queue                          — borderline AI candidates needing human review
POST   /duplicates/{child_id}/confirm              — confirm merge into a specific parent
POST   /duplicates/{complaint_id}/reject           — reject AI's duplicate suggestion, keep distinct
POST   /duplicates/{child_id}/unmerge              — admin-only: reverse an incorrect merge
GET    /duplicates/{complaint_id}/candidates       — full scored candidate list for one complaint
"""

from __future__ import annotations

from typing import Annotated, Optional
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from app.api.v1.dependencies.auth import CurrentUser, DbDep, OfficerRequired
from app.core.exceptions import NotFoundError
from app.repositories.complaint_repository import ComplaintRepository
from app.schemas.schemas import MessageResponse
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/duplicates", tags=["Duplicate Review"])


# ── Request bodies ─────────────────────────────────────────────────────────────

class ConfirmMergeRequest(BaseModel):
    parent_complaint_id: str
    notes: Optional[str] = Field(None, max_length=500)

class ReviewActionRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=500)

# ── Dependency ──────────────────────────────────────────────────────────────────

async def _get_merge_service(db: DbDep):
    from app.ai.pipelines.duplicate_merge_service import DuplicateMergeService
    return DuplicateMergeService(
        db=db,
        repo=ComplaintRepository(db),
        notifier=NotificationService(db),
        audit=AuditService(db),
    )


MergeSvcDep = Annotated[object, Depends(_get_merge_service)]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/queue",
    summary="List borderline AI duplicate suggestions awaiting human review",
)
async def get_review_queue(
    officer: OfficerRequired,
    service: MergeSvcDep,
) -> dict:
    """
    Complaints the AI flagged as *possibly* duplicate but below the
    auto-merge confidence threshold. Sorted by similarity score, highest first.
    """
    queue = await service.get_pending_review_queue(officer)
    return {"items": queue, "total": len(queue)}


@router.get(
    "/{complaint_id}/candidates",
    summary="Get the full scored duplicate-candidate list for one complaint",
)
async def get_candidates(
    complaint_id: str,
    current_user: CurrentUser,
    db:           DbDep,
) -> dict:
    """
    Returns every nearby complaint the AI compared against, with individual
    distance / image-similarity / category-match scores — useful context
    when an officer is deciding whether to confirm a merge.
    """
    repo = ComplaintRepository(db)
    analysis = await repo.get_ai_analysis(complaint_id)
    if not analysis:
        raise NotFoundError("AI analysis", complaint_id)

    candidates = []
    for cid in (analysis.similar_complaint_ids or []):
        candidate = await repo.get_by_id(cid)
        if candidate:
            candidates.append({
                "complaint_id":     str(candidate.id),
                "complaint_number": candidate.complaint_number,
                "title":            candidate.title,
                "status":           candidate.status,
                "category":         candidate.category,
            })

    return {
        "complaint_id":      complaint_id,
        "is_duplicate":      analysis.is_duplicate,
        "overall_similarity": float(analysis.similarity_score) if analysis.similarity_score else None,
        "candidates":        candidates,
    }


@router.post(
    "/{child_id}/confirm",
    response_model=MessageResponse,
    summary="Confirm a borderline duplicate and execute the merge",
)
async def confirm_merge(
    child_id: str,
    officer:  OfficerRequired,
    service:  MergeSvcDep,
    body:     ConfirmMergeRequest = Body(...),
) -> dict:
    """
    Merges `child_id` into the specified parent: transfers support count,
    closes the child with reason='duplicate', and notifies the child's
    citizen that their report has been consolidated into an existing,
    already-tracked complaint.
    """
    merged = await service.confirm_merge(
        child_complaint_id=child_id,
        parent_complaint_id=body.parent_complaint_id,
        reviewer=officer,
        notes=body.notes,
    )
    return {
        "message": (
            f"Complaint {merged.complaint_number} merged successfully into "
            f"the parent report."
        )
    }


@router.post(
    "/{complaint_id}/reject",
    response_model=MessageResponse,
    summary="Reject an AI duplicate suggestion — keep as a distinct complaint",
)
async def reject_duplicate(
    complaint_id: str,
    officer:      OfficerRequired,
    service:      MergeSvcDep,
    body:         ReviewActionRequest = Body(default=ReviewActionRequest()),
) -> dict:
    """
    Officer determines the AI's duplicate suggestion was a false positive.
    The complaint proceeds through the normal pipeline (pending_review →
    assigned → ...) as its own distinct issue.
    """
    updated = await service.reject_duplicate_flag(
        complaint_id=complaint_id, reviewer=officer, notes=body.notes,
    )
    return {
        "message": f"Duplicate flag rejected for {updated.complaint_number} — will be processed independently."
    }


@router.post(
    "/{child_id}/unmerge",
    response_model=MessageResponse,
    summary="Admin-only: reverse an incorrect merge",
)
async def unmerge_complaint(
    child_id: str,
    admin:    OfficerRequired,   # role check inside service narrows further to ADMIN
    service:  MergeSvcDep,
    body:     ReviewActionRequest = Body(default=ReviewActionRequest()),
) -> dict:
    """
    Reverses a merge that turns out to have consolidated two genuinely
    distinct issues. Transfers support back off the parent and reopens
    the child as pending_review.
    """
    restored = await service.unmerge(
        child_complaint_id=child_id, admin=admin, notes=body.notes,
    )
    return {
        "message": f"Merge reversed — {restored.complaint_number} reopened as a distinct complaint."
    }
