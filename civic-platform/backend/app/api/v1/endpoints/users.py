"""
Users API
==========
GET    /users/me                          — current user's profile
PATCH  /users/me                          — update own profile
POST   /users/me/avatar                   — upload avatar image
GET    /users/me/activity                 — activity summary for profile screen
GET    /users/{user_id}                   — view a profile (own / officer / admin)
GET    /users                             — admin/officer: paginated list with filters
PATCH  /users/{user_id}/status            — admin: suspend/reactivate
DELETE /users/{user_id}                   — admin: soft delete
PATCH  /users/{user_id}/role              — admin: promote/demote
GET    /users/analytics/summary           — admin: role counts, top reporters
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.v1.dependencies.auth import AdminRequired, CurrentUser, DbDep
from app.core.exceptions import BadRequestError
from app.models.models import UserRole, UserStatus
from app.repositories.user_repository import UserRepository
from app.schemas.schemas import (
    MessageResponse,
    PaginatedResponse,
    UserOut,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


async def _get_service(db: DbDep) -> UserService:
    return UserService(db=db, user_repo=UserRepository(db))


ServiceDep = Annotated[UserService, Depends(_get_service)]


# ── Self-service ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut, summary="Get my own profile")
async def get_my_profile(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut, summary="Update my profile")
async def update_my_profile(
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
    body: UserUpdateRequest,
) -> UserOut:
    updated = await service.update_profile(
        str(current_user.id),
        current_user,
        full_name=body.full_name,
        phone=body.phone,
        ward_id=body.ward_id,
        city=body.city,
    )
    await db.commit()
    return UserOut.model_validate(updated)


@router.post(
    "/me/avatar",
    response_model=dict,
    summary="Upload my avatar image",
)
async def upload_my_avatar(
    current_user: CurrentUser,
    service: ServiceDep,
    db: DbDep,
    image: UploadFile = File(...),
) -> dict:
    content = await image.read()
    cdn_url = await service.upload_avatar(
        str(current_user.id), content, image.content_type or "image/jpeg", current_user,
    )
    await db.commit()
    return {"avatar_url": cdn_url}


@router.get(
    "/me/activity",
    summary="Get my activity summary (complaint counts, recent reports, reputation)",
)
async def get_my_activity(current_user: CurrentUser, service: ServiceDep) -> dict:
    return await service.get_activity_summary(str(current_user.id))


# ── Viewing other profiles ────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=UserOut, summary="Get a user's profile")
async def get_user_profile(
    user_id: str, current_user: CurrentUser, service: ServiceDep,
) -> UserOut:
    user = await service.get_profile(user_id, current_user)
    return UserOut.model_validate(user)


# ── Admin / officer listing ───────────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedResponse[UserOut],
    summary="List users (admin sees everyone, officers see their ward's citizens)",
)
async def list_users(
    current_user: CurrentUser,
    service: ServiceDep,
    role: Optional[str] = Query(None, description="Filter by role: citizen | officer | admin"),
    status: Optional[str] = Query(None, description="Filter by status"),
    ward_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
) -> PaginatedResponse[UserOut]:
    users, total, pages = await service.list_users(
        current_user,
        role=role, status=status, ward_id=ward_id, search=search,
        page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order,
    )
    return PaginatedResponse[UserOut](
        items=[UserOut.model_validate(u) for u in users],
        total=total, page=page, page_size=page_size, pages=pages,
    )


# ── Admin actions ─────────────────────────────────────────────────────────────

@router.patch(
    "/{user_id}/status",
    response_model=UserOut,
    summary="Admin: suspend or reactivate a user account",
)
async def update_user_status(
    user_id: str,
    admin: AdminRequired,
    service: ServiceDep,
    db: DbDep,
    body: UserStatusUpdateRequest,
) -> UserOut:
    if body.status == UserStatus.SUSPENDED:
        updated = await service.suspend_user(user_id, admin, reason=body.reason)
    elif body.status == UserStatus.ACTIVE:
        updated = await service.reactivate_user(user_id, admin)
    else:
        raise BadRequestError(
            f"Unsupported status transition via this endpoint: '{body.status}'. "
            "Use 'active' to reactivate or 'suspended' to suspend."
        )
    await db.commit()
    return UserOut.model_validate(updated)


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    summary="Admin: soft-delete a user account",
)
async def delete_user(
    user_id: str, admin: AdminRequired, service: ServiceDep, db: DbDep,
) -> dict:
    await service.delete_user(user_id, admin)
    await db.commit()
    return {"message": "User account deleted."}


@router.patch(
    "/{user_id}/role",
    response_model=UserOut,
    summary="Admin: change a user's role",
)
async def change_user_role(
    user_id: str,
    admin: AdminRequired,
    service: ServiceDep,
    db: DbDep,
    role: UserRole,
) -> UserOut:
    updated = await service.change_user_role(user_id, role, admin)
    await db.commit()
    return UserOut.model_validate(updated)


# ── Analytics ─────────────────────────────────────────────────────────────────

@router.get(
    "/analytics/summary",
    summary="Admin: user analytics — role distribution, active count, top reporters",
)
async def get_user_analytics(admin: AdminRequired, service: ServiceDep) -> dict:
    return await service.get_user_analytics(admin)
