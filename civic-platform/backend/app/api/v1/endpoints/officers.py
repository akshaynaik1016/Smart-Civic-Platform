"""
Officers API
=============
POST   /officers                          — admin: onboard a new officer (creates User+Officer)
GET    /officers/me                       — officer: my own officer profile
PATCH  /officers/me/availability          — officer: toggle my availability
GET    /officers                          — admin/officer: paginated list with filters
GET    /officers/suggest                  — admin/officer: suggested officers for a complaint
GET    /officers/{officer_id}             — view a single officer profile
GET    /officers/{officer_id}/workload    — workload summary
PATCH  /officers/{officer_id}/scope        — admin: update ward/category assignment
PATCH  /officers/{officer_id}/capacity     — admin: update max_complaints
DELETE /officers/{officer_id}              — admin: deactivate
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field

from app.api.v1.dependencies.auth import AdminRequired, CurrentUser, DbDep
from app.repositories.officer_repository import OfficerRepository
from app.repositories.user_repository import UserRepository
from app.schemas.schemas import MessageResponse
from app.services.auth_service import AuthService
from app.services.officer_service import OfficerService

router = APIRouter(prefix="/officers", tags=["Officers"])


async def _get_service(db: DbDep) -> OfficerService:
    return OfficerService(db=db, officer_repo=OfficerRepository(db), user_repo=UserRepository(db))


ServiceDep = Annotated[OfficerService, Depends(_get_service)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class OfficerOnboardRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=8)
    badge_number: str = Field(min_length=2, max_length=50)
    department: str = Field(min_length=2, max_length=150)
    designation: Optional[str] = None
    ward_ids: list[int] = Field(default_factory=list)
    category_ids: list[int] = Field(default_factory=list)
    max_complaints: int = Field(20, ge=1, le=200)


class OfficerOut(BaseModel):
    id: str
    user_id: str
    name: Optional[str] = None
    badge_number: str
    department: str
    designation: Optional[str] = None
    ward_ids: list[int]
    category_ids: list[int]
    is_available: bool
    max_complaints: int
    total_assigned: int
    total_resolved: int
    performance_score: float

    class Config:
        from_attributes = True

    @classmethod
    def from_officer(cls, officer) -> "OfficerOut":
        return cls(
            id=str(officer.id),
            user_id=str(officer.user_id),
            name=officer.user.full_name if officer.user else None,
            badge_number=officer.badge_number,
            department=officer.department,
            designation=officer.designation,
            ward_ids=officer.ward_ids or [],
            category_ids=officer.category_ids or [],
            is_available=officer.is_available,
            max_complaints=officer.max_complaints,
            total_assigned=officer.total_assigned,
            total_resolved=officer.total_resolved,
            performance_score=float(officer.performance_score),
        )


class AvailabilityUpdateRequest(BaseModel):
    is_available: bool


class ScopeUpdateRequest(BaseModel):
    ward_ids: Optional[list[int]] = None
    category_ids: Optional[list[int]] = None


class CapacityUpdateRequest(BaseModel):
    max_complaints: int = Field(ge=1, le=200)


# ── Onboarding ────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=OfficerOut,
    status_code=201,
    summary="Admin: onboard a new officer (creates the User + Officer rows)",
)
async def onboard_officer(
    admin: AdminRequired, db: DbDep, body: OfficerOnboardRequest,
) -> OfficerOut:
    """
    Delegates account creation to AuthService.register_officer (the single
    source of truth for "what does a new officer account look like"),
    then re-fetches the row with its relationships loaded for the response.
    """
    from app.repositories.auth_repository import AuthRepository
    from app.core.redis_client import redis_client

    auth_service = AuthService(
        db=db, user_repo=UserRepository(db), auth_repo=AuthRepository(redis_client),
    )
    user = await auth_service.register_officer(
        full_name=body.full_name, email=body.email, phone=body.phone, password=body.password,
        badge_number=body.badge_number, department=body.department, designation=body.designation,
        ward_ids=body.ward_ids, category_ids=body.category_ids,
        max_complaints=body.max_complaints, created_by_id=str(admin.id),
    )
    await db.commit()

    officer_repo = OfficerRepository(db)
    officer = await officer_repo.get_by_user_id(str(user.id))
    return OfficerOut.from_officer(officer)


# ── Self-service ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=OfficerOut, summary="Get my own officer profile")
async def get_my_officer_profile(current_user: CurrentUser, service: ServiceDep) -> OfficerOut:
    officer = await service.get_my_officer_profile(current_user)
    return OfficerOut.from_officer(officer)


@router.patch(
    "/me/availability",
    response_model=OfficerOut,
    summary="Toggle my own availability for new assignments",
)
async def update_my_availability(
    current_user: CurrentUser, service: ServiceDep, db: DbDep, body: AvailabilityUpdateRequest,
) -> OfficerOut:
    officer = await service.update_my_availability(current_user, body.is_available)
    await db.commit()
    return OfficerOut.from_officer(officer)


# ── Listing & suggestions ─────────────────────────────────────────────────────

@router.get(
    "",
    summary="List officers with filters (admin/officer access)",
)
async def list_officers(
    current_user: CurrentUser,
    service: ServiceDep,
    department: Optional[str] = Query(None),
    ward_id: Optional[int] = Query(None),
    is_available: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    officers, total, pages = await service.list_officers(
        current_user, department=department, ward_id=ward_id,
        is_available=is_available, search=search, page=page, page_size=page_size,
    )
    return {
        "items": [OfficerOut.from_officer(o) for o in officers],
        "total": total, "page": page, "page_size": page_size, "pages": pages,
    }


@router.get(
    "/suggest",
    summary="Get suggested officers for a complaint assignment, sorted by lightest workload",
)
async def suggest_officers(
    current_user: CurrentUser,
    service: ServiceDep,
    ward_id: Optional[int] = Query(None),
    category_id: Optional[int] = Query(None),
    limit: int = Query(5, ge=1, le=20),
) -> list[dict]:
    return await service.suggest_officers_for_complaint(
        current_user, ward_id=ward_id, category_id=category_id, limit=limit,
    )


# ── Single officer ────────────────────────────────────────────────────────────

@router.get("/{officer_id}", response_model=OfficerOut, summary="Get a single officer's profile")
async def get_officer(officer_id: str, current_user: CurrentUser, service: ServiceDep) -> OfficerOut:
    officer = await service.get_officer(officer_id, current_user)
    return OfficerOut.from_officer(officer)


@router.get("/{officer_id}/workload", summary="Get an officer's current workload summary")
async def get_officer_workload(officer_id: str, current_user: CurrentUser, service: ServiceDep) -> dict:
    return await service.get_workload(officer_id, current_user)


# ── Admin updates ─────────────────────────────────────────────────────────────

@router.patch(
    "/{officer_id}/scope",
    response_model=OfficerOut,
    summary="Admin: update an officer's assigned wards/categories",
)
async def update_officer_scope(
    officer_id: str, admin: AdminRequired, service: ServiceDep, db: DbDep, body: ScopeUpdateRequest,
) -> OfficerOut:
    officer = await service.update_assignment_scope(
        officer_id, admin, ward_ids=body.ward_ids, category_ids=body.category_ids,
    )
    await db.commit()
    return OfficerOut.from_officer(officer)


@router.patch(
    "/{officer_id}/capacity",
    response_model=OfficerOut,
    summary="Admin: update an officer's max concurrent complaint capacity",
)
async def update_officer_capacity(
    officer_id: str, admin: AdminRequired, service: ServiceDep, db: DbDep, body: CapacityUpdateRequest,
) -> OfficerOut:
    officer = await service.update_max_complaints(officer_id, admin, body.max_complaints)
    await db.commit()
    return OfficerOut.from_officer(officer)


@router.delete(
    "/{officer_id}",
    response_model=MessageResponse,
    summary="Admin: deactivate an officer profile (soft delete)",
)
async def deactivate_officer(
    officer_id: str, admin: AdminRequired, service: ServiceDep, db: DbDep,
) -> dict:
    await service.deactivate_officer(officer_id, admin)
    await db.commit()
    return {"message": "Officer profile deactivated."}
