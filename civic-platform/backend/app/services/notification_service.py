"""
NotificationService
===================
Orchestrates the full notification lifecycle:

  1. Persist an in-app Notification row (always)
  2. Dispatch push via FCMGateway (if tokens registered)
  3. Dispatch email via EmailService (if channel includes email)
  4. Update delivery status back into the row

Domain events consumed:
  • complaint_submitted      → citizen confirmation
  • complaint_assigned       → citizen informed, officer task appears
  • complaint_status_changed → citizen status update
  • complaint_resolved       → citizen verify prompt
  • verification_required    → reminder push after 24 h
  • duplicate_detected       → merge notice
  • sla_breach               → officer + admin alert
  • system_announcement      → broadcast to all or a role
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Complaint,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    User,
    UserRole,
)
from app.repositories.notification_repository import NotificationRepository
from app.services.email_service import EmailService
from app.services.fcm_gateway import FCMGateway, fcm_gateway

logger = logging.getLogger(__name__)


# ── Notification templates ────────────────────────────────────────────────────

def _t(ntype: NotificationType, **ctx) -> tuple[str, str]:
    """Return (title, body) for a notification type using string templates."""
    templates: dict[NotificationType, tuple[str, str]] = {
        NotificationType.COMPLAINT_SUBMITTED: (
            "Complaint received ✅",
            "Your complaint '{title}' ({number}) has been submitted and is under review.",
        ),
        NotificationType.COMPLAINT_ASSIGNED: (
            "Officer assigned 👮",
            "Officer {officer_name} has been assigned to {number}.",
        ),
        NotificationType.COMPLAINT_STATUS_CHANGED: (
            "Status update — {new_status}",
            "Your complaint {number} is now: {new_status}.{notes_suffix}",
        ),
        NotificationType.COMPLAINT_RESOLVED: (
            "Issue resolved — please verify ✔️",
            "The issue in {number} has been marked resolved. Tap to confirm.",
        ),
        NotificationType.VERIFICATION_REQUIRED: (
            "Your verification is needed 🔍",
            "Please verify whether {number} has been resolved.",
        ),
        NotificationType.DUPLICATE_DETECTED: (
            "Similar complaint found 🔗",
            "Your complaint {number} is similar to {parent_number}. It has been linked.",
        ),
        NotificationType.SYSTEM_ANNOUNCEMENT: (
            "{announcement_title}",
            "{announcement_body}",
        ),
    }
    title_tpl, body_tpl = templates.get(ntype, ("Notification", "You have a new notification."))
    return title_tpl.format(**ctx), body_tpl.format(**ctx)


class NotificationService:
    """
    High-level notification service.
    Inject via FastAPI Depends — one instance per request.
    """

    def __init__(
        self,
        db:      AsyncSession,
        repo:    Optional[NotificationRepository] = None,
        email:   Optional[EmailService] = None,
        fcm:     Optional[FCMGateway] = None,
    ) -> None:
        self._db    = db
        self._repo  = repo or NotificationRepository(db)
        self._email = email or EmailService()
        self._fcm   = fcm   or fcm_gateway

    # ── Core create-and-dispatch ──────────────────────────────────────────────

    async def send(
        self,
        recipient: User,
        ntype: NotificationType,
        title: str,
        body: str,
        *,
        complaint_id: Optional[str] = None,
        data: Optional[dict] = None,
        channels: Optional[list[NotificationChannel]] = None,
        image_url: Optional[str] = None,
    ) -> list[Notification]:
        """
        Persist in-app row(s) and dispatch over requested channels.

        If `channels` is None, defaults to [IN_APP, PUSH].
        Email is only sent when explicitly in `channels`.
        """
        if channels is None:
            channels = [NotificationChannel.IN_APP, NotificationChannel.PUSH]

        created: list[Notification] = []

        # Always create an IN_APP record first
        notif = await self._repo.create(
            recipient_id=str(recipient.id),
            ntype=ntype,
            title=title,
            body=body,
            complaint_id=complaint_id,
            data=data,
            channel=NotificationChannel.IN_APP,
        )
        created.append(notif)

        # Push
        if NotificationChannel.PUSH in channels:
            await self._dispatch_push(recipient, notif, title, body, data, image_url)

        # Email
        if NotificationChannel.EMAIL in channels:
            await self._dispatch_email(recipient, ntype, title, body, complaint_id)

        return created

    # ── Domain event handlers ─────────────────────────────────────────────────

    async def notify_complaint_submitted(self, complaint: Complaint, citizen: User) -> None:
        title, body = _t(
            NotificationType.COMPLAINT_SUBMITTED,
            title=complaint.title,
            number=complaint.complaint_number,
        )
        await self.send(
            recipient=citizen,
            ntype=NotificationType.COMPLAINT_SUBMITTED,
            title=title,
            body=body,
            complaint_id=str(complaint.id),
            data={
                "complaint_id":     str(complaint.id),
                "complaint_number": complaint.complaint_number,
                "status":           complaint.status,
                "severity":         complaint.severity,
                "screen":           "complaint_detail",
            },
        )

    async def notify_complaint_assigned(
        self,
        complaint: Complaint,
        citizen: User,
        officer_user: User,
    ) -> None:
        title, body = _t(
            NotificationType.COMPLAINT_ASSIGNED,
            officer_name=officer_user.full_name,
            number=complaint.complaint_number,
        )
        await self.send(
            recipient=citizen,
            ntype=NotificationType.COMPLAINT_ASSIGNED,
            title=title,
            body=body,
            complaint_id=str(complaint.id),
            data={
                "complaint_id":     str(complaint.id),
                "complaint_number": complaint.complaint_number,
                "officer_name":     officer_user.full_name,
                "screen":           "complaint_detail",
            },
            channels=[
                NotificationChannel.IN_APP,
                NotificationChannel.PUSH,
                NotificationChannel.EMAIL,
            ],
        )

    async def notify_status_changed(
        self,
        complaint: Complaint,
        citizen: User,
        old_status: str,
        new_status: str,
        notes: Optional[str] = None,
    ) -> None:
        friendly_status = new_status.replace("_", " ").title()
        notes_suffix = f" Note: {notes}" if notes else ""

        title, body = _t(
            NotificationType.COMPLAINT_STATUS_CHANGED,
            number=complaint.complaint_number,
            new_status=friendly_status,
            notes_suffix=notes_suffix,
        )
        await self.send(
            recipient=citizen,
            ntype=NotificationType.COMPLAINT_STATUS_CHANGED,
            title=title,
            body=body,
            complaint_id=str(complaint.id),
            data={
                "complaint_id":     str(complaint.id),
                "complaint_number": complaint.complaint_number,
                "old_status":       old_status,
                "new_status":       new_status,
                "screen":           "complaint_detail",
            },
        )

    async def notify_resolved(self, complaint: Complaint, citizen: User) -> None:
        title, body = _t(
            NotificationType.COMPLAINT_RESOLVED,
            number=complaint.complaint_number,
        )
        await self.send(
            recipient=citizen,
            ntype=NotificationType.COMPLAINT_RESOLVED,
            title=title,
            body=body,
            complaint_id=str(complaint.id),
            data={
                "complaint_id":     str(complaint.id),
                "complaint_number": complaint.complaint_number,
                "action":           "verify_resolution",
                "screen":           "complaint_verify",
            },
            channels=[
                NotificationChannel.IN_APP,
                NotificationChannel.PUSH,
                NotificationChannel.EMAIL,
            ],
        )

    async def notify_verification_required(
        self, complaint: Complaint, citizen: User
    ) -> None:
        title, body = _t(
            NotificationType.VERIFICATION_REQUIRED,
            number=complaint.complaint_number,
        )
        await self.send(
            recipient=citizen,
            ntype=NotificationType.VERIFICATION_REQUIRED,
            title=title,
            body=body,
            complaint_id=str(complaint.id),
            data={
                "complaint_id": str(complaint.id),
                "action":       "verify_resolution",
                "screen":       "complaint_verify",
            },
        )

    async def notify_duplicate_detected(
        self,
        complaint: Complaint,
        citizen: User,
        parent_number: str,
    ) -> None:
        title, body = _t(
            NotificationType.DUPLICATE_DETECTED,
            number=complaint.complaint_number,
            parent_number=parent_number,
        )
        await self.send(
            recipient=citizen,
            ntype=NotificationType.DUPLICATE_DETECTED,
            title=title,
            body=body,
            complaint_id=str(complaint.id),
            data={
                "complaint_id":  str(complaint.id),
                "parent_number": parent_number,
                "screen":        "complaint_detail",
            },
        )

    async def notify_sla_breach(
        self,
        complaint: Complaint,
        officer_user: Optional[User] = None,
    ) -> None:
        if not officer_user:
            return
        await self.send(
            recipient=officer_user,
            ntype=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="⚠️ SLA Breach Alert",
            body=(
                f"Complaint {complaint.complaint_number} ({complaint.severity.upper()}) "
                "has breached its SLA deadline. Immediate action required."
            ),
            complaint_id=str(complaint.id),
            data={
                "complaint_id":     str(complaint.id),
                "complaint_number": complaint.complaint_number,
                "severity":         complaint.severity,
                "screen":           "complaint_detail",
            },
            channels=[
                NotificationChannel.IN_APP,
                NotificationChannel.PUSH,
            ],
        )

    async def broadcast_announcement(
        self,
        title: str,
        body: str,
        *,
        target_role: Optional[UserRole] = None,
        recipient_ids: Optional[list[str]] = None,
        data: Optional[dict] = None,
    ) -> int:
        """
        Send a system announcement to multiple users.

        Args:
            target_role:   Broadcast to all users of this role (admin uses get_user_ids).
            recipient_ids: Explicit list of user IDs (overrides target_role).

        Returns the number of rows created.
        """
        if not recipient_ids:
            logger.info("broadcast_announcement: no recipients resolved")
            return 0

        records = [
            {
                "recipient_id": uid,
                "type":         NotificationType.SYSTEM_ANNOUNCEMENT,
                "title":        title,
                "body":         body,
                "data":         data or {},
                "channel":      NotificationChannel.IN_APP,
                "status":       NotificationStatus.PENDING,
                "scheduled_for":datetime.now(timezone.utc),
            }
            for uid in recipient_ids
        ]
        created = await self._repo.bulk_create(records)
        logger.info("Broadcast created %d notifications", len(created))
        return len(created)

    # ── User-facing read API ──────────────────────────────────────────────────

    async def get_for_user(
        self,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> tuple[Sequence[Notification], int]:
        return await self._repo.get_for_user(
            user_id, page=page, page_size=page_size, unread_only=unread_only
        )

    async def unread_count(self, user_id: str) -> int:
        return await self._repo.unread_count(user_id)

    async def mark_read(self, notif_id: str, user_id: str) -> bool:
        return await self._repo.mark_read(notif_id, user_id)

    async def mark_multiple_read(
        self, notif_ids: list[str], user_id: str
    ) -> int:
        return await self._repo.mark_multiple_read(notif_ids, user_id)

    async def mark_all_read(self, user_id: str) -> int:
        return await self._repo.mark_all_read(user_id)

    # ── Delivery dispatchers ──────────────────────────────────────────────────

    async def _dispatch_push(
        self,
        recipient: User,
        notif: Notification,
        title: str,
        body: str,
        data: Optional[dict],
        image_url: Optional[str],
    ) -> None:
        """Fetch FCM tokens from Redis and fire push notifications."""
        try:
            from app.core.redis_client import redis_client
            from app.repositories.auth_repository import AuthRepository

            auth_repo = AuthRepository(redis_client)
            tokens    = await auth_repo.get_all_fcm_tokens(str(recipient.id))

            if not tokens:
                return

            if len(tokens) == 1:
                result = await self._fcm.send(
                    token=tokens[0],
                    title=title,
                    body=body,
                    data=data,
                    image_url=image_url,
                )
                if result.success:
                    await self._repo.mark_sent(str(notif.id), result.message_id)
                elif result.is_permanent_failure:
                    # Token no longer valid — remove it
                    await auth_repo.delete_fcm_token(
                        str(recipient.id), "default"
                    )
                    await self._repo.mark_failed(str(notif.id), result.error_code or "permanent")
                else:
                    await self._repo.mark_failed(str(notif.id), result.error_code or "unknown")
            else:
                batch = await self._fcm.send_multicast(
                    tokens=tokens, title=title, body=body, data=data, image_url=image_url,
                )
                if batch.successes > 0:
                    await self._repo.mark_sent(str(notif.id))
                else:
                    await self._repo.mark_failed(str(notif.id), "all_tokens_failed")

                # Remove permanently invalid tokens
                if batch.invalid_tokens:
                    for bad_token in batch.invalid_tokens:
                        # Scan Redis to find the key for this token
                        async for key in redis_client.scan_iter(
                            f"auth:fcm:{recipient.id}:*", count=20
                        ):
                            stored = await redis_client.get(key)
                            stored_str = stored.decode() if isinstance(stored, bytes) else stored
                            if stored_str == bad_token:
                                await redis_client.delete(key)

        except Exception as exc:
            logger.error("Push dispatch error for user %s: %s", str(recipient.id), exc)
            await self._repo.mark_failed(str(notif.id), str(exc)[:200])

    async def _dispatch_email(
        self,
        recipient: User,
        ntype: NotificationType,
        title: str,
        body: str,
        complaint_id: Optional[str],
    ) -> None:
        """Send email notification via EmailService."""
        try:
            # Map notification type to email method
            if ntype == NotificationType.COMPLAINT_RESOLVED:
                await self._email.send_status_update_email(
                    to_email=recipient.email,
                    name=recipient.full_name,
                    complaint_number="",
                    title=title,
                    old_status="in_progress",
                    new_status="resolved",
                )
            elif ntype == NotificationType.COMPLAINT_ASSIGNED:
                await self._email.send_status_update_email(
                    to_email=recipient.email,
                    name=recipient.full_name,
                    complaint_number="",
                    title=title,
                    old_status="submitted",
                    new_status="assigned",
                )
            elif ntype == NotificationType.COMPLAINT_STATUS_CHANGED:
                await self._email.send_status_update_email(
                    to_email=recipient.email,
                    name=recipient.full_name,
                    complaint_number="",
                    title=title,
                    old_status="",
                    new_status="",
                )
            # Other types don't send email by default
        except Exception as exc:
            logger.error("Email dispatch error for user %s: %s", str(recipient.id), exc)

    # ── Delivery retry (called by Celery) ─────────────────────────────────────

    async def retry_failed(self) -> int:
        """
        Re-queue failed notifications that haven't exceeded max retries.
        Returns the count retried.
        """
        pending = await self._repo.get_failed_retryable()
        count = 0
        for notif in pending:
            await self._repo.reset_to_pending(str(notif.id))
            count += 1
        logger.info("Reset %d failed notifications to pending", count)
        return count

    # ── Admin analytics ───────────────────────────────────────────────────────

    async def get_delivery_stats(self) -> dict:
        status_counts  = await self._repo.delivery_stats()
        channel_counts = await self._repo.channel_stats()
        return {
            "by_status":  status_counts,
            "by_channel": channel_counts,
        }
