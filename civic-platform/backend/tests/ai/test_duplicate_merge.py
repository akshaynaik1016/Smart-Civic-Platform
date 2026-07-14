"""
Test suite for the duplicate merge workflow.

Covers DuplicateMergeService: auto_merge, confirm_merge, reject_duplicate_flag,
unmerge, and the pending review queue — using mocked repository/notifier/audit
dependencies so no real DB or Redis is required.

Run:
    pytest tests/ai/test_duplicate_merge.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.ai.pipelines.duplicate_merge_service import DuplicateMergeService
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.models.models import ComplaintStatus, UserRole


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _complaint(
    id="child-1", complaint_number="CMP-2025-00010",
    status=ComplaintStatus.SUBMITTED, citizen_id="citizen-1",
    is_duplicate=False, parent_complaint_id=None,
):
    return SimpleNamespace(
        id=id, complaint_number=complaint_number, status=status,
        citizen_id=citizen_id, is_duplicate=is_duplicate,
        parent_complaint_id=parent_complaint_id, supporters=[],
    )


def _user(id="officer-1", role=UserRole.OFFICER, full_name="Officer Anil", email="anil@civic.gov"):
    return SimpleNamespace(id=id, role=role, full_name=full_name, email=email)


def _make_repo(**overrides):
    repo = MagicMock()
    repo.get_by_id            = AsyncMock(side_effect=overrides.get("get_by_id"))
    repo.is_supporter         = AsyncMock(return_value=False)
    repo.add_supporter        = AsyncMock(return_value=True)
    repo.remove_supporter     = AsyncMock(return_value=True)
    repo.update_fields        = AsyncMock(
        side_effect=lambda cid, **kw: _complaint(
            id=cid, **{k: v for k, v in kw.items() if k in ("status", "is_duplicate", "parent_complaint_id")}
        )
    )
    repo.update_status        = AsyncMock(side_effect=lambda cid, status, **kw: _complaint(id=cid, status=status))
    repo.add_status_history   = AsyncMock(return_value=None)
    repo.recalculate_priority = AsyncMock(return_value=50.0)
    for k, v in overrides.items():
        if k != "get_by_id":
            setattr(repo, k, v)
    return repo


def _make_notifier():
    n = MagicMock()
    n.notify_duplicate_detected = AsyncMock(return_value=None)
    return n


def _make_audit():
    a = MagicMock()
    a.log_update = AsyncMock(return_value=None)
    return a


def _service(repo=None, notifier=None, audit=None):
    return DuplicateMergeService(
        db=MagicMock(),
        repo=repo or _make_repo(),
        notifier=notifier or _make_notifier(),
        audit=audit or _make_audit(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# auto_merge
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoMerge:

    @pytest.mark.asyncio
    async def test_auto_merge_closes_child_and_links_parent(self):
        child  = _complaint(id="child-1", status=ComplaintStatus.SUBMITTED)
        parent = _complaint(id="parent-1", complaint_number="CMP-2025-00001")

        async def get_by_id(cid, detail=False, **kw):
            return parent if cid == "parent-1" else None

        repo = _make_repo(get_by_id=get_by_id)
        notifier = _make_notifier()
        svc = _service(repo=repo, notifier=notifier)

        await svc.auto_merge(child_complaint=child, parent_complaint_id="parent-1", similarity_score=0.93)

        repo.update_fields.assert_called_once()
        call = repo.update_fields.call_args
        assert call[0][0] == "child-1"
        assert call[1]["is_duplicate"] is True
        assert call[1]["parent_complaint_id"] == "parent-1"
        assert call[1]["status"] == ComplaintStatus.CLOSED
        assert call[1]["closed_reason"] == "duplicate"

    @pytest.mark.asyncio
    async def test_auto_merge_transfers_support_to_parent(self):
        child  = _complaint(id="child-1", citizen_id="citizen-A")
        parent = _complaint(id="parent-1", citizen_id="citizen-B")

        repo = _make_repo(get_by_id=lambda cid, **kw: parent if cid == "parent-1" else None)
        svc = _service(repo=repo)

        await svc.auto_merge(child_complaint=child, parent_complaint_id="parent-1", similarity_score=0.9)

        repo.add_supporter.assert_called_once_with("parent-1", "citizen-A")

    @pytest.mark.asyncio
    async def test_auto_merge_skips_support_transfer_if_same_citizen(self):
        child  = _complaint(id="child-1", citizen_id="citizen-A")
        parent = _complaint(id="parent-1", citizen_id="citizen-A")

        repo = _make_repo(get_by_id=lambda cid, **kw: parent if cid == "parent-1" else None)
        svc = _service(repo=repo)

        await svc.auto_merge(child_complaint=child, parent_complaint_id="parent-1", similarity_score=0.9)

        repo.add_supporter.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_merge_skips_support_transfer_if_already_supporting(self):
        child  = _complaint(id="child-1", citizen_id="citizen-A")
        parent = _complaint(id="parent-1", citizen_id="citizen-B")

        repo = _make_repo(get_by_id=lambda cid, **kw: parent if cid == "parent-1" else None)
        repo.is_supporter = AsyncMock(return_value=True)
        svc = _service(repo=repo)

        await svc.auto_merge(child_complaint=child, parent_complaint_id="parent-1", similarity_score=0.9)

        repo.add_supporter.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_merge_notifies_citizen(self):
        child  = _complaint(id="child-1")
        parent = _complaint(id="parent-1", complaint_number="CMP-2025-00099")

        repo = _make_repo(get_by_id=lambda cid, **kw: parent if cid == "parent-1" else None)
        notifier = _make_notifier()
        svc = _service(repo=repo, notifier=notifier)

        await svc.auto_merge(child_complaint=child, parent_complaint_id="parent-1", similarity_score=0.9)

        notifier.notify_duplicate_detected.assert_called_once()
        args = notifier.notify_duplicate_detected.call_args[0]
        assert args[1] == "CMP-2025-00099"

    @pytest.mark.asyncio
    async def test_auto_merge_recalculates_parent_priority(self):
        child  = _complaint(id="child-1")
        parent = _complaint(id="parent-1")
        repo = _make_repo(get_by_id=lambda cid, **kw: parent if cid == "parent-1" else None)
        svc = _service(repo=repo)

        await svc.auto_merge(child_complaint=child, parent_complaint_id="parent-1", similarity_score=0.9)

        repo.recalculate_priority.assert_called_with("parent-1")

    @pytest.mark.asyncio
    async def test_auto_merge_aborts_gracefully_if_parent_missing(self):
        child = _complaint(id="child-1")
        repo = _make_repo(get_by_id=lambda cid, **kw: None)
        svc = _service(repo=repo)

        result = await svc.auto_merge(
            child_complaint=child, parent_complaint_id="ghost-parent", similarity_score=0.9,
        )

        assert result is child
        repo.update_fields.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# confirm_merge
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfirmMerge:

    @pytest.mark.asyncio
    async def test_confirm_merge_requires_officer_or_admin(self):
        citizen = _user(role=UserRole.CITIZEN)
        svc = _service()
        with pytest.raises(ForbiddenError):
            await svc.confirm_merge("child-1", "parent-1", reviewer=citizen)

    @pytest.mark.asyncio
    async def test_confirm_merge_rejects_self_merge(self):
        officer = _user(role=UserRole.OFFICER)
        svc = _service()
        with pytest.raises(BadRequestError):
            await svc.confirm_merge("same-id", "same-id", reviewer=officer)

    @pytest.mark.asyncio
    async def test_confirm_merge_404_when_child_missing(self):
        officer = _user(role=UserRole.OFFICER)
        repo = _make_repo(get_by_id=lambda cid, **kw: None)
        svc = _service(repo=repo)
        with pytest.raises(NotFoundError):
            await svc.confirm_merge("child-1", "parent-1", reviewer=officer)

    @pytest.mark.asyncio
    async def test_confirm_merge_404_when_parent_missing(self):
        officer = _user(role=UserRole.OFFICER)
        child = _complaint(id="child-1")

        async def get_by_id(cid, **kw):
            return child if cid == "child-1" else None

        repo = _make_repo(get_by_id=get_by_id)
        svc = _service(repo=repo)
        with pytest.raises(NotFoundError):
            await svc.confirm_merge("child-1", "parent-1", reviewer=officer)

    @pytest.mark.asyncio
    async def test_confirm_merge_rejects_already_merged_child(self):
        officer = _user(role=UserRole.OFFICER)
        child  = _complaint(id="child-1", is_duplicate=True, parent_complaint_id="other-parent")
        parent = _complaint(id="parent-1")

        async def get_by_id(cid, **kw):
            return {"child-1": child, "parent-1": parent}.get(cid)

        repo = _make_repo(get_by_id=get_by_id)
        svc = _service(repo=repo)
        with pytest.raises(BadRequestError):
            await svc.confirm_merge("child-1", "parent-1", reviewer=officer)

    @pytest.mark.asyncio
    async def test_confirm_merge_rejects_resolved_child(self):
        officer = _user(role=UserRole.OFFICER)
        child  = _complaint(id="child-1", status=ComplaintStatus.RESOLVED)
        parent = _complaint(id="parent-1")

        async def get_by_id(cid, **kw):
            return {"child-1": child, "parent-1": parent}.get(cid)

        repo = _make_repo(get_by_id=get_by_id)
        svc = _service(repo=repo)
        with pytest.raises(BadRequestError):
            await svc.confirm_merge("child-1", "parent-1", reviewer=officer)

    @pytest.mark.asyncio
    async def test_confirm_merge_rejects_closed_parent(self):
        officer = _user(role=UserRole.OFFICER)
        child  = _complaint(id="child-1")
        parent = _complaint(id="parent-1", status=ComplaintStatus.CLOSED)

        async def get_by_id(cid, **kw):
            return {"child-1": child, "parent-1": parent}.get(cid)

        repo = _make_repo(get_by_id=get_by_id)
        svc = _service(repo=repo)
        with pytest.raises(BadRequestError):
            await svc.confirm_merge("child-1", "parent-1", reviewer=officer)

    @pytest.mark.asyncio
    async def test_confirm_merge_succeeds_and_logs_audit(self):
        officer = _user(role=UserRole.OFFICER)
        child  = _complaint(id="child-1")
        parent = _complaint(id="parent-1", complaint_number="CMP-2025-00050")

        async def get_by_id(cid, detail=False, **kw):
            return {"child-1": child, "parent-1": parent}.get(cid)

        repo  = _make_repo(get_by_id=get_by_id)
        audit = _make_audit()
        svc = _service(repo=repo, audit=audit)

        await svc.confirm_merge("child-1", "parent-1", reviewer=officer, notes="Same pothole")

        audit.log_update.assert_called_once()
        repo.update_fields.assert_called_once()
        assert repo.update_fields.call_args[1]["status"] == ComplaintStatus.CLOSED

    @pytest.mark.asyncio
    async def test_admin_can_also_confirm_merge(self):
        admin = _user(role=UserRole.ADMIN)
        child  = _complaint(id="child-1")
        parent = _complaint(id="parent-1")

        async def get_by_id(cid, **kw):
            return {"child-1": child, "parent-1": parent}.get(cid)

        repo = _make_repo(get_by_id=get_by_id)
        svc = _service(repo=repo)

        await svc.confirm_merge("child-1", "parent-1", reviewer=admin)   # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# reject_duplicate_flag
# ═══════════════════════════════════════════════════════════════════════════════

class TestRejectDuplicateFlag:

    @pytest.mark.asyncio
    async def test_reject_requires_officer_or_admin(self):
        citizen = _user(role=UserRole.CITIZEN)
        svc = _service()
        with pytest.raises(ForbiddenError):
            await svc.reject_duplicate_flag("complaint-1", reviewer=citizen)

    @pytest.mark.asyncio
    async def test_reject_404_when_complaint_missing(self):
        officer = _user(role=UserRole.OFFICER)
        repo = _make_repo(get_by_id=lambda cid, **kw: None)
        svc = _service(repo=repo)
        with pytest.raises(NotFoundError):
            await svc.reject_duplicate_flag("complaint-1", reviewer=officer)

    @pytest.mark.asyncio
    async def test_reject_blocked_if_already_merged(self):
        officer = _user(role=UserRole.OFFICER)
        complaint = _complaint(id="c1", is_duplicate=True, parent_complaint_id="p1")
        repo = _make_repo(get_by_id=lambda cid, **kw: complaint)
        svc = _service(repo=repo)
        with pytest.raises(BadRequestError):
            await svc.reject_duplicate_flag("c1", reviewer=officer)

    @pytest.mark.asyncio
    async def test_reject_clears_duplicate_flag(self):
        officer = _user(role=UserRole.OFFICER)
        complaint = _complaint(id="c1", status=ComplaintStatus.AI_PROCESSING, is_duplicate=True)
        repo = _make_repo(get_by_id=lambda cid, **kw: complaint)
        svc = _service(repo=repo)

        await svc.reject_duplicate_flag("c1", reviewer=officer)

        repo.update_fields.assert_called_once_with("c1", is_duplicate=False, parent_complaint_id=None)

    @pytest.mark.asyncio
    async def test_reject_transitions_ai_processing_to_pending_review(self):
        officer = _user(role=UserRole.OFFICER)
        complaint = _complaint(id="c1", status=ComplaintStatus.AI_PROCESSING)
        repo = _make_repo(get_by_id=lambda cid, **kw: complaint)
        svc = _service(repo=repo)

        await svc.reject_duplicate_flag("c1", reviewer=officer)

        repo.update_status.assert_called_once_with("c1", ComplaintStatus.PENDING_REVIEW)


# ═══════════════════════════════════════════════════════════════════════════════
# unmerge
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnmerge:

    @pytest.mark.asyncio
    async def test_unmerge_requires_admin_role(self):
        officer = _user(role=UserRole.OFFICER)
        svc = _service()
        with pytest.raises(ForbiddenError):
            await svc.unmerge("child-1", admin=officer)

    @pytest.mark.asyncio
    async def test_unmerge_404_when_child_missing(self):
        admin = _user(role=UserRole.ADMIN)
        repo = _make_repo(get_by_id=lambda cid, **kw: None)
        svc = _service(repo=repo)
        with pytest.raises(NotFoundError):
            await svc.unmerge("child-1", admin=admin)

    @pytest.mark.asyncio
    async def test_unmerge_rejects_non_merged_complaint(self):
        admin = _user(role=UserRole.ADMIN)
        complaint = _complaint(id="c1", is_duplicate=False)
        repo = _make_repo(get_by_id=lambda cid, **kw: complaint)
        svc = _service(repo=repo)
        with pytest.raises(BadRequestError):
            await svc.unmerge("c1", admin=admin)

    @pytest.mark.asyncio
    async def test_unmerge_restores_pending_review_status(self):
        admin = _user(role=UserRole.ADMIN)
        child  = _complaint(id="c1", is_duplicate=True, parent_complaint_id="p1", citizen_id="cit-1")
        parent = _complaint(id="p1")

        async def get_by_id(cid, **kw):
            return {"c1": child, "p1": parent}.get(cid)

        repo = _make_repo(get_by_id=get_by_id)
        svc = _service(repo=repo)

        await svc.unmerge("c1", admin=admin)

        repo.update_fields.assert_called_with("c1", is_duplicate=False, parent_complaint_id=None)
        repo.update_status.assert_called_with("c1", ComplaintStatus.PENDING_REVIEW)

    @pytest.mark.asyncio
    async def test_unmerge_transfers_support_back_to_child(self):
        admin = _user(role=UserRole.ADMIN)
        child  = _complaint(id="c1", is_duplicate=True, parent_complaint_id="p1", citizen_id="cit-1")
        parent = _complaint(id="p1")

        async def get_by_id(cid, **kw):
            return {"c1": child, "p1": parent}.get(cid)

        repo = _make_repo(get_by_id=get_by_id)
        repo.is_supporter = AsyncMock(return_value=True)
        svc = _service(repo=repo)

        await svc.unmerge("c1", admin=admin)

        repo.remove_supporter.assert_called_once_with("p1", "cit-1")
        repo.add_supporter.assert_called_once_with("c1", "cit-1")

    @pytest.mark.asyncio
    async def test_unmerge_recalculates_both_priorities(self):
        admin = _user(role=UserRole.ADMIN)
        child  = _complaint(id="c1", is_duplicate=True, parent_complaint_id="p1")
        parent = _complaint(id="p1")

        async def get_by_id(cid, **kw):
            return {"c1": child, "p1": parent}.get(cid)

        repo = _make_repo(get_by_id=get_by_id)
        svc = _service(repo=repo)

        await svc.unmerge("c1", admin=admin)

        calls = [c.args[0] for c in repo.recalculate_priority.call_args_list]
        assert "p1" in calls
        assert "c1" in calls


# ═══════════════════════════════════════════════════════════════════════════════
# pending review queue — permission check
# ═══════════════════════════════════════════════════════════════════════════════

class TestPendingReviewQueueGuard:

    @pytest.mark.asyncio
    async def test_queue_requires_officer_or_admin(self):
        citizen = _user(role=UserRole.CITIZEN)
        svc = _service()
        with pytest.raises(ForbiddenError):
            await svc.get_pending_review_queue(citizen)
