"""
Complaint endpoints — wired against ComplaintService
=======================================================
POST   /complaints                   — submit new complaint
GET    /complaints                   — list (paginated, filtered)
GET    /complaints/nearby            — geo radius query
GET    /complaints/export/csv        — CSV export (admin/officer)
GET    /complaints/{id}              — get detail
PATCH  /complaints/{id}              — update complaint (citizen)
PATCH  /complaints/{id}/status       — update status (officer/admin)
PATCH  /complaints/{id}/assign       — assign officer (admin)
POST   /complaints/bulk-assign       — bulk assign (admin)
POST   /complaints/{id}/images       — upload image(s)
DELETE /complaints/{id}/images/{img} — delete an image
POST   /complaints/{id}/support      — support/upvote
DELETE /complaints/{id}/support      — remove support
POST   /complaints/{id}/verify       — citizen verifies resolution

This file previously implemented every operation directly against raw
SQLAlchemy queries, entirely bypassing ComplaintService — which meant the
duplicate-merge workflow, SLA-aware priority recalculation, audit logging,
push/email notifications, and S3-aware image upload built into that service
were never actually reachable through the API. It also referenced two
modules that don't exist (`app.workers.tasks.process_complaint_ai`,
`app.services.ai_service.AIService`) and the retired `cache/` package.
Rewritten to delegate to ComplaintService throughout.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Optional
from fastapi import Request
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.v1.dependencies.auth import (
    AdminRequired, CurrentUser, DbDep, OfficerRequired,
)
from app.core.exceptions import BadRequestError
from app.models.models import ComplaintStatus, IssueCategory, SeverityLevel
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.user_repository import UserRepository
from app.schemas.schemas import (
    AssignOfficerRequest,
    BulkAssignRequest,
    ComplaintCreateRequest,
    ComplaintListOut,
    ComplaintOut,
    ComplaintUpdateRequest,
    MessageResponse,
    PaginatedResponse,
    StatusUpdateRequest,
    VerifyResolutionRequest,
)
from app.schemas.complaint import ComplaintOut
from app.services.audit_service import AuditService
from app.services.complaint_service import ComplaintService
from app.services.notification_service import NotificationService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/complaints", tags=["Complaints"])


async def _get_service(db: DbDep) -> ComplaintService:
    return ComplaintService(
        db=db,
        repo=ComplaintRepository(db),
        user_repo=UserRepository(db),
        storage=StorageService(),
        notifier=NotificationService(db),
        audit=AuditService(db),
    )


ServiceDep = Annotated[ComplaintService, Depends(_get_service)]


# ─── Submit complaint ─────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ComplaintOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new civic complaint",
)


async def create_complaint(
    request: Request,
    payload: ComplaintCreateRequest,
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
) -> ComplaintOut:
    complaint = await service.submit_complaint(
    citizen=current_user,
    title=payload.title,
    description=payload.description,
    category=payload.category,
    severity=payload.severity,
    latitude=payload.latitude,
    longitude=payload.longitude,
    address=payload.address,
    ward_id=payload.ward_id,
    landmark=payload.landmark,
    tags=payload.tags,
    client_ip=request.client.host,
)
    await db.commit()
    detailed = await service.get_complaint(str(complaint.id), current_user)
    return ComplaintOut.model_validate(detailed)


# ─── List complaints ──────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedResponse[ComplaintListOut],
    summary="List complaints with filtering, search and pagination",
)
async def list_complaints(
    current_user: CurrentUser,
    service: ServiceDep,
    status: Optional[ComplaintStatus] = Query(None),
    severity: Optional[SeverityLevel] = Query(None),
    category: Optional[IssueCategory] = Query(None),
    ward_id: Optional[int] = Query(None),
    officer_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    is_duplicate: Optional[bool] = Query(None),
    sla_breached: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedResponse[ComplaintListOut]:
    complaints, total, pages = await service.list_complaints(
        current_user,
        status=status.value if status else None,
        severity=severity.value if severity else None,
        category=category.value if category else None,
        ward_id=ward_id, officer_id=officer_id,
        date_from=date_from, date_to=date_to, search=search,
        is_duplicate=is_duplicate, sla_breached=sla_breached,
        page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order,
    )
    return PaginatedResponse(
        items=[ComplaintListOut.model_validate(c) for c in complaints],
        total=total, page=page, page_size=page_size, pages=pages,
    )


# ─── Nearby (must come before /{complaint_id} to avoid route collision) ───────

@router.get("/nearby", response_model=list[ComplaintListOut], summary="Find complaints near a location")
async def get_nearby_complaints(
    current_user: CurrentUser,
    service: ServiceDep,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=5.0, ge=0.1, le=50),
) -> list[ComplaintListOut]:
    complaints = await service.get_nearby(lat, lng, radius_km, requester=current_user)
    return [ComplaintListOut.model_validate(c) for c in complaints]


# ─── CSV Export (must also come before /{complaint_id}) ───────────────────────

@router.get(
    "/export/csv",
    response_class=StreamingResponse,
    summary="Export complaints as CSV (admin/officer)",
)
async def export_complaints_csv(
    officer: OfficerRequired,
    service: ServiceDep,
    status: Optional[ComplaintStatus] = Query(None),
    severity: Optional[SeverityLevel] = Query(None),
    category: Optional[IssueCategory] = Query(None),
    ward_id: Optional[int] = Query(None),
) -> StreamingResponse:
    filters = {
        "status": status.value if status else None,
        "severity": severity.value if severity else None,
        "category": category.value if category else None,
        "ward_id": ward_id,
    }
    filters = {k: v for k, v in filters.items() if v is not None}
    csv_buffer = await service.export_csv(officer, filters)
    return StreamingResponse(
        iter([csv_buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=complaints.csv"},
    )


# ─── Bulk assign (also before /{complaint_id} for the same reason) ────────────

@router.post(
    "/bulk-assign",
    response_model=MessageResponse,
    summary="Bulk assign multiple complaints to one officer (admin only)",
)
async def bulk_assign(
    payload: BulkAssignRequest,
    admin: AdminRequired,
    service: ServiceDep,
    db: DbDep,
) -> MessageResponse:
    count = await service.bulk_assign(
        [str(cid) for cid in payload.complaint_ids], str(payload.officer_id), admin,
    )
    await db.commit()
    return MessageResponse(message=f"Assigned {count} complaint(s) to the officer.")


# ─── Get detail ───────────────────────────────────────────────────────────────

@router.get("/{complaint_id}", response_model=ComplaintOut, summary="Get full complaint details")
async def get_complaint(
    complaint_id: uuid.UUID, current_user: CurrentUser, service: ServiceDep,
) -> ComplaintOut:
    complaint = await service.get_complaint(str(complaint_id), current_user)
    return ComplaintOut.model_validate(complaint)


# ─── Update complaint ─────────────────────────────────────────────────────────

@router.patch("/{complaint_id}", response_model=ComplaintOut, summary="Update a complaint (citizen, before assigned)")
async def update_complaint(
    complaint_id: uuid.UUID,
    payload: ComplaintUpdateRequest,
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
) -> ComplaintOut:
    updated = await service.update_complaint(
        str(complaint_id), current_user,
        title=payload.title, description=payload.description, severity=payload.severity,
        address=payload.address, ward_id=payload.ward_id, landmark=payload.landmark,
        tags=payload.tags,
    )
    await db.commit()
    return ComplaintOut.model_validate(updated)


# ─── Update status ────────────────────────────────────────────────────────────

@router.patch(
    "/{complaint_id}/status",
    response_model=ComplaintOut,
    summary="Update complaint status (officer / admin)",
)
async def update_status(
    complaint_id: uuid.UUID,
    payload: StatusUpdateRequest,
    officer: OfficerRequired,
    service: ServiceDep,
    db: DbDep,
) -> ComplaintOut:
    updated = await service.update_status(
        str(complaint_id), payload.status, officer,
        notes=payload.notes,
        officer_id=str(payload.officer_id) if payload.officer_id else None,
    )
    await db.commit()
    return ComplaintOut.model_validate(updated)


# ─── Assign officer ───────────────────────────────────────────────────────────

@router.patch(
    "/{complaint_id}/assign",
    response_model=ComplaintOut,
    summary="Assign complaint to an officer (admin only)",
)
async def assign_officer(
    complaint_id: uuid.UUID,
    payload: AssignOfficerRequest,
    admin: AdminRequired,
    service: ServiceDep,
    db: DbDep,
) -> ComplaintOut:
    updated = await service.assign_officer(str(complaint_id), str(payload.officer_id), admin)
    await db.commit()
    return ComplaintOut.model_validate(updated)


# ─── Upload image ─────────────────────────────────────────────────────────────

@router.post(
    "/{complaint_id}/images",
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more images for a complaint",
)
async def upload_images(
    complaint_id: uuid.UUID,
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
    files: list[UploadFile] = File(...),
) -> dict:
    """
    Uploads happen synchronously within the request (not fire-and-forget),
    so an oversized or invalid file is reported back to the citizen
    immediately rather than silently failing in a background task they
    have no visibility into.
    """
    if len(files) > 5:
        raise BadRequestError("Maximum 5 images per upload.")

    uploaded = []
    for i, file in enumerate(files):
        content = await file.read()
        img = await service.upload_image(
            str(complaint_id), current_user, content,
            content_type=file.content_type or "image/jpeg",
            original_filename=file.filename or f"image_{i}.jpg",
        )
        uploaded.append({"id": str(img.id), "cdn_url": img.cdn_url, "is_primary": img.is_primary})

    await db.commit()
    return {"message": f"{len(uploaded)} image(s) uploaded.", "images": uploaded}


@router.delete(
    "/{complaint_id}/images/{image_id}",
    response_model=MessageResponse,
    summary="Delete an image from a complaint",
)
async def delete_image(
    complaint_id: uuid.UUID, image_id: uuid.UUID,
    current_user: CurrentUser, service: ServiceDep, db: DbDep,
) -> MessageResponse:
    await service.delete_image(str(complaint_id), str(image_id), current_user)
    await db.commit()
    return MessageResponse(message="Image deleted.")


# ─── Support / Upvote ─────────────────────────────────────────────────────────

@router.post("/{complaint_id}/support", response_model=MessageResponse, summary="Support/upvote a complaint")
async def support_complaint(
    complaint_id: uuid.UUID, current_user: CurrentUser, service: ServiceDep, db: DbDep,
) -> MessageResponse:
    result = await service.add_support(str(complaint_id), current_user)
    await db.commit()
    return MessageResponse(message=f"Support added. Total support: {result['count']}.")


@router.delete("/{complaint_id}/support", response_model=MessageResponse, summary="Remove support from a complaint")
async def remove_support(
    complaint_id: uuid.UUID, current_user: CurrentUser, service: ServiceDep, db: DbDep,
) -> MessageResponse:
    result = await service.remove_support(str(complaint_id), current_user)
    await db.commit()
    return MessageResponse(message=f"Support removed. Total support: {result['count']}.")


# ─── Verify resolution ────────────────────────────────────────────────────────

@router.post("/{complaint_id}/verify", response_model=ComplaintOut, summary="Citizen verifies a resolution")
async def verify_resolution(
    complaint_id: uuid.UUID,
    payload: VerifyResolutionRequest,
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
) -> ComplaintOut:
    updated = await service.verify_resolution(
        str(complaint_id), current_user,
        is_resolved=payload.is_resolved, feedback=payload.feedback, rating=payload.rating,
    )
    await db.commit()
    return ComplaintOut.model_validate(updated)
