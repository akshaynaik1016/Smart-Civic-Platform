"""
Test suite for the Notification Preferences module.

Tests:
  • NotificationPrefsRepository — Redis get/save/update/reset/delete
  • NotificationPrefsService    — wants_channel, quiet hours logic, is_in_quiet_hours
  • Preference update merging   — partial patches preserve unchanged fields

Run:
    pytest tests/test_notification_preferences.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.notification_preferences import (
    ChannelPrefs,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    NotificationPrefsRepository,
    NotificationPrefsService,
    QuietHoursPrefs,
)


# ─── Redis mock helpers ───────────────────────────────────────────────────────

def _make_redis(stored_json: str | None = None):
    """Return a mock Redis client, optionally pre-seeded with stored JSON."""
    r = MagicMock()
    raw = stored_json.encode() if stored_json else None
    r.get    = AsyncMock(return_value=raw)
    r.set    = AsyncMock(return_value=True)
    r.expire = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# Repository tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationPrefsRepository:

    @pytest.mark.asyncio
    async def test_get_returns_defaults_when_no_record(self):
        repo   = NotificationPrefsRepository(_make_redis(stored_json=None))
        prefs  = await repo.get("user_123")
        assert isinstance(prefs, NotificationPreferences)
        assert prefs.complaint_submitted.push is True
        assert prefs.complaint_submitted.email is True
        assert prefs.quiet_hours.enabled is False

    @pytest.mark.asyncio
    async def test_get_deserialises_stored_json(self):
        stored = NotificationPreferences(daily_digest=True)
        repo   = NotificationPrefsRepository(_make_redis(stored.model_dump_json()))
        prefs  = await repo.get("user_abc")
        assert prefs.daily_digest is True

    @pytest.mark.asyncio
    async def test_save_serialises_to_redis(self):
        redis = _make_redis()
        repo  = NotificationPrefsRepository(redis)
        prefs = NotificationPreferences(sla_alerts=False)
        await repo.save("user_xyz", prefs)
        redis.set.assert_called_once()
        call_args  = redis.set.call_args
        stored_raw = call_args[0][1]
        stored     = json.loads(stored_raw)
        assert stored["sla_alerts"] is False

    @pytest.mark.asyncio
    async def test_update_merges_partial_fields(self):
        original = NotificationPreferences(
            complaint_submitted=ChannelPrefs(push=True, email=True, in_app=True),
            daily_digest=False,
        )
        redis = _make_redis(original.model_dump_json())
        repo  = NotificationPrefsRepository(redis)

        patch = NotificationPreferencesUpdate(
            complaint_submitted=ChannelPrefs(push=False, email=True, in_app=True),
        )
        updated = await repo.update("user_1", patch)

        assert updated.complaint_submitted.push is False     # changed
        assert updated.complaint_submitted.email is True     # unchanged
        assert updated.daily_digest is False                 # other field untouched
        redis.set.assert_called_once()                       # persistence happened

    @pytest.mark.asyncio
    async def test_update_quiet_hours(self):
        original = NotificationPreferences()
        redis    = _make_redis(original.model_dump_json())
        repo     = NotificationPrefsRepository(redis)

        patch = NotificationPreferencesUpdate(
            quiet_hours=QuietHoursPrefs(enabled=True, start="23:00", end="06:00")
        )
        updated = await repo.update("user_2", patch)

        assert updated.quiet_hours.enabled is True
        assert updated.quiet_hours.start == "23:00"
        assert updated.quiet_hours.end   == "06:00"

    @pytest.mark.asyncio
    async def test_reset_saves_defaults(self):
        redis = _make_redis()
        repo  = NotificationPrefsRepository(redis)
        prefs = await repo.reset("user_3")

        assert isinstance(prefs, NotificationPreferences)
        assert prefs.complaint_submitted.push is True
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_removes_key(self):
        redis = _make_redis()
        repo  = NotificationPrefsRepository(redis)
        await repo.delete("user_4")
        redis.delete.assert_called_once_with("prefs:notif:user_4")

    @pytest.mark.asyncio
    async def test_get_refreshes_ttl_on_hit(self):
        prefs = NotificationPreferences()
        redis = _make_redis(prefs.model_dump_json())
        repo  = NotificationPrefsRepository(redis)
        await repo.get("user_5")
        redis.expire.assert_called_once_with("prefs:notif:user_5", 7 * 86_400)

    @pytest.mark.asyncio
    async def test_get_handles_corrupted_json_gracefully(self):
        redis = _make_redis(stored_json="{NOT VALID JSON:::}")
        repo  = NotificationPrefsRepository(redis)
        prefs = await repo.get("user_corrupt")
        # Should fall back to defaults silently
        assert isinstance(prefs, NotificationPreferences)


# ═══════════════════════════════════════════════════════════════════════════════
# Service tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationPrefsService:

    def _service(self, prefs: NotificationPreferences | None = None) -> NotificationPrefsService:
        stored = prefs.model_dump_json() if prefs else None
        svc    = NotificationPrefsService(_make_redis(stored))
        return svc

    # ── wants_channel ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_wants_push_defaults_to_true(self):
        svc    = self._service()
        result = await svc.wants_channel("u1", "complaint_submitted", "push")
        assert result is True

    @pytest.mark.asyncio
    async def test_wants_email_false_when_disabled(self):
        prefs = NotificationPreferences(
            complaint_status_changed=ChannelPrefs(push=True, email=False, in_app=True)
        )
        svc    = self._service(prefs)
        result = await svc.wants_channel("u2", "complaint_status_changed", "email")
        assert result is False

    @pytest.mark.asyncio
    async def test_wants_push_false_for_duplicate_by_default(self):
        svc    = self._service()   # uses platform defaults
        result = await svc.wants_channel("u3", "duplicate_detected", "push")
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_notification_type_defaults_to_true(self):
        svc    = self._service()
        result = await svc.wants_channel("u4", "some_future_type", "push")
        assert result is True

    @pytest.mark.asyncio
    async def test_in_app_always_true_by_default(self):
        svc = self._service()
        for ntype in [
            "complaint_submitted", "complaint_assigned",
            "complaint_resolved", "system_announcement",
        ]:
            assert await svc.wants_channel("u5", ntype, "in_app") is True

    # ── quiet hours ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_quiet_hours_disabled_by_default(self):
        svc = self._service()
        assert await svc.is_in_quiet_hours("u6") is False

    @pytest.mark.asyncio
    async def test_quiet_hours_same_day_window_inside(self):
        # 09:00–17:00 window; mock now = 12:00 UTC
        prefs = NotificationPreferences(
            quiet_hours=QuietHoursPrefs(enabled=True, start="09:00", end="17:00")
        )
        svc = self._service(prefs)
        with patch(
            "app.services.notification_preferences.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
            result = await svc.is_in_quiet_hours("u7")
        assert result is True

    @pytest.mark.asyncio
    async def test_quiet_hours_same_day_window_outside(self):
        prefs = NotificationPreferences(
            quiet_hours=QuietHoursPrefs(enabled=True, start="09:00", end="17:00")
        )
        svc = self._service(prefs)
        with patch(
            "app.services.notification_preferences.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 1, 20, 0, tzinfo=timezone.utc)
            result = await svc.is_in_quiet_hours("u8")
        assert result is False

    @pytest.mark.asyncio
    async def test_quiet_hours_overnight_window_at_23h(self):
        # 22:00–07:00 overnight; mock now = 23:00
        prefs = NotificationPreferences(
            quiet_hours=QuietHoursPrefs(enabled=True, start="22:00", end="07:00")
        )
        svc = self._service(prefs)
        with patch(
            "app.services.notification_preferences.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 1, 23, 0, tzinfo=timezone.utc)
            result = await svc.is_in_quiet_hours("u9")
        assert result is True

    @pytest.mark.asyncio
    async def test_quiet_hours_overnight_window_at_03h(self):
        # 22:00–07:00 overnight; mock now = 03:00
        prefs = NotificationPreferences(
            quiet_hours=QuietHoursPrefs(enabled=True, start="22:00", end="07:00")
        )
        svc = self._service(prefs)
        with patch(
            "app.services.notification_preferences.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 2, 3, 0, tzinfo=timezone.utc)
            result = await svc.is_in_quiet_hours("u10")
        assert result is True

    @pytest.mark.asyncio
    async def test_quiet_hours_overnight_window_at_noon(self):
        # 22:00–07:00 overnight; mock now = 12:00 → NOT in quiet hours
        prefs = NotificationPreferences(
            quiet_hours=QuietHoursPrefs(enabled=True, start="22:00", end="07:00")
        )
        svc = self._service(prefs)
        with patch(
            "app.services.notification_preferences.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 2, 12, 0, tzinfo=timezone.utc)
            result = await svc.is_in_quiet_hours("u11")
        assert result is False

    # ── digest / SLA toggles ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_daily_digest_off_by_default(self):
        svc = self._service()
        assert await svc.wants_daily_digest("u12") is False

    @pytest.mark.asyncio
    async def test_daily_digest_on_when_set(self):
        prefs = NotificationPreferences(daily_digest=True)
        svc   = self._service(prefs)
        assert await svc.wants_daily_digest("u13") is True

    @pytest.mark.asyncio
    async def test_sla_alerts_on_by_default(self):
        svc = self._service()
        assert await svc.wants_sla_alerts("u14") is True

    @pytest.mark.asyncio
    async def test_sla_alerts_off_when_set(self):
        prefs = NotificationPreferences(sla_alerts=False)
        svc   = self._service(prefs)
        assert await svc.wants_sla_alerts("u15") is False

    # ── update_preferences ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_preferences_partial(self):
        original = NotificationPreferences(daily_digest=False, sla_alerts=True)
        svc      = self._service(original)

        updated = await svc.update_preferences(
            "u16",
            NotificationPreferencesUpdate(daily_digest=True),
        )
        assert updated.daily_digest is True
        assert updated.sla_alerts is True   # untouched

    @pytest.mark.asyncio
    async def test_update_preferences_channel_prefs(self):
        original = NotificationPreferences()
        svc      = self._service(original)

        updated = await svc.update_preferences(
            "u17",
            NotificationPreferencesUpdate(
                complaint_resolved=ChannelPrefs(push=True, email=False, in_app=True)
            ),
        )
        assert updated.complaint_resolved.email is False
        assert updated.complaint_resolved.push  is True

    @pytest.mark.asyncio
    async def test_reset_to_defaults(self):
        prefs = NotificationPreferences(daily_digest=True, sla_alerts=False)
        svc   = self._service(prefs)

        reset = await svc.reset_to_defaults("u18")
        assert reset.daily_digest is False
        assert reset.sla_alerts   is True


# ═══════════════════════════════════════════════════════════════════════════════
# Schema validation tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreferenceSchemas:

    def test_default_preferences_are_valid(self):
        prefs = NotificationPreferences()
        assert prefs.complaint_submitted.push  is True
        assert prefs.quiet_hours.enabled       is False
        assert prefs.daily_digest              is False
        assert prefs.sla_alerts                is True

    def test_duplicate_detected_push_default_is_false(self):
        prefs = NotificationPreferences()
        assert prefs.duplicate_detected.push  is False
        assert prefs.duplicate_detected.email is False
        assert prefs.duplicate_detected.in_app is True

    def test_quiet_hours_time_pattern_validation(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QuietHoursPrefs(enabled=True, start="25:99", end="07:00")

    def test_channel_prefs_all_false_allowed(self):
        cp = ChannelPrefs(push=False, email=False, in_app=False)
        assert cp.push is False

    def test_partial_update_allows_none_fields(self):
        patch = NotificationPreferencesUpdate()
        dumped = patch.model_dump(exclude_none=True)
        assert dumped == {}

    def test_preferences_round_trips_json(self):
        original = NotificationPreferences(
            daily_digest=True,
            sla_alerts=False,
            quiet_hours=QuietHoursPrefs(enabled=True, start="21:30", end="08:00"),
        )
        serialised  = original.model_dump_json()
        deserialised = NotificationPreferences.model_validate_json(serialised)
        assert deserialised.daily_digest == original.daily_digest
        assert deserialised.quiet_hours.start == "21:30"
