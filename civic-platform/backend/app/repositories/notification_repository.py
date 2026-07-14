"""
NotificationRepository
======================
All database operations for the notifications table.
Pure data-access — no delivery logic, no HTTP concerns.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Create ───────────────────────────────────────────────────────────────

    async def create(
        self,
        recipient_id: str,
        ntype: NotificationType,
        title: str,
        body: str,
        *,
        complaint_id: Optional[str] = None,
        data: Optional[dict] = None,
        channel: NotificationChannel = NotificationChannel.IN_APP,
        scheduled_for: Optional[datetime] = None,
    ) -> Notification:
        notif = Notification(
            recipient_id=recipient_id,
            complaint_id=complaint_id,
            type=ntype,
            title=title,
            body=body,
            data=data or {},
            channel=channel,
            status=NotificationStatus.PENDING,
            scheduled_for=scheduled_for or datetime.now(timezone.utc),
        )
        self._db.add(notif)
        await self._db.flush()
        await self._db.refresh(notif)
        return notif

    async def bulk_create(self, records: list[dict]) -> list[Notification]:
        """Insert multiple notification rows in one flush."""
        notifications = [Notification(**r) for r in records]
        self._db.add_all(notifications)
        await self._db.flush()
        return notifications

    # ── Lookups ──────────────────────────────────────────────────────────────

    async def get_by_id(self, notif_id: str) -> Optional[Notification]:
        result = await self._db.execute(
            select(Notification).where(Notification.id == notif_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
        ntype: Optional[NotificationType] = None,
    ) -> tuple[Sequence[Notification], int]:
        """Return (notifications, total_count) for a user."""
        filters = [Notification.recipient_id == user_id]

        if unread_only:
            filters.append(Notification.read_at.is_(None))
        if ntype:
            filters.append(Notification.type == ntype)

        total = (
            await self._db.execute(
                select(func.count()).where(and_(*filters))
            )
        ).scalar() or 0

        rows = (
            await self._db.execute(
                select(Notification)
                .where(and_(*filters))
                .order_by(desc(Notification.created_at))
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).scalars().all()

        return rows, total

    async def unread_count(self, user_id: str) -> int:
        result = await self._db.execute(
            select(func.count()).where(
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        return result.scalar() or 0

    # ── Pending delivery queue ────────────────────────────────────────────────

    async def get_pending(
        self,
        channel: Optional[NotificationChannel] = None,
        limit: int = 100,
    ) -> Sequence[Notification]:
        """Fetch notifications ready to deliver (Celery worker uses this)."""
        filters = [
            Notification.status == NotificationStatus.PENDING,
            Notification.scheduled_for <= func.now(),
            Notification.retry_count < 3,
        ]
        if channel:
            filters.append(Notification.channel == channel)

        return (
            await self._db.execute(
                select(Notification)
                .where(and_(*filters))
                .order_by(Notification.scheduled_for.asc())
                .limit(limit)
            )
        ).scalars().all()

    async def get_failed_retryable(self, limit: int = 50) -> Sequence[Notification]:
        """Notifications that failed but haven't hit max retries."""
        return (
            await self._db.execute(
                select(Notification)
                .where(
                    Notification.status == NotificationStatus.FAILED,
                    Notification.retry_count < 3,
                )
                .order_by(Notification.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()

    # ── Mark read ─────────────────────────────────────────────────────────────

    async def mark_read(self, notif_id: str, user_id: str) -> bool:
        result = await self._db.execute(
            update(Notification)
            .where(
                Notification.id == notif_id,
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(
                read_at=datetime.now(timezone.utc),
                status=NotificationStatus.READ,
            )
        )
        return result.rowcount > 0

    async def mark_multiple_read(
        self, notif_ids: list[str], user_id: str
    ) -> int:
        result = await self._db.execute(
            update(Notification)
            .where(
                Notification.id.in_(notif_ids),
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(
                read_at=datetime.now(timezone.utc),
                status=NotificationStatus.READ,
            )
        )
        return result.rowcount

    async def mark_all_read(self, user_id: str) -> int:
        result = await self._db.execute(
            update(Notification)
            .where(
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(
                read_at=datetime.now(timezone.utc),
                status=NotificationStatus.READ,
            )
        )
        return result.rowcount

    # ── Delivery status updates ───────────────────────────────────────────────

    async def mark_sent(
        self,
        notif_id: str,
        fcm_message_id: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            update(Notification)
            .where(Notification.id == notif_id)
            .values(
                status=NotificationStatus.SENT,
                sent_at=datetime.now(timezone.utc),
                fcm_message_id=fcm_message_id,
            )
        )

    async def mark_delivered(self, notif_id: str) -> None:
        await self._db.execute(
            update(Notification)
            .where(Notification.id == notif_id)
            .values(
                status=NotificationStatus.DELIVERED,
                delivered_at=datetime.now(timezone.utc),
            )
        )

    async def mark_failed(self, notif_id: str, reason: str) -> None:
        await self._db.execute(
            update(Notification)
            .where(Notification.id == notif_id)
            .values(
                status=NotificationStatus.FAILED,
                failed_reason=reason,
                retry_count=Notification.retry_count + 1,
            )
        )

    async def reset_to_pending(self, notif_id: str) -> None:
        """Reset a failed notification back to pending for retry."""
        await self._db.execute(
            update(Notification)
            .where(Notification.id == notif_id)
            .values(status=NotificationStatus.PENDING)
        )

    # ── Analytics / admin ─────────────────────────────────────────────────────

    async def delivery_stats(self) -> dict:
        rows = (
            await self._db.execute(
                select(
                    Notification.status,
                    func.count().label("cnt"),
                )
                .group_by(Notification.status)
            )
        ).all()
        return {r.status: r.cnt for r in rows}

    async def channel_stats(self) -> dict:
        rows = (
            await self._db.execute(
                select(
                    Notification.channel,
                    func.count().label("cnt"),
                    func.count()
                    .filter(Notification.status == NotificationStatus.SENT)
                    .label("sent"),
                    func.count()
                    .filter(Notification.status == NotificationStatus.FAILED)
                    .label("failed"),
                )
                .group_by(Notification.channel)
            )
        ).all()
        return [
            {"channel": r.channel, "total": r.cnt, "sent": r.sent, "failed": r.failed}
            for r in rows
        ]

    async def delete_old(self, days: int = 90) -> int:
        """Purge read notifications older than `days` days."""
        from sqlalchemy import text

        result = await self._db.execute(
            text(
                "DELETE FROM notifications WHERE read_at IS NOT NULL "
                "AND created_at < NOW() - INTERVAL ':days days'"
            ).bindparams(days=days)
        )
        return result.rowcount
