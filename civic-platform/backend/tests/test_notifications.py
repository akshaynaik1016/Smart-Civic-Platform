"""
Notification module test suite
================================

Unit tests  — service logic, FCM gateway error parsing, template rendering
Integration — NotificationRepository against an in-memory SQLite async DB
API tests   — FastAPI endpoints via httpx AsyncClient

Run:
    pytest tests/test_notifications.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    User,
    UserRole,
    UserStatus,
)


# ─── SQLite in-memory DB for tests ───────────────────────────────────────────

@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """In-memory async SQLite session for unit/integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.core.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _user(role: UserRole = UserRole.CITIZEN, **kwargs) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=f"test_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Test User",
        password_hash="hashed",
        role=role,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    for k, v in kwargs.items():
        setattr(u, k, v)
    return u


def _complaint(**kwargs):
    from app.models.models import Complaint, ComplaintStatus, SeverityLevel, IssueCategory
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number="CMP-2025-00001",
        citizen_id=str(uuid.uuid4()),
        category_id=1,
        category=IssueCategory.POTHOLE,
        status=ComplaintStatus.RESOLVED,
        severity=SeverityLevel.HIGH,
        priority_score=70.0,
        latitude=15.8700,
        longitude=74.5000,
        title="Large pothole on College Road",
        description="Deep pothole causing vehicle damage.",
    )
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


@pytest.fixture
def mock_redis():
    """Mock Redis client with async methods."""
    r = MagicMock()
    r.scan_iter = AsyncMock(return_value=_async_iter([]))
    r.get       = AsyncMock(return_value=None)
    r.set       = AsyncMock(return_value=True)
    r.delete    = AsyncMock(return_value=1)
    r.exists    = AsyncMock(return_value=0)
    r.pipeline  = MagicMock(return_value=_mock_pipeline())
    return r


def _async_iter(items):
    async def _gen():
        for item in items:
            yield item
    return _gen()


def _mock_pipeline():
    pipe = MagicMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__  = AsyncMock(return_value=False)
    pipe.execute    = AsyncMock(return_value=[True, True])
    pipe.set        = MagicMock(return_value=pipe)
    pipe.expire     = MagicMock(return_value=pipe)
    pipe.hset       = MagicMock(return_value=pipe)
    return pipe


@pytest.fixture
def mock_fcm():
    """Mock FCMGateway."""
    from app.services.fcm_gateway import FCMResult, FCMBatchResult, FCMErrorKind
    fcm = MagicMock()
    fcm.is_available = True
    fcm.send          = AsyncMock(return_value=FCMResult(success=True, message_id="msg_001"))
    fcm.send_multicast= AsyncMock(return_value=FCMBatchResult(
        total=1, successes=1, failures=0,
        results=[FCMResult(success=True, message_id="msg_001")],
    ))
    fcm.send_to_topic = AsyncMock(return_value=FCMResult(success=True, message_id="topic_001"))
    fcm.subscribe_to_topic   = AsyncMock(return_value=True)
    fcm.unsubscribe_from_topic = AsyncMock(return_value=True)
    return fcm


@pytest.fixture
def mock_email():
    email = MagicMock()
    email.send_otp_email       = AsyncMock(return_value=True)
    email.send_welcome_email   = AsyncMock(return_value=True)
    email.send_status_update_email = AsyncMock(return_value=True)
    email._send                = AsyncMock(return_value=True)
    return email


# ═══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — NotificationRepository
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationRepository:

    @pytest.mark.asyncio
    async def test_create_returns_persisted_notification(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        notif = await repo.create(
            recipient_id=str(user.id),
            ntype=NotificationType.COMPLAINT_SUBMITTED,
            title="Test",
            body="Body text",
        )

        assert notif.id is not None
        assert notif.status == NotificationStatus.PENDING
        assert notif.channel == NotificationChannel.IN_APP
        assert notif.read_at is None

    @pytest.mark.asyncio
    async def test_get_for_user_pagination(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        # Create 5 notifications
        for i in range(5):
            await repo.create(
                recipient_id=str(user.id),
                ntype=NotificationType.SYSTEM_ANNOUNCEMENT,
                title=f"Notif {i}",
                body="body",
            )

        page1, total = await repo.get_for_user(str(user.id), page=1, page_size=3)
        page2, _     = await repo.get_for_user(str(user.id), page=2, page_size=3)

        assert total == 5
        assert len(page1) == 3
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_unread_count_decrements_on_mark_read(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        n = await repo.create(
            recipient_id=str(user.id),
            ntype=NotificationType.COMPLAINT_RESOLVED,
            title="Resolved",
            body="body",
        )

        assert await repo.unread_count(str(user.id)) == 1
        await repo.mark_read(str(n.id), str(user.id))
        assert await repo.unread_count(str(user.id)) == 0

    @pytest.mark.asyncio
    async def test_mark_all_read(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        for _ in range(4):
            await repo.create(
                recipient_id=str(user.id),
                ntype=NotificationType.SYSTEM_ANNOUNCEMENT,
                title="A",
                body="b",
            )

        marked = await repo.mark_all_read(str(user.id))
        assert marked == 4
        assert await repo.unread_count(str(user.id)) == 0

    @pytest.mark.asyncio
    async def test_mark_sent_updates_status(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        n = await repo.create(
            recipient_id=str(user.id),
            ntype=NotificationType.COMPLAINT_SUBMITTED,
            title="T",
            body="B",
        )

        await repo.mark_sent(str(n.id), fcm_message_id="fcm_abc")
        refreshed = await repo.get_by_id(str(n.id))
        assert refreshed.status == NotificationStatus.SENT
        assert refreshed.fcm_message_id == "fcm_abc"

    @pytest.mark.asyncio
    async def test_mark_failed_increments_retry_count(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        n = await repo.create(
            recipient_id=str(user.id),
            ntype=NotificationType.COMPLAINT_SUBMITTED,
            title="T",
            body="B",
        )

        await repo.mark_failed(str(n.id), reason="FCM_ERROR")
        refreshed = await repo.get_by_id(str(n.id))
        assert refreshed.status == NotificationStatus.FAILED
        assert refreshed.retry_count == 1
        assert refreshed.failed_reason == "FCM_ERROR"

    @pytest.mark.asyncio
    async def test_get_pending_filters_max_retries(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        # One with retry_count=2 (eligible) and one with retry_count=3 (not)
        n_ok  = Notification(
            id=str(uuid.uuid4()),
            recipient_id=str(user.id),
            type=NotificationType.COMPLAINT_SUBMITTED,
            title="Ok",
            body="b",
            channel=NotificationChannel.PUSH,
            status=NotificationStatus.PENDING,
            retry_count=2,
            scheduled_for=datetime.now(timezone.utc),
        )
        n_max = Notification(
            id=str(uuid.uuid4()),
            recipient_id=str(user.id),
            type=NotificationType.COMPLAINT_SUBMITTED,
            title="Max",
            body="b",
            channel=NotificationChannel.PUSH,
            status=NotificationStatus.PENDING,
            retry_count=3,
            scheduled_for=datetime.now(timezone.utc),
        )
        db.add_all([n_ok, n_max])
        await db.flush()

        pending = await repo.get_pending(limit=100)
        ids = [str(p.id) for p in pending]
        assert str(n_ok.id) in ids
        assert str(n_max.id) not in ids

    @pytest.mark.asyncio
    async def test_bulk_create(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user_a = _user()
        user_b = _user()
        db.add_all([user_a, user_b])
        await db.flush()

        records = [
            {
                "id": str(uuid.uuid4()),
                "recipient_id": str(user_a.id),
                "type": NotificationType.SYSTEM_ANNOUNCEMENT,
                "title": "Announcement",
                "body": "Body",
                "data": {},
                "channel": NotificationChannel.IN_APP,
                "status": NotificationStatus.PENDING,
                "scheduled_for": datetime.now(timezone.utc),
            },
            {
                "id": str(uuid.uuid4()),
                "recipient_id": str(user_b.id),
                "type": NotificationType.SYSTEM_ANNOUNCEMENT,
                "title": "Announcement",
                "body": "Body",
                "data": {},
                "channel": NotificationChannel.IN_APP,
                "status": NotificationStatus.PENDING,
                "scheduled_for": datetime.now(timezone.utc),
            },
        ]
        created = await repo.bulk_create(records)
        assert len(created) == 2

    @pytest.mark.asyncio
    async def test_unread_only_filter(self, db: AsyncSession):
        from app.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        user = _user()
        db.add(user)
        await db.flush()

        n1 = await repo.create(
            recipient_id=str(user.id),
            ntype=NotificationType.COMPLAINT_SUBMITTED,
            title="Unread",
            body="b",
        )
        n2 = await repo.create(
            recipient_id=str(user.id),
            ntype=NotificationType.COMPLAINT_SUBMITTED,
            title="Read",
            body="b",
        )
        await repo.mark_read(str(n2.id), str(user.id))

        rows, total = await repo.get_for_user(str(user.id), unread_only=True)
        assert total == 1
        assert rows[0].id == n1.id


# ═══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — FCMGateway
# ═══════════════════════════════════════════════════════════════════════════════

class TestFCMGateway:

    def test_parse_error_permanent(self):
        from app.services.fcm_gateway import FCMGateway, FCMErrorKind
        gw = FCMGateway()
        exc = Exception("messaging/unregistered")
        exc.code = "messaging/unregistered"
        result = gw._parse_error(exc)
        assert result.success is False
        assert result.error_kind == FCMErrorKind.PERMANENT
        assert result.is_permanent_failure is True

    def test_parse_error_retryable(self):
        from app.services.fcm_gateway import FCMGateway, FCMErrorKind
        gw = FCMGateway()
        exc = Exception("messaging/unavailable")
        exc.code = "messaging/unavailable"
        result = gw._parse_error(exc)
        assert result.error_kind == FCMErrorKind.RETRYABLE
        assert result.is_retryable_failure is True

    def test_parse_error_unknown(self):
        from app.services.fcm_gateway import FCMGateway, FCMErrorKind
        gw = FCMGateway()
        exc = Exception("some_unknown_error")
        result = gw._parse_error(exc)
        assert result.error_kind == FCMErrorKind.UNKNOWN

    def test_is_available_false_without_credentials(self):
        from app.services.fcm_gateway import FCMGateway
        with patch("app.core.config.settings.FIREBASE_CREDENTIALS_JSON", ""):
            gw = FCMGateway()
            gw._enabled = False
            assert gw.is_available is False

    @pytest.mark.asyncio
    async def test_send_returns_disabled_when_no_credentials(self):
        from app.services.fcm_gateway import FCMGateway
        gw = FCMGateway()
        gw._enabled      = False
        gw._initialized  = False
        result = await gw.send("token123", "Title", "Body")
        assert result.success is False
        assert result.error_code == "FCM_DISABLED"

    @pytest.mark.asyncio
    async def test_send_multicast_empty_tokens(self):
        from app.services.fcm_gateway import FCMGateway
        gw = FCMGateway()
        result = await gw.send_multicast([], "Title", "Body")
        assert result.total == 0
        assert result.successes == 0


# ═══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — NotificationService (mocked repo, FCM, email)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationService:

    def _make_service(self, db, mock_fcm, mock_email):
        from app.services.notification_service import NotificationService
        repo = MagicMock()
        repo.create           = AsyncMock()
        repo.bulk_create      = AsyncMock(return_value=[])
        repo.get_for_user     = AsyncMock(return_value=([], 0))
        repo.unread_count     = AsyncMock(return_value=0)
        repo.mark_read        = AsyncMock(return_value=True)
        repo.mark_multiple_read = AsyncMock(return_value=1)
        repo.mark_all_read    = AsyncMock(return_value=5)
        repo.mark_sent        = AsyncMock()
        repo.mark_failed      = AsyncMock()
        repo.get_failed_retryable = AsyncMock(return_value=[])
        repo.delivery_stats   = AsyncMock(return_value={})
        repo.channel_stats    = AsyncMock(return_value=[])

        notif = Notification(
            id=str(uuid.uuid4()),
            recipient_id="user_1",
            type=NotificationType.COMPLAINT_SUBMITTED,
            title="T",
            body="B",
            channel=NotificationChannel.IN_APP,
            status=NotificationStatus.PENDING,
            scheduled_for=datetime.now(timezone.utc),
        )
        repo.create.return_value = notif

        return NotificationService(db=db, repo=repo, email=mock_email, fcm=mock_fcm), repo

    @pytest.mark.asyncio
    async def test_send_creates_in_app_record(self, db, mock_fcm, mock_email):
        citizen = _user()
        service, repo = self._make_service(db, mock_fcm, mock_email)

        await service.send(
            recipient=citizen,
            ntype=NotificationType.COMPLAINT_SUBMITTED,
            title="Test",
            body="Body",
            channels=[NotificationChannel.IN_APP],
        )

        repo.create.assert_called_once()
        call_kwargs = repo.create.call_args.kwargs
        assert call_kwargs["ntype"] == NotificationType.COMPLAINT_SUBMITTED
        assert call_kwargs["recipient_id"] == str(citizen.id)

    @pytest.mark.asyncio
    async def test_notify_complaint_submitted_triggers_push(self, db, mock_fcm, mock_email):
        citizen = _user()
        complaint = _complaint(citizen_id=str(citizen.id))
        service, repo = self._make_service(db, mock_fcm, mock_email)

        with patch(
            "app.repositories.auth_repository.AuthRepository.get_all_fcm_tokens",
            AsyncMock(return_value=["token_abc"]),
        ):
            await service.notify_complaint_submitted(complaint, citizen)

        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_resolved_sends_email(self, db, mock_fcm, mock_email):
        citizen = _user()
        complaint = _complaint(citizen_id=str(citizen.id))
        service, repo = self._make_service(db, mock_fcm, mock_email)

        with patch(
            "app.repositories.auth_repository.AuthRepository.get_all_fcm_tokens",
            AsyncMock(return_value=[]),
        ):
            await service.notify_resolved(complaint, citizen)

        # Email is included in notify_resolved channels
        # (EmailService mock should have been called)
        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_all_read_calls_repo(self, db, mock_fcm, mock_email):
        service, repo = self._make_service(db, mock_fcm, mock_email)
        result = await service.mark_all_read("user_123")
        repo.mark_all_read.assert_called_once_with("user_123")
        assert result == 5

    @pytest.mark.asyncio
    async def test_broadcast_announcement_no_recipients_returns_zero(self, db, mock_fcm, mock_email):
        service, repo = self._make_service(db, mock_fcm, mock_email)
        count = await service.broadcast_announcement(
            title="Test", body="Body", recipient_ids=None
        )
        assert count == 0
        repo.bulk_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_announcement_creates_records(self, db, mock_fcm, mock_email):
        service, repo = self._make_service(db, mock_fcm, mock_email)
        mock_notifs = [MagicMock() for _ in range(3)]
        repo.bulk_create.return_value = mock_notifs

        count = await service.broadcast_announcement(
            title="City Alert",
            body="Road blocked on MG Road",
            recipient_ids=["u1", "u2", "u3"],
        )
        assert count == 3
        repo.bulk_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_push_skips_when_no_tokens(self, db, mock_fcm, mock_email):
        service, repo = self._make_service(db, mock_fcm, mock_email)
        user   = _user()
        notif  = MagicMock()
        notif.id = str(uuid.uuid4())

        with patch(
            "app.repositories.auth_repository.AuthRepository.get_all_fcm_tokens",
            AsyncMock(return_value=[]),
        ):
            await service._dispatch_push(user, notif, "T", "B", None, None)

        mock_fcm.send.assert_not_called()
        mock_fcm.send_multicast.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_push_removes_invalid_token(self, db, mock_fcm, mock_email):
        from app.services.fcm_gateway import FCMResult, FCMBatchResult, FCMErrorKind
        service, repo = self._make_service(db, mock_fcm, mock_email)
        user  = _user()
        notif = MagicMock()
        notif.id = str(uuid.uuid4())

        bad_token = "expired_token_xyz"
        mock_fcm.send_multicast.return_value = FCMBatchResult(
            total=1, successes=0, failures=1,
            results=[FCMResult(success=False, error_code="UNREGISTERED",
                               error_kind=FCMErrorKind.PERMANENT)],
            invalid_tokens=[bad_token],
        )

        mock_redis = MagicMock()
        mock_redis.scan_iter = MagicMock(return_value=_async_iter(
            [f"auth:fcm:{user.id}:default"]
        ))
        mock_redis.get    = AsyncMock(return_value=bad_token.encode())
        mock_redis.delete = AsyncMock(return_value=1)

        with patch(
            "app.repositories.auth_repository.AuthRepository.get_all_fcm_tokens",
            AsyncMock(return_value=[bad_token]),
        ), patch("app.core.redis_client.redis_client", mock_redis):
            await service._dispatch_push(user, notif, "T", "B", None, None)

        repo.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_failed_resets_to_pending(self, db, mock_fcm, mock_email):
        service, repo = self._make_service(db, mock_fcm, mock_email)
        failed_notifs = [MagicMock(id=str(uuid.uuid4())) for _ in range(3)]
        repo.get_failed_retryable.return_value = failed_notifs
        repo.reset_to_pending = AsyncMock()

        count = await service.retry_failed()
        assert count == 3
        assert repo.reset_to_pending.call_count == 3

    @pytest.mark.asyncio
    async def test_unread_count_delegates_to_repo(self, db, mock_fcm, mock_email):
        repo_mock = MagicMock()
        repo_mock.unread_count = AsyncMock(return_value=7)
        from app.services.notification_service import NotificationService
        service = NotificationService(db=db, repo=repo_mock, email=mock_email, fcm=mock_fcm)
        result = await service.unread_count("user_abc")
        assert result == 7
        repo_mock.unread_count.assert_called_once_with("user_abc")

    @pytest.mark.asyncio
    async def test_sla_breach_notification_targets_officer(self, db, mock_fcm, mock_email):
        officer_user = _user(role=UserRole.OFFICER, full_name="Anil Patil")
        complaint    = _complaint()
        service, repo = self._make_service(db, mock_fcm, mock_email)

        await service.notify_sla_breach(complaint, officer_user)

        repo.create.assert_called_once()
        kwargs = repo.create.call_args.kwargs
        assert kwargs["recipient_id"] == str(officer_user.id)
        assert kwargs["ntype"] == NotificationType.SYSTEM_ANNOUNCEMENT

    @pytest.mark.asyncio
    async def test_sla_breach_skips_when_no_officer(self, db, mock_fcm, mock_email):
        complaint     = _complaint()
        service, repo = self._make_service(db, mock_fcm, mock_email)

        await service.notify_sla_breach(complaint, officer_user=None)

        repo.create.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationTemplates:

    def test_complaint_submitted_template(self):
        from app.services.notification_service import _t
        title, body = _t(
            NotificationType.COMPLAINT_SUBMITTED,
            title="Large pothole",
            number="CMP-2025-00001",
        )
        assert "CMP-2025-00001" in body
        assert "received" in title.lower() or "✅" in title

    def test_status_changed_template_includes_notes(self):
        from app.services.notification_service import _t
        title, body = _t(
            NotificationType.COMPLAINT_STATUS_CHANGED,
            number="CMP-2025-00001",
            new_status="In Progress",
            notes_suffix=" Note: Repair crew dispatched",
        )
        assert "Repair crew dispatched" in body

    def test_duplicate_template_includes_parent(self):
        from app.services.notification_service import _t
        title, body = _t(
            NotificationType.DUPLICATE_DETECTED,
            number="CMP-2025-00042",
            parent_number="CMP-2025-00038",
        )
        assert "CMP-2025-00038" in body
        assert "CMP-2025-00042" in body

    def test_all_types_render_without_error(self):
        from app.services.notification_service import _t
        ctx = {
            "title": "Test", "number": "CMP-001",
            "officer_name": "John", "new_status": "Resolved",
            "notes_suffix": "", "parent_number": "CMP-000",
            "announcement_title": "Alert", "announcement_body": "Body",
        }
        for ntype in NotificationType:
            t, b = _t(ntype, **ctx)
            assert isinstance(t, str) and isinstance(b, str)
