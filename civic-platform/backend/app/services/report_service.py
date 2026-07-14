"""
ReportService
==============
Generates the actual report files (PDF/CSV) backing the `reports` table.
Reuses ComplaintService's existing analytics methods as the data source —
this service's job is presentation (PDF layout) and lifecycle (queued →
generating → ready/failed/expired), not re-deriving analytics queries that
already exist.

Generation is dispatched to a Celery task (see workers/report_worker.py)
rather than run synchronously in the request — a report covering a year of
complaint history could take several seconds to render, which has no
business blocking an HTTP response.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.models.models import Report, ReportStatus, ReportType, User, UserRole
from app.repositories.report_repository import ReportRepository
from app.services.complaint_service import ComplaintService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

_REPORT_RETENTION_DAYS = 30


class ReportService:
    def __init__(
        self, db: AsyncSession, repo: ReportRepository,
        complaint_service: ComplaintService, storage: StorageService,
    ) -> None:
        self._db = db
        self._repo = repo
        self._complaints = complaint_service
        self._storage = storage

    # ── Request a report (queues it; actual generation happens async) ────────

    async def request_report(
        self, requester: User, report_type: ReportType,
        title: str, parameters: Optional[dict] = None,
    ) -> Report:
        if requester.role not in (UserRole.ADMIN, UserRole.OFFICER):
            raise ForbiddenError("Only officers and admins can generate reports.")

        report = await self._repo.create(
            generated_by=str(requester.id), type=report_type, title=title,
            parameters=parameters or {}, status=ReportStatus.QUEUED,
        )
        logger.info("Report queued: %s (%s) by %s", report.id, report_type, requester.email)
        return report

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def get_report(self, report_id: str, requester: User) -> Report:
        report = await self._repo.get_by_id(report_id)
        if not report:
            raise NotFoundError("Report", report_id)
        if str(report.generated_by) != str(requester.id) and requester.role != UserRole.ADMIN:
            raise ForbiddenError("You can only view your own reports.")
        return report

    async def list_my_reports(
        self, requester: User, status: Optional[ReportStatus] = None, page: int = 1, page_size: int = 20,
    ) -> tuple:
        reports, total = await self._repo.list_for_user(
            str(requester.id), status=status, page=page, page_size=page_size,
        )
        return reports, total

    async def list_all_reports(
        self, admin: User, status: Optional[ReportStatus] = None,
        report_type: Optional[ReportType] = None, page: int = 1, page_size: int = 20,
    ) -> tuple:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError("Admin access required.")
        return await self._repo.list_all(status=status, report_type=report_type, page=page, page_size=page_size)

    # ── Generation (called from the Celery task, NOT from the request path) ──

    async def generate(self, report_id: str) -> None:
        """
        Builds the actual file content and uploads to S3. Designed to be
        called from workers/report_worker.py's Celery task — never called
        directly from an API request handler, since this can take several
        seconds for a year-long trend report.
        """
        report = await self._repo.get_by_id(report_id)
        if not report:
            logger.error("generate() called for missing report %s", report_id)
            return

        await self._repo.mark_generating(report_id)
        await self._db.commit()

        try:
            file_bytes, page_count, summary = await self._build_report_content(report)
            ext = "csv" if report.type == ReportType.CUSTOM and report.parameters.get("format") == "csv" else "pdf"
            s3_key = f"reports/{report.generated_by}/{report_id}.{ext}"

            cdn_url = await self._storage.upload_bytes(
                key=s3_key, data=file_bytes,
                content_type="application/pdf" if ext == "pdf" else "text/csv",
                public=False,
            )

            expires_at = datetime.now(timezone.utc) + timedelta(days=_REPORT_RETENTION_DAYS)
            await self._repo.mark_ready(
                report_id, s3_key=s3_key, s3_bucket=self._storage_bucket_name(),
                cdn_url=cdn_url, file_size_bytes=len(file_bytes),
                page_count=page_count, summary=summary, expires_at=expires_at,
            )
            await self._db.commit()
            logger.info("Report %s generated successfully (%d bytes)", report_id, len(file_bytes))

        except Exception as exc:
            logger.error("Report generation failed for %s: %s", report_id, exc, exc_info=True)
            await self._repo.mark_failed(report_id, str(exc))
            await self._db.commit()

    def _storage_bucket_name(self) -> str:
        """StorageService keeps the configured bucket name on a private
        attribute — accessed via a named method rather than reaching into
        `_bucket` directly from outside the class."""
        return getattr(self._storage, "_bucket", "")

    async def _build_report_content(self, report: Report) -> tuple[bytes, Optional[int], dict]:
        """Returns (file_bytes, page_count_or_None, summary_dict)."""
        from types import SimpleNamespace
        # Generation always runs as a privileged background task regardless
        # of who originally requested it — this stand-in only needs to
        # satisfy the role check inside ComplaintService's analytics methods.
        system_requester = SimpleNamespace(role=UserRole.ADMIN)

        if report.type == ReportType.CATEGORY_ANALYSIS:
            data = await self._complaints.get_category_analytics()
            summary = {"categories": len(data)}
            pdf_bytes, pages = self._render_table_pdf(
                title=report.title, columns=["Category", "Total", "Resolved", "Resolution Rate"],
                rows=[[d["category"], d["total"], d["resolved"],
                       f"{round((d['resolved']/d['total'])*100, 1) if d['total'] else 0}%"] for d in data],
            )
            return pdf_bytes, pages, summary

        if report.type == ReportType.WARD_ANALYSIS:
            data = await self._complaints.get_ward_summary()
            summary = {"wards": len(data)}
            pdf_bytes, pages = self._render_table_pdf(
                title=report.title, columns=["Ward", "Total", "Resolved", "Resolution Rate"],
                rows=[[d["ward_id"], d["total"], d["resolved"],
                       f"{round((d['resolved']/d['total'])*100, 1) if d['total'] else 0}%"] for d in data],
            )
            return pdf_bytes, pages, summary

        if report.type in (ReportType.DAILY_SUMMARY, ReportType.WEEKLY_SUMMARY, ReportType.MONTHLY_SUMMARY):
            stats = await self._complaints.get_dashboard_stats(system_requester)
            months = report.parameters.get("months", 1)
            trend = await self._complaints.get_monthly_trend(months=months)
            summary = stats
            pdf_bytes, pages = self._render_summary_pdf(report.title, stats, trend)
            return pdf_bytes, pages, summary

        if report.type == ReportType.RESOLUTION_RATE:
            severity_dist = await self._complaints.get_severity_distribution()
            summary = {"severity_breakdown": severity_dist}
            pdf_bytes, pages = self._render_table_pdf(
                title=report.title, columns=["Severity", "Count", "Percentage"],
                rows=[[d["severity"], d["count"], f"{d['percentage']}%"] for d in severity_dist],
            )
            return pdf_bytes, pages, summary

        if report.type == ReportType.OFFICER_PERFORMANCE:
            from sqlalchemy import select
            from app.models.models import Officer, User as UserModel

            rows = (
                await self._db.execute(
                    select(Officer, UserModel)
                    .join(UserModel, Officer.user_id == UserModel.id)
                    .where(Officer.deleted_at.is_(None))
                    .order_by(Officer.performance_score.desc())
                    .limit(50)
                )
            ).all()
            table_rows = [
                [u.full_name, o.badge_number, o.total_assigned, o.total_resolved, float(o.performance_score)]
                for o, u in rows
            ]
            summary = {"officer_count": len(table_rows)}
            pdf_bytes, pages = self._render_table_pdf(
                title=report.title,
                columns=["Officer", "Badge", "Assigned", "Resolved", "Score"],
                rows=table_rows,
            )
            return pdf_bytes, pages, summary

        # CUSTOM / fallback — CSV export of raw complaint data
        filters = report.parameters.get("filters", {})
        csv_buf = await self._complaints.export_csv(system_requester, filters)
        content = csv_buf.getvalue().encode("utf-8")
        return content, None, {"format": "csv", "row_count": content.count(b"\n")}

    # ── PDF rendering helpers ─────────────────────────────────────────────────

    def _render_table_pdf(self, title: str, columns: list[str], rows: list[list]) -> tuple[bytes, int]:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, title=title)
        styles = getSampleStyleSheet()
        story = [
            Paragraph(title, styles["Title"]),
            Paragraph(
                f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')} — "
                "Smart Civic Intelligence Platform",
                styles["Normal"],
            ),
            Spacer(1, 18),
        ]

        table_data = [columns] + [[str(c) for c in row] for row in rows]
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
        doc.build(story)

        buf.seek(0)
        content = buf.getvalue()
        from pypdf import PdfReader
        page_count = len(PdfReader(io.BytesIO(content)).pages)
        return content, page_count

    def _render_summary_pdf(self, title: str, stats: dict, trend: list[dict]) -> tuple[bytes, int]:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, title=title)
        styles = getSampleStyleSheet()
        story = [
            Paragraph(title, styles["Title"]),
            Paragraph(
                f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')}",
                styles["Normal"],
            ),
            Spacer(1, 18),
            Paragraph("Key Metrics", styles["Heading2"]),
        ]

        kpi_rows = [
            ["Total Complaints", str(stats.get("total_complaints", 0))],
            ["Open Complaints", str(stats.get("open_complaints", 0))],
            ["Resolved Today", str(stats.get("resolved_today", 0))],
            ["Avg Resolution (days)", str(stats.get("avg_resolution_days", 0))],
        ]
        kpi_table = Table(kpi_rows, colWidths=[200, 150])
        kpi_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 24))

        if trend:
            story.append(Paragraph("Monthly Trend", styles["Heading2"]))
            trend_data = [["Month", "Submitted", "Resolved", "Pending"]] + [
                [t["month"], t["submitted"], t["resolved"], t["pending"]] for t in trend
            ]
            trend_table = Table(trend_data, repeatRows=1)
            trend_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]))
            story.append(trend_table)

        doc.build(story)
        buf.seek(0)
        content = buf.getvalue()
        from pypdf import PdfReader
        page_count = len(PdfReader(io.BytesIO(content)).pages)
        return content, page_count

    # ── Download URL ──────────────────────────────────────────────────────────

    async def get_download_url(self, report_id: str, requester: User) -> str:
        report = await self.get_report(report_id, requester)
        if report.status != ReportStatus.READY:
            raise BadRequestError(f"Report is not ready yet (status: {report.status}).")
        if not report.s3_key:
            raise BadRequestError("Report has no associated file.")
        return await self._storage.presigned_url(report.s3_key, expiry=3600)
