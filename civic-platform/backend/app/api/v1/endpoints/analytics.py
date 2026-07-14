"""
Analytics API
==============
GET /analytics/dashboard            — top-line KPIs for the admin dashboard
GET /analytics/categories           — complaint counts + resolution rate by category
GET /analytics/wards                — complaint counts + resolution rate by ward
GET /analytics/trend                — monthly submitted/resolved/pending trend
GET /analytics/heatmap              — lat/lng/weight points for the map heatmap layer
GET /analytics/severity-distribution — severity breakdown with percentages
GET /analytics/officers/performance — officer leaderboard (assigned/resolved/avg-days)

All endpoints require officer or admin access — this is operational data,
not citizen-facing. Most handlers here are thin pass-throughs to methods
that already exist on ComplaintService / ComplaintRepository; this router's
job is mostly the HTTP binding, except for the officer leaderboard, which
is genuinely new logic (no OfficerService exists yet — see officers.py).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.v1.dependencies.auth import OfficerRequired, DbDep
from app.models.models import Officer, User
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.complaint_service import ComplaintService
from app.services.notification_service import NotificationService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


async def _get_complaint_service(db: DbDep) -> ComplaintService:
    return ComplaintService(
        db=db,
        repo=ComplaintRepository(db),
        user_repo=UserRepository(db),
        storage=StorageService(),
        notifier=NotificationService(db),
        audit=AuditService(db),
    )


@router.get(
    "/dashboard",
    summary="Top-line KPIs: total/open complaints, resolved today, avg resolution time",
)
async def get_dashboard_stats(officer: OfficerRequired, db: DbDep) -> dict:
    service = await _get_complaint_service(db)
    return await service.get_dashboard_stats(officer)


@router.get(
    "/categories",
    summary="Complaint counts and resolution rate broken down by category",
)
async def get_category_analytics(officer: OfficerRequired, db: DbDep) -> list[dict]:
    service = await _get_complaint_service(db)
    return await service.get_category_analytics()


@router.get(
    "/wards",
    summary="Complaint counts and resolution rate broken down by ward",
)
async def get_ward_summary(officer: OfficerRequired, db: DbDep) -> list[dict]:
    service = await _get_complaint_service(db)
    return await service.get_ward_summary()


@router.get(
    "/trend",
    summary="Monthly submitted/resolved/pending trend",
)
async def get_monthly_trend(
    officer: OfficerRequired,
    db: DbDep,
    months: int = Query(6, ge=1, le=24, description="How many months back to include"),
) -> list[dict]:
    service = await _get_complaint_service(db)
    return await service.get_monthly_trend(months)


@router.get(
    "/heatmap",
    summary="Lat/lng/weight points for the map heatmap layer (open complaints only)",
)
async def get_heatmap(officer: OfficerRequired, db: DbDep) -> list[dict]:
    service = await _get_complaint_service(db)
    return await service.get_heatmap()


@router.get(
    "/severity-distribution",
    summary="Severity breakdown with percentages",
)
async def get_severity_distribution(officer: OfficerRequired, db: DbDep) -> list[dict]:
    service = await _get_complaint_service(db)
    return await service.get_severity_distribution()


@router.get(
    "/officers/performance",
    summary="Officer leaderboard — assigned, resolved, avg resolution days, performance score",
)
async def get_officer_performance(
    officer: OfficerRequired,
    db: DbDep,
    department: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    filters = [Officer.deleted_at.is_(None)]
    if department:
        filters.append(Officer.department == department)

    rows = (
        await db.execute(
            select(Officer, User)
            .join(User, Officer.user_id == User.id)
            .where(*filters)
            .order_by(Officer.performance_score.desc())
            .limit(limit)
        )
    ).all()

    return [
        {
            "officer_id":          str(officer.id),
            "name":                user.full_name,
            "badge_number":        officer.badge_number,
            "department":          officer.department,
            "total_assigned":      officer.total_assigned,
            "total_resolved":      officer.total_resolved,
            "avg_resolution_days": float(officer.avg_resolution_days) if officer.avg_resolution_days else None,
            "performance_score":   float(officer.performance_score),
            "is_available":        officer.is_available,
            "workload_pct": (
                round((officer.total_assigned / officer.max_complaints) * 100, 1)
                if officer.max_complaints else 0
            ),
        }
        for officer, user in rows
    ]
