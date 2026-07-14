"""
Notification Preferences API
=============================
Endpoints for reading and updating per-user notification preferences.

GET    /notifications/preferences          — read current user's preferences
PUT    /notifications/preferences          — replace (full update)
PATCH  /notifications/preferences          — partial update
DELETE /notifications/preferences          — reset to platform defaults
POST   /notifications/preferences/test     — send a test notification to verify settings
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from app.api.v1.dependencies.auth import CurrentUser
from app.core.exceptions import NotFoundError
from app.schemas.schemas import MessageResponse
from app.services.notification_preferences import (
    NotificationPreferences,
    NotificationPreferencesUpdate,
    NotificationPrefsService,
)

router = APIRouter(
    prefix="/notifications/preferences",
    tags=["Notification Preferences"],
)


# ── Dependency ────────────────────────────────────────────────────────────────

async def _get_prefs_service() -> NotificationPrefsService:
    from app.core.redis_client import redis_client
    return NotificationPrefsService(redis_client)


PrefsSvcDep = Annotated[NotificationPrefsService, Depends(_get_prefs_service)]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=NotificationPreferences,
    summary="Get notification preferences for the current user",
)
async def get_preferences(
    current_user: CurrentUser,
    service:      PrefsSvcDep,
) -> NotificationPreferences:
    """
    Returns the user's current notification preference document.
    If no preferences have been saved, platform defaults are returned.
    """
    return await service.get_preferences(str(current_user.id))


@router.put(
    "",
    response_model=NotificationPreferences,
    summary="Replace notification preferences (full update)",
)
async def replace_preferences(
    current_user: CurrentUser,
    service:      PrefsSvcDep,
    body:         NotificationPreferences = Body(...),
) -> NotificationPreferences:
    """
    Completely replaces the user's notification preferences.
    All fields are required (use PATCH for partial updates).
    """
    await service._repo.save(str(current_user.id), body)
    return body


@router.patch(
    "",
    response_model=NotificationPreferences,
    summary="Partially update notification preferences",
)
async def patch_preferences(
    current_user: CurrentUser,
    service:      PrefsSvcDep,
    body:         NotificationPreferencesUpdate = Body(...),
) -> NotificationPreferences:
    """
    Applies a partial update — only the fields you supply are changed.

    Example — disable email for status changes only:
    ```json
    {"complaint_status_changed": {"push": true, "email": false, "in_app": true}}
    ```

    Example — enable quiet hours from 22:00 to 07:00:
    ```json
    {"quiet_hours": {"enabled": true, "start": "22:00", "end": "07:00"}}
    ```
    """
    return await service.update_preferences(str(current_user.id), body)


@router.delete(
    "",
    response_model=MessageResponse,
    summary="Reset notification preferences to platform defaults",
)
async def reset_preferences(
    current_user: CurrentUser,
    service:      PrefsSvcDep,
) -> dict:
    """
    Deletes the user's custom preferences and restores platform defaults.
    """
    await service.reset_to_defaults(str(current_user.id))
    return {"message": "Notification preferences reset to defaults."}


@router.post(
    "/test",
    response_model=MessageResponse,
    summary="Send a test notification to verify current settings",
)
async def send_test_notification(
    current_user: CurrentUser,
    service:      PrefsSvcDep,
) -> dict:
    """
    Fires a test in-app + push notification to the current user so they can
    verify their preferences are working correctly.
    """
    from app.core.database import AsyncSessionLocal
    from app.repositories.notification_repository import NotificationRepository
    from app.services.fcm_gateway import fcm_gateway
    from app.services.email_service import EmailService
    from app.services.notification_service import NotificationService
    from app.models.models import NotificationChannel, NotificationType

    in_quiet = await service.is_in_quiet_hours(str(current_user.id))
    wants_push = await service.wants_channel(
        str(current_user.id), "system_announcement", "push"
    )

    async with AsyncSessionLocal() as db:
        notif_svc = NotificationService(
            db=db,
            repo=NotificationRepository(db),
            email=EmailService(),
            fcm=fcm_gateway,
        )
        channels = [NotificationChannel.IN_APP]
        if wants_push and not in_quiet:
            channels.append(NotificationChannel.PUSH)

        await notif_svc.send(
            recipient=current_user,
            ntype=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Test Notification 🔔",
            body="Your Smart Civic notification settings are working correctly.",
            data={"type": "test", "screen": "notifications"},
            channels=channels,
        )
        await db.commit()

    msg = "Test notification sent."
    if in_quiet:
        msg += " (Push suppressed — quiet hours active.)"
    elif not wants_push:
        msg += " (Push disabled in your preferences.)"

    return {"message": msg}
