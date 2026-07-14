"""
Celery notification workers
============================
Background tasks for the notification pipeline.

Tasks:
  dispatch_pending_notifications   — poll pending rows, fire FCM/email
  retry_failed_notifications       — re-queue retryable failures
  send_verification_reminders      — 24h push to citizens who haven't verified
  check_sla_breaches               — sweep overdue complaints, alert officers
  send_daily_digest                — officer daily summary email
  purge_old_notifications          — clean up read notifications > 90 days

Schedule (configured in Celery beat):
  dispatch_pending_notifications   → every 1 minute
  retry_failed_notifications       → every 15 minutes
  send_verification_reminders      → every 6 hours
  check_sla_breaches               → every 15 minutes
  send_daily_digest                → daily at 07:00 IST
  purge_old_notifications          → weekly on Sunday 02:00 IST
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger

from app.core.config import settings

logger = get_task_logger(__name__)

# ─── Celery application ───────────────────────────────────────────────────────

celery_app = Celery(
    "smart_civic_notifications",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                    # re-queue on worker crash
    worker_prefetch_multiplier=1,           # fair dispatch
    task_soft_time_limit=120,              # 2 min soft limit
    task_time_limit=180,                   # 3 min hard limit
    result_expires=3600,
)

# ─── Beat schedule ────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    "dispatch-pending-every-1-min": {
        "task": "app.workers.notification_worker.dispatch_pending_notifications",
        "schedule": 60.0,
    },
    "retry-failed-every-15-min": {
        "task": "app.workers.notification_worker.retry_failed_notifications",
        "schedule": 900.0,
    },
    "verification-reminders-every-6h": {
        "task": "app.workers.notification_worker.send_verification_reminders",
        "schedule": 21600.0,
    },
    "sla-breach-check-every-15-min": {
        "task": "app.workers.notification_worker.check_sla_breaches",
        "schedule": 900.0,
    },
    "daily-officer-digest": {
        "task": "app.workers.notification_worker.send_daily_digest",
        "schedule": crontab(hour=1, minute=30),  # 07:00 IST = 01:30 UTC
    },
    "purge-old-notifications-weekly": {
        "task": "app.workers.notification_worker.purge_old_notifications",
        "schedule": crontab(hour=20, minute=30, day_of_week="sun"),  # Sun 02:00 IST
    },
}


# ─── Async helper ────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _get_db_and_redis():
    """Open a DB session and Redis connection for use inside a task."""
    from app.core.database import AsyncSessionLocal
    from app.core.redis_client import redis_client

    db = AsyncSessionLocal()
    return db, redis_client


# ─── Tasks ───────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.workers.notification_worker.dispatch_pending_notifications",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def dispatch_pending_notifications(self):
    """
    Pull all PENDING notifications from DB and fire them over FCM/email.
    Runs every minute via beat.
    """
    async def _run_task():
        db, redis_client = await _get_db_and_redis()
        dispatched = 0
        try:
            from app.repositories.notification_repository import NotificationRepository
            from app.services.notification_service import NotificationService
            from app.services.email_service import EmailService
            from app.services.fcm_gateway import fcm_gateway
            from app.models.models import NotificationChannel, User
            from sqlalchemy import select

            repo    = NotificationRepository(db)
            service = NotificationService(db, repo, EmailService(), fcm_gateway)

            pending = await repo.get_pending(limit=200)
            logger.info("dispatch_pending: %d notifications to process", len(pending))

            for notif in pending:
                # Load recipient
                result = await db.execute(
                    select(User).where(User.id == notif.recipient_id)
                )
                recipient = result.scalar_one_or_none()
                if not recipient:
                    await repo.mark_failed(str(notif.id), "recipient_not_found")
                    continue

                if notif.channel == NotificationChannel.PUSH:
                    await service._dispatch_push(
                        recipient, notif,
                        notif.title, notif.body,
                        notif.data, None,
                    )
                elif notif.channel == NotificationChannel.EMAIL:
                    await service._dispatch_email(
                        recipient, notif.type,
                        notif.title, notif.body,
                        str(notif.complaint_id) if notif.complaint_id else None,
                    )

                dispatched += 1

            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("dispatch_pending error: %s", exc)
            raise self.retry(exc=exc)
        finally:
            await db.close()

        return {"dispatched": dispatched}

    return _run(_run_task())


@celery_app.task(
    name="app.workers.notification_worker.retry_failed_notifications",
    bind=True,
    max_retries=2,
)
def retry_failed_notifications(self):
    """Reset retryable failed notifications back to PENDING."""
    async def _run_task():
        db, _ = await _get_db_and_redis()
        try:
            from app.repositories.notification_repository import NotificationRepository
            from app.services.notification_service import NotificationService

            repo    = NotificationRepository(db)
            service = NotificationService(db, repo)
            count   = await service.retry_failed()
            await db.commit()
            logger.info("retry_failed: reset %d notifications", count)
            return {"reset": count}
        except Exception as exc:
            await db.rollback()
            logger.error("retry_failed error: %s", exc)
            raise self.retry(exc=exc)
        finally:
            await db.close()

    return _run(_run_task())


@celery_app.task(
    name="app.workers.notification_worker.send_verification_reminders",
    bind=True,
)
def send_verification_reminders(self):
    """
    Find complaints resolved > 24h ago where citizen hasn't verified,
    and send a reminder push.
    """
    async def _run_task():
        db, _ = await _get_db_and_redis()
        sent = 0
        try:
            from sqlalchemy import select, and_
            from app.models.models import Complaint, ComplaintStatus, User
            from app.repositories.notification_repository import NotificationRepository
            from app.services.notification_service import NotificationService
            from app.services.fcm_gateway import fcm_gateway
            from app.services.email_service import EmailService

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            q = select(Complaint).where(
                and_(
                    Complaint.status == ComplaintStatus.RESOLVED,
                    Complaint.citizen_verified == False,
                    Complaint.resolved_at <= cutoff,
                    Complaint.deleted_at.is_(None),
                )
            )
            complaints = (await db.execute(q)).scalars().all()

            service = NotificationService(
                db,
                NotificationRepository(db),
                EmailService(),
                fcm_gateway,
            )

            for complaint in complaints:
                citizen_q = select(User).where(User.id == complaint.citizen_id)
                citizen   = (await db.execute(citizen_q)).scalar_one_or_none()
                if citizen:
                    await service.notify_verification_required(complaint, citizen)
                    sent += 1

            await db.commit()
            logger.info("verification_reminders: sent %d reminders", sent)
            return {"sent": sent}
        except Exception as exc:
            await db.rollback()
            logger.error("verification_reminders error: %s", exc)
        finally:
            await db.close()

        return {"sent": sent}

    return _run(_run_task())


@celery_app.task(
    name="app.workers.notification_worker.check_sla_breaches",
    bind=True,
)
def check_sla_breaches(self):
    """Mark overdue complaints as SLA-breached and alert assigned officers."""
    async def _run_task():
        db, _ = await _get_db_and_redis()
        count = 0
        try:
            from sqlalchemy import select, update, and_
            from app.models.models import (
                Complaint, ComplaintStatus, Officer, User,
            )
            from app.repositories.notification_repository import NotificationRepository
            from app.services.notification_service import NotificationService
            from app.services.fcm_gateway import fcm_gateway
            from app.services.email_service import EmailService

            now = datetime.now(timezone.utc)
            breach_q = select(Complaint).where(
                and_(
                    Complaint.deleted_at.is_(None),
                    Complaint.sla_deadline < now,
                    Complaint.sla_breached == False,
                    Complaint.status.not_in([
                        ComplaintStatus.RESOLVED, ComplaintStatus.VERIFIED,
                        ComplaintStatus.CLOSED,   ComplaintStatus.REJECTED,
                    ]),
                )
            )
            complaints = (await db.execute(breach_q)).scalars().all()

            service = NotificationService(
                db,
                NotificationRepository(db),
                EmailService(),
                fcm_gateway,
            )

            for complaint in complaints:
                # Mark breached
                await db.execute(
                    update(Complaint)
                    .where(Complaint.id == complaint.id)
                    .values(sla_breached=True)
                )
                count += 1

                # Alert officer
                if complaint.officer_id:
                    officer_q = (
                        select(Officer, User)
                        .join(User, Officer.user_id == User.id)
                        .where(Officer.id == complaint.officer_id)
                    )
                    row = (await db.execute(officer_q)).first()
                    if row:
                        _, officer_user = row
                        await service.notify_sla_breach(complaint, officer_user)

            await db.commit()
            logger.info("sla_breach_check: marked %d breaches", count)
            return {"breached": count}
        except Exception as exc:
            await db.rollback()
            logger.error("sla_breach_check error: %s", exc)
        finally:
            await db.close()

        return {"breached": count}

    return _run(_run_task())


@celery_app.task(
    name="app.workers.notification_worker.send_daily_digest",
    bind=True,
)
def send_daily_digest(self):
    """
    Email each officer a digest of their open complaints for the day.
    Runs at 07:00 IST via beat.
    """
    async def _run_task():
        db, _ = await _get_db_and_redis()
        sent = 0
        try:
            from sqlalchemy import select, and_, func
            from app.models.models import (
                Officer, User, Complaint, ComplaintStatus,
            )
            from app.services.email_service import EmailService

            email_svc = EmailService()

            officers_q = (
                select(Officer, User)
                .join(User, Officer.user_id == User.id)
                .where(Officer.deleted_at.is_(None))
            )
            officers = (await db.execute(officers_q)).all()

            for officer, user in officers:
                open_q = select(func.count()).where(
                    and_(
                        Complaint.officer_id == officer.id,
                        Complaint.status.in_([
                            ComplaintStatus.ASSIGNED,
                            ComplaintStatus.IN_PROGRESS,
                        ]),
                        Complaint.deleted_at.is_(None),
                    )
                )
                sla_breach_q = select(func.count()).where(
                    and_(
                        Complaint.officer_id == officer.id,
                        Complaint.sla_breached == True,
                        Complaint.deleted_at.is_(None),
                    )
                )
                open_count  = (await db.execute(open_q)).scalar() or 0
                breach_count= (await db.execute(sla_breach_q)).scalar() or 0

                if open_count == 0:
                    continue

                subject = f"Daily Digest — {open_count} open complaints [{datetime.now().strftime('%d %b')}]"
                html = f"""
                <div style="font-family:Inter,sans-serif;padding:24px;background:#f0f4f8">
                  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:24px">
                    <h2 style="color:#0d1b2a">Good morning, {user.full_name} 👋</h2>
                    <p>Here's your daily complaint summary:</p>
                    <div style="display:flex;gap:12px;margin:20px 0">
                      <div style="flex:1;background:#eff6ff;border-radius:10px;padding:14px;text-align:center">
                        <div style="font-size:28px;font-weight:700;color:#1d4ed8">{open_count}</div>
                        <div style="font-size:12px;color:#64748b">Open complaints</div>
                      </div>
                      <div style="flex:1;background:#fef2f2;border-radius:10px;padding:14px;text-align:center">
                        <div style="font-size:28px;font-weight:700;color:#dc2626">{breach_count}</div>
                        <div style="font-size:12px;color:#64748b">SLA breaches</div>
                      </div>
                    </div>
                    <p style="color:#64748b;font-size:12px">Log in to the Smart Civic portal to take action.</p>
                  </div>
                </div>"""

                await email_svc._send(user.email, subject, html)
                sent += 1

            logger.info("daily_digest: sent to %d officers", sent)
            return {"sent": sent}
        except Exception as exc:
            logger.error("daily_digest error: %s", exc)
        finally:
            await db.close()

        return {"sent": sent}

    return _run(_run_task())


@celery_app.task(
    name="app.workers.notification_worker.purge_old_notifications",
    bind=True,
)
def purge_old_notifications(self):
    """Remove read notifications older than 90 days."""
    async def _run_task():
        db, _ = await _get_db_and_redis()
        try:
            from app.repositories.notification_repository import NotificationRepository
            repo    = NotificationRepository(db)
            deleted = await repo.delete_old(days=90)
            await db.commit()
            logger.info("purge_old_notifications: deleted %d rows", deleted)
            return {"deleted": deleted}
        except Exception as exc:
            await db.rollback()
            logger.error("purge_old_notifications error: %s", exc)
        finally:
            await db.close()
        return {"deleted": 0}

    return _run(_run_task())


# ── One-shot task helpers (called by API endpoints) ───────────────────────────

@celery_app.task(
    name="app.workers.notification_worker.send_push_to_user",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def send_push_to_user(
    self,
    user_id: str,
    title: str,
    body: str,
    data: dict | None = None,
    notification_id: str | None = None,
):
    """
    Fire-and-forget push task. Called by the API immediately after
    persisting the in-app Notification row, so the HTTP response is
    not blocked by FCM latency.
    """
    async def _run_task():
        _, redis_client = await _get_db_and_redis()
        try:
            from app.repositories.auth_repository import AuthRepository
            from app.services.fcm_gateway import fcm_gateway

            auth_repo = AuthRepository(redis_client)
            tokens    = await auth_repo.get_all_fcm_tokens(user_id)

            if not tokens:
                return {"sent": 0}

            if len(tokens) == 1:
                result = await fcm_gateway.send(tokens[0], title, body, data)
                return {"sent": 1 if result.success else 0}

            batch = await fcm_gateway.send_multicast(tokens, title, body, data)
            return {"sent": batch.successes, "failed": batch.failures}

        except Exception as exc:
            logger.error("send_push_to_user error [%s]: %s", user_id, exc)
            raise self.retry(exc=exc)

    return _run(_run_task())


@celery_app.task(
    name="app.workers.notification_worker.send_topic_push",
)
def send_topic_push(topic: str, title: str, body: str, data: dict | None = None):
    """Broadcast a push to all subscribers of an FCM topic."""
    async def _run_task():
        from app.services.fcm_gateway import fcm_gateway
        result = await fcm_gateway.send_to_topic(topic, title, body, data)
        return {"success": result.success, "message_id": result.message_id}

    return _run(_run_task())
