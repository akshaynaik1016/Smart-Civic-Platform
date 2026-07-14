"""
Report generation worker
==========================
Registers the report-generation task on the SAME Celery app instance
already constructed in workers/notification_worker.py — deliberately not a
second Celery() app, since running two broker connections in one worker
process is a common source of confusing "why didn't my task fire" bugs.

Task:
  generate_report(report_id)   — builds the PDF/CSV and uploads to S3,
                                   dispatched from POST /reports
  expire_old_reports           — periodic sweep marking past-expiry reports
                                   as expired (daily)

This module must be imported wherever celery_app is loaded (e.g. the
Celery worker entrypoint / docker-compose command) so its @celery_app.task
decorators actually register. See docker-compose.yml's `worker` service
command — it already points at notification_worker:celery_app; as long as
this module is imported before that app starts consuming, both task sets
share one worker pool.
"""

from __future__ import annotations

import asyncio
import logging

from celery.utils.log import get_task_logger

from app.workers.notification_worker import celery_app

logger = get_task_logger(__name__)


def _run_async(coro):
    """Celery tasks are sync; bridge into the async service layer per-call."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.workers.report_worker.generate_report",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def generate_report(self, report_id: str) -> dict:
    """
    Generates the report file and uploads it to S3. Called via
    .delay(report_id) immediately after POST /reports queues the row, so
    the citizen-facing request returns instantly while the PDF renders
    in the background.
    """
    async def _do():
        from app.core.database import AsyncSessionLocal
        from app.repositories.complaint_repository import ComplaintRepository
        from app.repositories.report_repository import ReportRepository
        from app.repositories.user_repository import UserRepository
        from app.services.audit_service import AuditService
        from app.services.complaint_service import ComplaintService
        from app.services.notification_service import NotificationService
        from app.services.report_service import ReportService
        from app.services.storage_service import StorageService

        async with AsyncSessionLocal() as db:
            complaint_service = ComplaintService(
                db=db, repo=ComplaintRepository(db), user_repo=UserRepository(db),
                storage=StorageService(), notifier=NotificationService(db), audit=AuditService(db),
            )
            report_service = ReportService(
                db=db, repo=ReportRepository(db),
                complaint_service=complaint_service, storage=StorageService(),
            )
            await report_service.generate(report_id)

    try:
        _run_async(_do())
        logger.info("Report %s generation task completed", report_id)
        return {"report_id": report_id, "status": "completed"}
    except Exception as exc:
        logger.error("Report %s generation task failed: %s", report_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(name="app.workers.report_worker.expire_old_reports")
def expire_old_reports() -> dict:
    """Periodic sweep — marks reports past their expires_at as 'expired'."""
    async def _do():
        from app.core.database import AsyncSessionLocal
        from app.repositories.report_repository import ReportRepository

        async with AsyncSessionLocal() as db:
            repo = ReportRepository(db)
            count = await repo.expire_old_reports()
            await db.commit()
            return count

    count = _run_async(_do())
    logger.info("Expired %d old report(s)", count)
    return {"expired_count": count}


# ─── Register this task's beat schedule entry on the shared app ──────────────

celery_app.conf.beat_schedule["expire-old-reports-daily"] = {
    "task": "app.workers.report_worker.expire_old_reports",
    "schedule": 86400.0,   # once a day
}
