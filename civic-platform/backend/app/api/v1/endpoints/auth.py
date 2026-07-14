"""
Authentication endpoints — wired against AuthService / AuthRepository
========================================================================
POST /auth/register        — citizen registration
POST /auth/login           — email + password login
POST /auth/refresh         — refresh access token
POST /auth/logout          — revoke tokens
POST /auth/otp/send        — send OTP
POST /auth/otp/verify      — verify OTP
POST /auth/password/change — change password
GET  /auth/me              — current user profile

This file previously called `cache.managers.session_cache.SessionCacheManager`
directly — an older, separate Redis-backed implementation built earlier in
this project's history (see /home/claude/civic-platform/cache/). That
package has been retired in favor of AuthRepository
(app/repositories/auth_repository.py), which is the OTP / session /
token-blacklist implementation every other module already depends on via
app.core.redis_client (notification preferences, FCM device registration,
the officers/users routers). Routing this file through AuthService instead
of duplicating that logic inline means OTPs issued here are now actually
validated by the same store everything else reads from — previously they
were two non-interoperating systems that happened to both compile.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.v1.dependencies.auth import ClientIp, CurrentUser, DbDep, bearer_scheme
from app.core.exceptions import BadRequestError
from app.repositories.auth_repository import AuthRepository
from app.repositories.user_repository import UserRepository
from app.schemas.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    OtpVerifyRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth_service import AuthService
from app.services.email_service import email_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def _get_service(db: DbDep) -> AuthService:
    from app.core.redis_client import redis_client
    return AuthService(db=db, user_repo=UserRepository(db), auth_repo=AuthRepository(redis_client))


ServiceDep = Annotated[AuthService, Depends(_get_service)]


# ─── Register ─────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new citizen account",
)
async def register(
    payload: RegisterRequest,
    background: BackgroundTasks,
    service: ServiceDep,
    db: DbDep,
    client_ip: ClientIp,
) -> MessageResponse:
    user, otp = await service.register_citizen(payload, client_ip=client_ip)
    await db.commit()

    background.add_task(
        email_service.send_otp_email,
        to_email=user.email, name=user.full_name, otp=otp, purpose="verify",
        city=getattr(user, "city", "Hubballi"),
    )

    return MessageResponse(
        message="Account created. Please verify your email address with the OTP sent.",
    )


# ─── Login ────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=dict,  # TokenResponse fields + user
    summary="Authenticate with email and password",
)
async def login(
    payload: LoginRequest,
    service: ServiceDep,
    db: DbDep,
    client_ip: ClientIp,
) -> dict:
    result = await service.login(payload.email, payload.password, client_ip=client_ip)
    await db.commit()
    # AuthService._build_token_response includes internal _access_jti/_refresh_jti
    # keys used only for blacklisting — strip them before they reach the client.
    return {k: v for k, v in result.items() if not k.startswith("_")}


# ─── Refresh ──────────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using refresh token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    service: ServiceDep,
    db: DbDep,
) -> TokenResponse:
    tokens = await service.refresh_tokens(payload.refresh_token)
    await db.commit()
    clean = {k: v for k, v in tokens.items() if not k.startswith("_")}
    return TokenResponse(**clean)


# ─── Logout ───────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke access and refresh tokens for the current session",
)
async def logout(
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    device_id: str = "default",
    logout_all_devices: bool = False,
) -> MessageResponse:
    await service.logout(
        access_token=credentials.credentials,
        user_id=str(current_user.id),
        device_id=device_id,
        logout_all_devices=logout_all_devices,
    )
    return MessageResponse(message="Successfully logged out")


# ─── OTP send ─────────────────────────────────────────────────────────────────

@router.post(
    "/otp/send",
    response_model=MessageResponse,
    summary="Send OTP to a registered email address",
)
async def send_otp(
    email: str,
    purpose: str,
    background: BackgroundTasks,
    service: ServiceDep,
) -> MessageResponse:
    otp, user = await service.send_email_otp(email, purpose=purpose)
    if user and otp:
        background.add_task(
            email_service.send_otp_email,
            to_email=user.email, name=user.full_name, otp=otp, purpose=purpose,
        )
    # Always return the same message regardless of whether the email exists —
    # do not reveal account existence via response timing/content.
    return MessageResponse(message="If that email exists, an OTP has been sent. Valid for 5 minutes.")


# ─── OTP verify ───────────────────────────────────────────────────────────────

@router.post(
    "/otp/verify",
    response_model=dict,
    summary="Verify OTP and activate the account",
)
async def verify_otp(
    payload: OtpVerifyRequest,
    service: ServiceDep,
    db: DbDep,
) -> dict:
    identifier = (payload.email or payload.phone or "").lower()
    if not identifier:
        raise BadRequestError("Email or phone is required.")

    ok, reason, user = await service.verify_email_otp(identifier, payload.otp, purpose=payload.purpose)

    if not ok:
        detail = {
            "expired": "OTP has expired. Please request a new one.",
            "invalid": "Incorrect OTP code.",
            "max_attempts": "Too many incorrect attempts. Please request a new OTP.",
        }.get(reason, "OTP verification failed.")
        raise BadRequestError(detail)

    await db.commit()

    if payload.purpose == "verify" and user:
        return await service.issue_token_pair(user)

    return {"message": "OTP verified successfully."}


# ─── Change password ──────────────────────────────────────────────────────────

@router.post(
    "/password/change",
    response_model=MessageResponse,
    summary="Change the authenticated user's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
) -> MessageResponse:
    await service.change_password(current_user, payload.current_password, payload.new_password)
    await db.commit()
    return MessageResponse(message="Password changed successfully. Please log in again.")


# ─── Me ───────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the authenticated user's profile",
)
async def get_me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
