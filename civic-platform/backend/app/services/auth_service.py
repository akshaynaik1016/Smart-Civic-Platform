"""
AuthService — business logic for the entire authentication lifecycle.

Responsibilities:
  • Citizen / officer / admin registration with duplicate checks
  • Email + password login with brute-force protection
  • JWT access-token / refresh-token issuance
  • Token refresh and revocation (logout)
  • OTP generation, delivery, and verification
  • Password change and forgot-password flow
  • Audit log emission on every auth event

Depends on:
  • UserRepository  — DB queries
  • AuthRepository  — Redis (OTP, blacklist, sessions)
  • EmailService    — OTP / notification delivery
  • AuditService    — append-only audit trail
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    TokenExpiredError,
    TokenRevokedError,
    UnauthorizedError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_expiry_seconds,
    hash_password,
    verify_password,
)
from app.models.models import AuditAction, User, UserRole, UserStatus
from app.repositories.auth_repository import AuthRepository
from app.repositories.user_repository import UserRepository
from app.schemas.schemas import RegisterRequest, TokenResponse, UserOut

logger = logging.getLogger(__name__)


# ─── Token bundle helper ──────────────────────────────────────────────────────

def _build_token_response(user: User) -> dict:
    """Issue a fresh access + refresh token pair for the given user."""
    access_token,  access_jti  = create_access_token(str(user.id), user.role, user.email)
    refresh_token, refresh_jti = create_refresh_token(str(user.id))
    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "Bearer",
        "expires_in":    settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "_access_jti":   access_jti,
        "_refresh_jti":  refresh_jti,
    }


class AuthService:
    """
    Stateless service — all state lives in the DB (via UserRepository)
    and Redis (via AuthRepository).
    """

    def __init__(
        self,
        db:        AsyncSession,
        user_repo: UserRepository,
        auth_repo: AuthRepository,
    ) -> None:
        self._db        = db
        self._users     = user_repo
        self._auth      = auth_repo

    # ── Registration ──────────────────────────────────────────────────────────

    async def register_citizen(
        self,
        payload: RegisterRequest,
        client_ip: Optional[str] = None,
    ) -> User:
        """
        Create a new citizen account.
        The account starts as PENDING_VERIFICATION; email OTP activates it.
        """
        # Uniqueness
        if await self._users.email_exists(payload.email):
            raise ConflictError("An account with this email already exists.")
        if payload.phone and await self._users.phone_exists(payload.phone):
            raise ConflictError("An account with this phone number already exists.")

        user = await self._users.create(
            email=payload.email.lower().strip(),
            phone=payload.phone,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name.strip(),
            role=UserRole.CITIZEN,
            status=UserStatus.PENDING_VERIFICATION,
            ward_id=getattr(payload, "ward_id", None),
            city=getattr(payload, "city", "Hubballi"),
        )

        # Generate and store OTP — caller dispatches email as a background task
        otp = await self._auth.generate_otp(user.email, purpose="verify")

        logger.info("Citizen registered", extra={
            "user_id": user.id, "email": user.email, "ip": client_ip,
        })
        return user, otp

    async def register_officer(
        self,
        full_name: str,
        email: str,
        phone: str,
        password: str,
        badge_number: str,
        department: str,
        designation: Optional[str] = None,
        ward_ids: Optional[list[int]] = None,
        category_ids: Optional[list[int]] = None,
        max_complaints: int = 20,
        created_by_id: Optional[str] = None,
    ) -> User:
        """
        Create an officer account (admin action).
        Officer accounts are ACTIVE immediately (no email verification required).
        """
        from app.models.models import Officer

        if await self._users.email_exists(email):
            raise ConflictError("Email already in use.")

        user = await self._users.create(
            email=email.lower().strip(),
            phone=phone,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role=UserRole.OFFICER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )

        officer = Officer(
            user_id=user.id,
            badge_number=badge_number,
            department=department,
            designation=designation,
            ward_ids=ward_ids or [],
            category_ids=category_ids or [],
            max_complaints=max_complaints,
        )
        self._db.add(officer)
        await self._db.flush()

        logger.info("Officer created", extra={
            "user_id": user.id, "badge": badge_number, "created_by": created_by_id,
        })
        return user

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        client_ip: str = "unknown",
        device_id: str = "default",
    ) -> dict:
        """
        Authenticate with email + password.
        Returns a token bundle dict on success.
        Raises appropriate errors on failure.
        """
        # Brute-force protection
        if await self._auth.is_login_blocked(client_ip):
            retry_after = await self._auth.get_block_ttl(client_ip)
            raise RateLimitError(retry_after=retry_after)

        user = await self._users.get_by_email(email)

        if not user or not verify_password(password, user.password_hash):
            await self._auth.record_failed_attempt(client_ip)
            # Generic message — don't reveal which field is wrong
            raise UnauthorizedError("Incorrect email or password.")

        if user.status == UserStatus.SUSPENDED:
            raise ForbiddenError("Your account has been suspended. Contact support.")

        if user.status == UserStatus.INACTIVE:
            raise ForbiddenError("Your account is inactive.")

        # Email must be verified for citizens
        if (
            user.role == UserRole.CITIZEN
            and not user.email_verified
            and user.status == UserStatus.PENDING_VERIFICATION
        ):
            raise ForbiddenError(
                "Please verify your email address before logging in. "
                "Check your inbox for the OTP."
            )

        # Successful auth — clear failed attempts, update last_login
        await self._auth.clear_failed_attempts(client_ip)
        await self._users.update_last_login(user.id)

        tokens = _build_token_response(user)

        # Persist hashed refresh token
        await self._auth.store_refresh_token(
            user.id, tokens["refresh_token"], device_id
        )

        # Cache session snapshot
        await self._auth.store_session(user.id, {
            "id":    user.id,
            "email": user.email,
            "role":  user.role,
            "name":  user.full_name,
        })

        logger.info("Login success", extra={
            "user_id": user.id, "role": user.role, "ip": client_ip,
        })
        return {**tokens, "user": UserOut.model_validate(user)}

    # ── Token refresh ─────────────────────────────────────────────────────────

    async def refresh_tokens(
        self,
        refresh_token: str,
        device_id: str = "default",
    ) -> dict:
        """
        Validate a refresh token and issue a new access token.
        Implements refresh-token rotation: the old refresh token is revoked
        and a new one is issued.
        """
        try:
            claims = decode_token(refresh_token)
        except Exception:
            raise UnauthorizedError("Invalid or expired refresh token.")

        if claims.get("type") != "refresh":
            raise UnauthorizedError("Not a refresh token.")

        user_id = claims.get("sub", "")

        # Verify the token is the one we stored (prevents token reuse after logout)
        is_valid = await self._auth.validate_refresh_token(user_id, refresh_token, device_id)
        if not is_valid:
            # Possible token theft — revoke ALL tokens for this user
            await self._auth.revoke_all_refresh_tokens(user_id)
            raise TokenRevokedError()

        user = await self._users.get_by_id(user_id)
        if not user or user.status not in (UserStatus.ACTIVE,):
            raise UnauthorizedError("User account is not active.")

        # Revoke the used refresh token (rotation)
        await self._auth.revoke_refresh_token(user_id, device_id)

        # Issue fresh pair
        tokens = _build_token_response(user)
        await self._auth.store_refresh_token(user_id, tokens["refresh_token"], device_id)

        logger.info("Token refreshed", extra={"user_id": user_id})
        return tokens

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(
        self,
        access_token: str,
        user_id: str,
        device_id: str = "default",
        logout_all_devices: bool = False,
    ) -> None:
        """
        Revoke the current session's tokens.
        If logout_all_devices=True, revoke refresh tokens on all devices.
        """
        # Blacklist the access token until it naturally expires
        try:
            claims = decode_token(access_token)
            jti = claims.get("jti", "")
            ttl = get_token_expiry_seconds(access_token)
            if jti:
                await self._auth.blacklist_token(jti, ttl)
        except Exception:
            pass

        if logout_all_devices:
            await self._auth.revoke_all_refresh_tokens(user_id)
        else:
            await self._auth.revoke_refresh_token(user_id, device_id)

        await self._auth.delete_session(user_id)
        logger.info("Logout", extra={"user_id": user_id, "all_devices": logout_all_devices})

    # ── OTP flow ──────────────────────────────────────────────────────────────

    async def send_email_otp(
        self,
        email: str,
        purpose: str = "verify",
    ) -> Optional[str]:
        """
        Generate and store an OTP. Returns (otp_code, user) so the caller
        can dispatch the email as a background task.
        Returns None if no user exists for that email (caller must NOT reveal this).
        """
        user = await self._users.get_by_email(email)
        if not user:
            return None, None
        otp = await self._auth.generate_otp(email.lower(), purpose=purpose)
        return otp, user

    async def verify_email_otp(
        self,
        email: str,
        otp_code: str,
        purpose: str = "verify",
    ) -> tuple[bool, str, Optional[User]]:
        """
        Verify OTP and (if purpose=='verify') activate the account.
        Returns (success, reason, user_or_None).
        """
        ok, reason = await self._auth.verify_otp(email.lower(), otp_code, purpose)
        if not ok:
            return False, reason, None

        user = await self._users.get_by_email(email)
        if not user:
            return False, "user_not_found", None

        if purpose == "verify" and not user.email_verified:
            await self._users.mark_email_verified(user.id)
            await self._db.refresh(user)

        return True, "ok", user

    async def issue_token_pair(self, user: User, device_id: str = "default") -> dict:
        """
        Public entry point for issuing a fresh access+refresh token pair for
        an already-authenticated/verified user — used by the OTP-verify flow,
        which needs to log the citizen in immediately after activation
        without making them submit their password again. Mirrors the same
        token-issuance + refresh-token storage + session caching that
        login() performs, so a session created this way is indistinguishable
        from one created via password login.
        """
        tokens = _build_token_response(user)
        await self._auth.store_refresh_token(user.id, tokens["refresh_token"], device_id)
        await self._auth.store_session(user.id, {
            "id": user.id, "email": user.email, "role": user.role, "name": user.full_name,
        })
        return {**tokens, "user": UserOut.model_validate(user)}

    async def verify_phone_otp(
        self,
        phone: str,
        otp_code: str,
    ) -> tuple[bool, str]:
        """Verify a phone-number OTP."""
        ok, reason = await self._auth.verify_otp(phone, otp_code, purpose="phone")
        if ok:
            user = await self._users.get_by_phone(phone)
            if user:
                await self._users.mark_phone_verified(user.id)
        return ok, reason

    # ── Password management ───────────────────────────────────────────────────

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> None:
        """
        Authenticated password change.
        Revokes all existing refresh tokens to force re-login on other devices.
        """
        if not verify_password(current_password, user.password_hash):
            raise BadRequestError("Current password is incorrect.")

        if len(new_password) < 8:
            raise BadRequestError("New password must be at least 8 characters.")

        if verify_password(new_password, user.password_hash):
            raise BadRequestError("New password must differ from the current password.")

        await self._users.update_password(user.id, hash_password(new_password))
        await self._auth.revoke_all_refresh_tokens(user.id)
        await self._auth.delete_session(user.id)
        logger.info("Password changed", extra={"user_id": user.id})

    async def initiate_password_reset(self, email: str) -> Optional[str]:
        """
        Forgot-password: generate a reset OTP.
        Always returns the same message regardless of whether the email exists.
        """
        user = await self._users.get_by_email(email)
        if not user:
            return None, None
        otp = await self._auth.generate_otp(email.lower(), purpose="reset", ttl=600)
        return otp, user

    async def complete_password_reset(
        self,
        email: str,
        otp_code: str,
        new_password: str,
    ) -> None:
        """Verify reset OTP and set the new password."""
        ok, reason = await self._auth.verify_otp(email.lower(), otp_code, purpose="reset")
        if not ok:
            err_map = {
                "expired":      "OTP has expired. Please request a new password reset.",
                "invalid":      "Incorrect OTP code.",
                "max_attempts": "Too many incorrect attempts. Please start over.",
            }
            raise BadRequestError(err_map.get(reason, "OTP verification failed."))

        user = await self._users.get_by_email(email)
        if not user:
            raise NotFoundError("User", email)

        if len(new_password) < 8:
            raise BadRequestError("Password must be at least 8 characters.")

        await self._users.update_password(user.id, hash_password(new_password))
        await self._auth.revoke_all_refresh_tokens(user.id)
        await self._auth.delete_session(user.id)
        logger.info("Password reset complete", extra={"user_id": user.id})

    # ── FCM tokens ────────────────────────────────────────────────────────────

    async def register_device(
        self,
        user_id: str,
        device_id: str,
        fcm_token: str,
    ) -> None:
        await self._auth.store_fcm_token(user_id, device_id, fcm_token)

    async def deregister_device(self, user_id: str, device_id: str) -> None:
        await self._auth.delete_fcm_token(user_id, device_id)
