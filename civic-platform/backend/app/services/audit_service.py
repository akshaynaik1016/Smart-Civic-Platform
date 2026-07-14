"""
AuditService — append-only audit trail writer.

Every sensitive operation (login, status change, role change, delete, export…)
calls AuditService.log(). The audit_logs table is partitioned by month and
never modified after insert.

Usage:
    audit = AuditService(db)
    await audit.log(
        action=AuditAction.login,
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=client_ip,
        success=True,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditAction, AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Write-only audit log service."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(
        self,
        action:        AuditAction,
        *,
        user_id:       Optional[str]  = None,
        resource_type: Optional[str]  = None,
        resource_id:   Optional[str]  = None,
        old_values:    Optional[dict] = None,
        new_values:    Optional[dict] = None,
        ip_address:    Optional[str]  = None,
        user_agent:    Optional[str]  = None,
        request_id:    Optional[str]  = None,
        success:       bool           = True,
        error_message: Optional[str]  = None,
        duration_ms:   Optional[int]  = None,
    ) -> None:
        """
        Append one audit log entry.

        This method intentionally never raises — audit failures must not
        break the primary operation.  Errors are swallowed and logged.
        """
        try:
            entry = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                success=success,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            self._db.add(entry)
            # flush without committing — the outer request handler commits
            await self._db.flush([entry])
        except Exception as exc:
            import traceback

            print("\n========== AUDIT ERROR ==========")
            traceback.print_exc()
            print("=================================\n")

    # ── Convenience shortcuts ─────────────────────────────────────────────────

    async def log_login(
        self,
        user_id: str,
        ip: str,
        user_agent: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        action = AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED
        await self.log(
            action=action,
            user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            ip_address=ip,
            user_agent=user_agent,
            success=success,
            error_message=error,
        )

    async def log_logout(self, user_id: str, ip: str) -> None:
        await self.log(
            action=AuditAction.LOGOUT,
            user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            ip_address=ip,
        )

    async def log_create(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        new_values: Optional[dict] = None,
        ip: Optional[str] = None,
    ) -> None:
        await self.log(
            action=AuditAction.CREATE,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            new_values=new_values,
            ip_address=ip,
        )

    async def log_update(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        ip: Optional[str] = None,
    ) -> None:
        await self.log(
            action=AuditAction.UPDATE,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip,
        )

    async def log_delete(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        ip: Optional[str] = None,
    ) -> None:
        await self.log(
            action=AuditAction.DELETE,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip,
        )

    async def log_role_change(
        self,
        admin_id: str,
        target_user_id: str,
        old_role: str,
        new_role: str,
        ip: Optional[str] = None,
    ) -> None:
        await self.log(
            action=AuditAction.ROLE_CHANGED,
            user_id=admin_id,
            resource_type="user",
            resource_id=target_user_id,
            old_values={"role": old_role},
            new_values={"role": new_role},
            ip_address=ip,
        )

    async def log_password_change(self, user_id: str, ip: Optional[str] = None) -> None:
        await self.log(
            action=AuditAction.PASSWORD_CHANGED,
            user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            ip_address=ip,
        )

    async def log_complaint_assigned(
        self,
        admin_id: str,
        complaint_id: str,
        officer_id: str,
        ip: Optional[str] = None,
    ) -> None:
        await self.log(
            action=AuditAction.COMPLAINT_ASSIGNED,
            user_id=admin_id,
            resource_type="complaint",
            resource_id=complaint_id,
            new_values={"officer_id": officer_id},
            ip_address=ip,
        )
