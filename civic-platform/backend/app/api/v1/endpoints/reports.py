"""
Reports API
============
POST   /reports                      — officer/admin: request a new report (queues async generation)
GET    /reports/me                   — list my requested reports
GET    /reports                      — admin: list all reports across all users
GET    /reports/{report_id}          — get report status/metadata
GET    /reports/{report_id}/download — get a presigned download URL (only when status=ready)
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.v1.dependencies.auth import AdminRequired, CurrentUser, DbDep
from app.models.models import ReportStatus, ReportType
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.complaint_service import ComplaintService
from app.services.notification_service import NotificationService
from app.services.report_service import ReportService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/reports", tags=["Reports"])


async def _get_service(db: DbDep) -> ReportService:
    complaint_service = ComplaintService(
        db=db, repo=ComplaintRepository(db), user_repo=UserRepository(db),
        storage=StorageService(), notifier=NotificationService(db), audit=AuditService(db),
    )
    return ReportService(
        db=db, repo=ReportRepository(db),
        complaint_service=complaint_service, storage=StorageService(),
    )


ServiceDep = Annotated[ReportService, Depends(_get_service)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class ReportRequest(BaseModel):
    type: ReportType
    title: str = Field(min_length=2, max_length=255)
    parameters: dict = Field(default_factory=dict, description=(
        "Type-specific options, e.g. {'months': 12} for summary reports, "
        "{'filters': {...}} for custom CSV exports, {'format': 'csv'} to "
        "force CSV instead of PDF for CUSTOM reports."
    ))


class ReportOut(BaseModel):
    id: str
    type: str
    title: str
    status: str
    file_format: str
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None
    error_message: Optional[str] = None
    queued_at: str
    completed_at: Optional[str] = None
    expires_at: Optional[str] = None

    @classmethod
    def from_report(cls, r) -> "ReportOut":
        return cls(
            id=str(r.id), type=r.type, title=r.title, status=r.status,
            file_format=r.file_format, file_size_bytes=r.file_size_bytes,
            page_count=r.page_count, error_message=r.error_message,
            queued_at=r.queued_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            expires_at=r.expires_at.isoformat() if r.expires_at else None,
        )


# ── Request a report ──────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ReportOut,
    status_code=202,
    summary="Request a new report — queues generation, returns immediately",
)
async def request_report(
    current_user: CurrentUser, service: ServiceDep, db: DbDep, body: ReportRequest,
) -> ReportOut:
    """
    Returns HTTP 202 (Accepted) with status='queued' immediately. The
    actual PDF/CSV is built asynchronously by a Celery worker — poll
    GET /reports/{id} to know when it's ready, then call
    GET /reports/{id}/download.
    """
    report = await service.request_report(
        current_user, report_type=body.type, title=body.title, parameters=body.parameters,
    )
    await db.commit()

    from app.workers.report_worker import generate_report
    generate_report.delay(str(report.id))

    return ReportOut.from_report(report)


# ── Listing ───────────────────────────────────────────────────────────────────

@router.get("/me", summary="List reports I've requested")
async def list_my_reports(
    current_user: CurrentUser,
    service: ServiceDep,
    status: Optional[ReportStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    reports, total = await service.list_my_reports(current_user, status=status, page=page, page_size=page_size)
    return {
        "items": [ReportOut.from_report(r) for r in reports],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("", summary="Admin: list all reports across all users")
async def list_all_reports(
    admin: AdminRequired,
    service: ServiceDep,
    status: Optional[ReportStatus] = Query(None),
    type: Optional[ReportType] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    reports, total = await service.list_all_reports(
        admin, status=status, report_type=type, page=page, page_size=page_size,
    )
    return {
        "items": [ReportOut.from_report(r) for r in reports],
        "total": total, "page": page, "page_size": page_size,
    }


# ── Single report ─────────────────────────────────────────────────────────────

@router.get("/{report_id}", response_model=ReportOut, summary="Get report status/metadata")
async def get_report(report_id: str, current_user: CurrentUser, service: ServiceDep) -> ReportOut:
    report = await service.get_report(report_id, current_user)
    return ReportOut.from_report(report)


@router.get(
    "/{report_id}/download",
    summary="Get a presigned download URL (only available once status=ready)",
)
async def download_report(report_id: str, current_user: CurrentUser, service: ServiceDep) -> dict:
    url = await service.get_download_url(report_id, current_user)
    return {"download_url": url, "expires_in_seconds": 3600}
