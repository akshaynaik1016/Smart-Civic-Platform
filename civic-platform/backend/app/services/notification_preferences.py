"""
Notification Preferences
========================
Lets each user control which notification types they receive and over which channels.

Preferences are stored as a JSONB column on the user row (via Redis cache with DB fallback),
so there's no extra table needed. The schema is:

    {
        "complaint_submitted":      {"push": true,  "email": true,  "in_app": true},
        "complaint_assigned":       {"push": true,  "email": true,  "in_app": true},
        "complaint_status_changed": {"push": true,  "email": false, "in_app": true},
        "complaint_resolved":       {"push": true,  "email": true,  "in_app": true},
        "verification_required":    {"push": true,  "email": false, "in_app": true},
        "duplicate_detected":       {"push": false, "email": false, "in_app": true},
        "system_announcement":      {"push": true,  "email": false, "in_app": true},
        "quiet_hours":              {"enabled": false, "start": "22:00", "end": "07:00"},
        "daily_digest":             {"enabled": false},
        "sla_alerts":               {"enabled": true}
    }

Redis key: prefs:notif:{user_id}   TTL: 7 days (refreshed on read/write)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_REDIS_TTL    = 7 * 86_400           # 7 days
_REDIS_PREFIX = "prefs:notif"


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ChannelPrefs(BaseModel):
    push:   bool = True
    email:  bool = True
    in_app: bool = True


class QuietHoursPrefs(BaseModel):
    enabled: bool = False
    start:   str  = Field(default="22:00", pattern=r"^\d{2}:\d{2}$")
    end:     str  = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")


class NotificationPreferences(BaseModel):
    """Full preference document stored per user."""
    complaint_submitted:      ChannelPrefs = Field(default_factory=ChannelPrefs)
    complaint_assigned:       ChannelPrefs = Field(default_factory=ChannelPrefs)
    complaint_status_changed: ChannelPrefs = Field(default_factory=lambda: ChannelPrefs(email=False))
    complaint_resolved:       ChannelPrefs = Field(default_factory=ChannelPrefs)
    verification_required:    ChannelPrefs = Field(default_factory=lambda: ChannelPrefs(email=False))
    duplicate_detected:       ChannelPrefs = Field(default_factory=lambda: ChannelPrefs(push=False, email=False))
    system_announcement:      ChannelPrefs = Field(default_factory=lambda: ChannelPrefs(email=False))
    quiet_hours:              QuietHoursPrefs = Field(default_factory=QuietHoursPrefs)
    daily_digest:             bool = False
    sla_alerts:               bool = True


class NotificationPreferencesUpdate(BaseModel):
    """Partial update — all fields optional."""
    complaint_submitted:      Optional[ChannelPrefs] = None
    complaint_assigned:       Optional[ChannelPrefs] = None
    complaint_status_changed: Optional[ChannelPrefs] = None
    complaint_resolved:       Optional[ChannelPrefs] = None
    verification_required:    Optional[ChannelPrefs] = None
    duplicate_detected:       Optional[ChannelPrefs] = None
    system_announcement:      Optional[ChannelPrefs] = None
    quiet_hours:              Optional[QuietHoursPrefs] = None
    daily_digest:             Optional[bool] = None
    sla_alerts:               Optional[bool] = None


# ─── Repository ───────────────────────────────────────────────────────────────

class NotificationPrefsRepository:
    """
    Redis-backed preference store.
    Falls back to the default NotificationPreferences() when no record exists.
    """

    def __init__(self, redis) -> None:
        self._r = redis

    def _key(self, user_id: str) -> str:
        return f"{_REDIS_PREFIX}:{user_id}"

    async def get(self, user_id: str) -> NotificationPreferences:
        """Return preferences, loading defaults when not set."""
        try:
            raw = await self._r.get(self._key(user_id))
            if not raw:
                return NotificationPreferences()
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            prefs = NotificationPreferences(**data)
            # Refresh TTL on read (sliding expiry)
            await self._r.expire(self._key(user_id), _REDIS_TTL)
            return prefs
        except Exception as exc:
            logger.warning("NotificationPrefsRepository.get failed for %s: %s", user_id, exc)
            return NotificationPreferences()

    async def save(self, user_id: str, prefs: NotificationPreferences) -> None:
        """Persist the full preference document."""
        try:
            await self._r.set(
                self._key(user_id),
                prefs.model_dump_json(),
                ex=_REDIS_TTL,
            )
        except Exception as exc:
            logger.warning("NotificationPrefsRepository.save failed for %s: %s", user_id, exc)

    async def update(
        self,
        user_id: str,
        patch: NotificationPreferencesUpdate,
    ) -> NotificationPreferences:
        """
        Apply a partial update, preserving unchanged fields.
        Returns the merged result.
        """
        current = await self.get(user_id)
        updates = patch.model_dump(exclude_none=True)

        for field, value in updates.items():
            if isinstance(value, dict):
                current_val = getattr(current, field)
                if isinstance(current_val, (ChannelPrefs, QuietHoursPrefs)):
                    merged = current_val.model_copy(update=value)
                    setattr(current, field, merged)
                else:
                    setattr(current, field, value)
            else:
                setattr(current, field, value)

        await self.save(user_id, current)
        return current

    async def reset(self, user_id: str) -> NotificationPreferences:
        """Reset to defaults."""
        defaults = NotificationPreferences()
        await self.save(user_id, defaults)
        return defaults

    async def delete(self, user_id: str) -> None:
        """Remove preferences (e.g. when user account is deleted)."""
        try:
            await self._r.delete(self._key(user_id))
        except Exception:
            pass


# ─── Service ──────────────────────────────────────────────────────────────────

class NotificationPrefsService:
    """
    Business logic wrapper around NotificationPrefsRepository.

    Also exposes helper methods used by NotificationService to check whether
    a user wants to receive a given type/channel combination.
    """

    def __init__(self, redis) -> None:
        self._repo = NotificationPrefsRepository(redis)

    async def get_preferences(self, user_id: str) -> NotificationPreferences:
        return await self._repo.get(user_id)

    async def update_preferences(
        self,
        user_id: str,
        patch: NotificationPreferencesUpdate,
    ) -> NotificationPreferences:
        return await self._repo.update(user_id, patch)

    async def reset_to_defaults(self, user_id: str) -> NotificationPreferences:
        return await self._repo.reset(user_id)

    async def wants_channel(
        self,
        user_id: str,
        notification_type: str,
        channel: str,
    ) -> bool:
        """
        Returns True if the user has opted-in to the given type + channel.

        Usage:
            if await prefs_svc.wants_channel(uid, "complaint_resolved", "email"):
                await email_svc.send(...)
        """
        prefs = await self._repo.get(user_id)

        # Map notification_type string → preference field
        type_map = {
            "complaint_submitted":      prefs.complaint_submitted,
            "complaint_assigned":       prefs.complaint_assigned,
            "complaint_status_changed": prefs.complaint_status_changed,
            "complaint_resolved":       prefs.complaint_resolved,
            "verification_required":    prefs.verification_required,
            "duplicate_detected":       prefs.duplicate_detected,
            "system_announcement":      prefs.system_announcement,
        }

        type_prefs = type_map.get(notification_type)
        if type_prefs is None:
            return True   # unknown type → allow by default

        if not isinstance(type_prefs, ChannelPrefs):
            return bool(type_prefs)

        channel_map = {
            "push":   type_prefs.push,
            "email":  type_prefs.email,
            "in_app": type_prefs.in_app,
        }
        return channel_map.get(channel, True)

    async def is_in_quiet_hours(self, user_id: str) -> bool:
        """
        Returns True if the current time falls within the user's quiet hours.
        Push notifications should be suppressed during quiet hours.
        """
        prefs = await self._repo.get(user_id)
        qh = prefs.quiet_hours
        if not qh.enabled:
            return False

        now_time = datetime.now(timezone.utc).strftime("%H:%M")

        def _to_minutes(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        now_m   = _to_minutes(now_time)
        start_m = _to_minutes(qh.start)
        end_m   = _to_minutes(qh.end)

        if start_m <= end_m:
            # Same-day window e.g. 09:00–17:00
            return start_m <= now_m <= end_m
        else:
            # Overnight window e.g. 22:00–07:00
            return now_m >= start_m or now_m <= end_m

    async def wants_daily_digest(self, user_id: str) -> bool:
        prefs = await self._repo.get(user_id)
        return prefs.daily_digest

    async def wants_sla_alerts(self, user_id: str) -> bool:
        prefs = await self._repo.get(user_id)
        return prefs.sla_alerts
