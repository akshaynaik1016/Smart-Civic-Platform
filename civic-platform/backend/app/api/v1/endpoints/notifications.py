"""
Notification endpoints
======================

GET    /notifications                — list for current user (paginated)
GET    /notifications/unread-count   — badge count
PATCH  /notifications/read           — mark one / many / all as read
GET    /notifications/{id}           — single notification detail
DELETE /notifications/{id}           — delete a notification
POST   /notifications/push/test      — send test push to self (dev)
POST   /notifications/broadcast      — admin broadcast
GET    /notifications/admin/stats    — delivery analytics (admin)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import (
    CurrentUser,
    PaginationDep,
    AdminRequired,
)
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.models import (
    NotificationChannel,
    NotificationType,
    User,
    UserRole,
)
from app.repositories.notification_repository import NotificationRepository
from app.schemas.schemas import MessageResponse, NotificationOut, PaginatedResponse
from app.services.email_service import EmailService
from app.services.fcm_gateway import fcm_gateway
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])



# ── Dependency: NotificationService ──────────────────────────────────────────

async def _get_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    return NotificationService(
        db=db,
        repo=NotificationRepository(db),
        email=EmailService(),
        fcm=fcm_gateway,
    )

ServiceDep = Annotated[NotificationService, Depends(_get_service)]


# ── Request / Response models ────────────────────────────────────────────────

class MarkReadRequest(BaseModel):
    """Pass notification_ids to mark specific ones, or omit to mark all."""
    notification_ids: Optional[List[uuid.UUID]] = None


class BroadcastRequest(BaseModel):
    title:          str
    body:           str
    target_role:    Optional[str] = None
    recipient_ids:  Optional[List[uuid.UUID]] = None
    data:           Optional[dict] = None


class TestPushRequest(BaseModel):
    title: str = "Test Push 🔔"
    body:  str = "This is a test notification from Smart Civic."


class UnreadCountResponse(BaseModel):
    count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedResponse[NotificationOut],
    summary="List notifications for the current user",
)
async def list_notifications(
    current_user: CurrentUser,
    service:      ServiceDep,
    pagination:   PaginationDep,
    unread_only:  bool = Query(False, description="Return only unread notifications"),
    ntype:        Optional[str] = Query(None, description="Filter by notification type"),
):
    """
    Returns a paginated list of notifications for the authenticated user.
    Sorted newest-first.
    """
    from app.models.models import NotificationType as NT

    ntype_enum = NT(ntype) if ntype else None

    rows, total = await service._repo.get_for_user(
        str(current_user.id),
        page=pagination.page,
        page_size=pagination.page_size,
        unread_only=unread_only,
        ntype=ntype_enum,
    )

    import math

    return {
        "items":     [NotificationOut.model_validate(n) for n in rows],
        "total":     total,
        "page":      pagination.page,
        "page_size": pagination.page_size,
        "pages":     math.ceil(total / pagination.page_size) if pagination.page_size else 1,
    }


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get the unread notification badge count",
)
async def get_unread_count(
    current_user: CurrentUser,
    service:      ServiceDep,
):
    count = await service.unread_count(str(current_user.id))
    return {"count": count}


@router.patch(
    "/read",
    response_model=MessageResponse,
    summary="Mark notifications as read",
)
async def mark_read(
    current_user: CurrentUser,
    service:      ServiceDep,
    body:         MarkReadRequest = Body(...),
):
    """
    - Pass `notification_ids` to mark specific ones read.
    - Omit (or pass null) to mark **all** as read.
    """
    if body.notification_ids:
        count = await service.mark_multiple_read(
            [str(nid) for nid in body.notification_ids],
            str(current_user.id),
        )
    else:
        count = await service.mark_all_read(str(current_user.id))

    return {"message": f"{count} notification(s) marked as read."}


@router.get(
    "/{notification_id}",
    response_model=NotificationOut,
    summary="Get a single notification",
)
async def get_notification(
    notification_id: uuid.UUID,
    current_user:    CurrentUser,
    service:         ServiceDep,
):
    notif = await service._repo.get_by_id(str(notification_id))
    if not notif:
        raise NotFoundError("Notification", str(notification_id))
    if str(notif.recipient_id) != str(current_user.id) and current_user.role != UserRole.ADMIN:
        raise ForbiddenError("Access denied.")

    # Auto-mark read on open
    if not notif.read_at:
        await service.mark_read(str(notification_id), str(current_user.id))

    return NotificationOut.model_validate(notif)


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a notification",
)
async def delete_notification(
    notification_id: uuid.UUID,
    current_user:    CurrentUser,
    service:         ServiceDep,
):
    notif = await service._repo.get_by_id(str(notification_id))
    if not notif:
        raise NotFoundError("Notification", str(notification_id))
    if str(notif.recipient_id) != str(current_user.id) and current_user.role != UserRole.ADMIN:
        raise ForbiddenError("Access denied.")

    from sqlalchemy import delete
    from app.models.models import Notification

    await service._db.execute(
        delete(Notification).where(Notification.id == str(notification_id))
    )


# ── Push test (dev / self-testing) ────────────────────────────────────────────

@router.post(
    "/push/test",
    response_model=MessageResponse,
    summary="Send a test push notification to yourself",
)
async def send_test_push(
    current_user: CurrentUser,
    body:         TestPushRequest = Body(...),
):
    """
    Fires a push to all FCM tokens registered for the current user.
    Useful for mobile testing without triggering a real complaint event.
    """
    from app.core.redis_client import redis_client
    from app.repositories.auth_repository import AuthRepository

    auth_repo = AuthRepository(redis_client)
    tokens    = await auth_repo.get_all_fcm_tokens(str(current_user.id))

    if not tokens:
        return {"message": "No FCM tokens registered for your account."}

    result = await fcm_gateway.send_multicast(
        tokens=tokens,
        title=body.title,
        body=body.body,
        data={"type": "test"},
    )
    return {"message": f"Sent to {result.successes}/{len(tokens)} device(s)."}


# ── Admin: broadcast ──────────────────────────────────────────────────────────

@router.post(
    "/broadcast",
    response_model=MessageResponse,
    summary="Broadcast a system announcement (admin only)",
)
async def broadcast(
    admin: AdminRequired,
    service: ServiceDep,
    body:         BroadcastRequest = Body(...),
    background:   BackgroundTasks = BackgroundTasks(),
):
    """
    Send a system announcement.

    - Provide `recipient_ids` to target specific users.
    - Or provide `target_role` to target all users of that role.
      The actual user resolution happens in the background task.
    """
    recipient_ids = [str(uid) for uid in (body.recipient_ids or [])]

    # If no explicit list, we'd need to query all users with target_role.
    # The service handles None → empty, so the caller must provide IDs or
    # enqueue a separate async job to resolve the role list.
    count = await service.broadcast_announcement(
        title=body.title,
        body=body.body,
        target_role=UserRole(body.target_role) if body.target_role else None,
        recipient_ids=recipient_ids or None,
        data=body.data,
    )

    # If FCM topic push is requested
    if body.target_role:
        background.add_task(
            _push_to_role_topic,
            topic=f"role_{body.target_role}",
            title=body.title,
            body=body.body,
            data=body.data,
        )

    return {"message": f"Broadcast queued for {count} recipient(s)."}


async def _push_to_role_topic(
    topic: str, title: str, body: str, data: Optional[dict]
) -> None:
    """Fire a topic push as a background task."""
    try:
        result = await fcm_gateway.send_to_topic(topic, title, body, data)
        if not result.success:
            from app.core.logging import get_logger
            get_logger(__name__).warning(
                "Topic push failed [%s]: %s", topic, result.error_code
            )
    except Exception as exc:
        pass  # Background task — never let it propagate


# ── Admin: delivery analytics ────────────────────────────────────────────────

@router.get(
    "/admin/stats",
    summary="Notification delivery analytics (admin only)",
)
async def delivery_stats(
    admin: AdminRequired,
    service: ServiceDep,
):
    return await service.get_delivery_stats()


# ── Device token registration (mobile app) ────────────────────────────────────

class DeviceTokenRequest(BaseModel):
    fcm_token: str
    device_id: str = "default"
    topic_subscriptions: Optional[List[str]] = None


@router.post(
    "/device-token",
    response_model=MessageResponse,
    summary="Register a device FCM token",
)
async def register_device_token(
    current_user: CurrentUser,
    body:         DeviceTokenRequest = Body(...),
):
    """
    Called by the Flutter app on startup or when FCM issues a new token.
    Stores the token in Redis for future push dispatch.
    """
    from app.core.redis_client import redis_client
    from app.repositories.auth_repository import AuthRepository

    auth_repo = AuthRepository(redis_client)
    await auth_repo.store_fcm_token(
        user_id=str(current_user.id),
        device_id=body.device_id,
        fcm_token=body.fcm_token,
    )

    # Subscribe to default topics
    topics = body.topic_subscriptions or ["all_citizens"]
    if current_user.role == UserRole.OFFICER:
        topics.append("officer_alerts")
    if current_user.role == UserRole.ADMIN:
        topics.append("admin_alerts")

    await fcm_gateway.subscribe_to_topic([body.fcm_token], ",".join(topics))

    return {"message": "Device token registered successfully."}


@router.delete(
    "/device-token/{device_id}",
    response_model=MessageResponse,
    summary="Deregister a device FCM token",
)
async def deregister_device_token(
    device_id:    str,
    current_user: CurrentUser,
):
    from app.core.redis_client import redis_client
    from app.repositories.auth_repository import AuthRepository

    auth_repo = AuthRepository(redis_client)

    # Get token before deleting (for FCM unsubscription)
    token = await auth_repo.get_fcm_token(str(current_user.id), device_id)
    if token:
        await fcm_gateway.unsubscribe_from_topic([token], "all_citizens")

    await auth_repo.delete_fcm_token(str(current_user.id), device_id)
    return {"message": "Device token removed."}
