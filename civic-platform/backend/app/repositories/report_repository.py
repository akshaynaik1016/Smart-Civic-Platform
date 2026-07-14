"""
ReportRepository — every database operation that touches the `reports` table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Report, ReportStatus, ReportType


class ReportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, **kwargs) -> Report:
        report = Report(**kwargs)
        self._db.add(report)
        await self._db.flush()
        await self._db.refresh(report)
        return report

    async def get_by_id(self, report_id: str) -> Optional[Report]:
        q = select(Report).where(Report.id == report_id)
        return (await self._db.execute(q)).scalar_one_or_none()

    async def list_for_user(
        self, user_id: str, *, status: Optional[ReportStatus] = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple[Sequence[Report], int]:
        filters = [Report.generated_by == user_id]
        if status:
            filters.append(Report.status == status)

        total = (await self._db.execute(select(func.count()).where(and_(*filters)))).scalar() or 0
        rows = (
            await self._db.execute(
                select(Report).where(and_(*filters))
                .order_by(Report.queued_at.desc())
                .limit(page_size).offset((page - 1) * page_size)
            )
        ).scalars().all()
        return rows, total

    async def list_all(
        self, *, status: Optional[ReportStatus] = None, report_type: Optional[ReportType] = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple[Sequence[Report], int]:
        filters = []
        if status:
            filters.append(Report.status == status)
        if report_type:
            filters.append(Report.type == report_type)

        q_count = select(func.count())
        q_data = select(Report).order_by(Report.queued_at.desc())
        if filters:
            q_count = q_count.where(and_(*filters))
            q_data = q_data.where(and_(*filters))

        total = (await self._db.execute(q_count)).scalar() or 0
        rows = (
            await self._db.execute(q_data.limit(page_size).offset((page - 1) * page_size))
        ).scalars().all()
        return rows, total

    async def mark_generating(self, report_id: str) -> None:
        await self._db.execute(
            update(Report).where(Report.id == report_id)
            .values(status=ReportStatus.GENERATING, started_at=datetime.now(timezone.utc))
        )

    async def mark_ready(
        self, report_id: str, *, s3_key: str, s3_bucket: str, cdn_url: str,
        file_size_bytes: int, page_count: Optional[int] = None,
        summary: Optional[dict] = None, expires_at: Optional[datetime] = None,
    ) -> None:
        await self._db.execute(
            update(Report).where(Report.id == report_id).values(
                status=ReportStatus.READY,
                completed_at=datetime.now(timezone.utc),
                s3_key=s3_key, s3_bucket=s3_bucket, cdn_url=cdn_url,
                file_size_bytes=file_size_bytes, page_count=page_count,
                summary=summary, expires_at=expires_at,
            )
        )

    async def mark_failed(self, report_id: str, error_message: str) -> None:
        await self._db.execute(
            update(Report).where(Report.id == report_id).values(
                status=ReportStatus.FAILED,
                completed_at=datetime.now(timezone.utc),
                error_message=error_message[:2000],
            )
        )

    async def expire_old_reports(self) -> int:
        """Mark reports past their expires_at as expired — called by a periodic Celery task."""
        result = await self._db.execute(
            update(Report)
            .where(Report.status == ReportStatus.READY, Report.expires_at < datetime.now(timezone.utc))
            .values(status=ReportStatus.EXPIRED)
        )
        return result.rowcount
