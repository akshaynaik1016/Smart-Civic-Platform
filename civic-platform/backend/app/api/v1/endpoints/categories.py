"""
Categories API
===============
GET    /categories                  — public: list active issue categories (for the mobile app's report form)
GET    /categories/all               — admin: list all categories including inactive
GET    /categories/{category_id}     — get a single category
POST   /categories                   — admin: create a new category
PATCH  /categories/{category_id}     — admin: update SLA hours, description, activation
DELETE /categories/{category_id}     — admin: deactivate (soft) — never hard-deletes,
                                         since complaints.category_id has ON DELETE RESTRICT
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.v1.dependencies.auth import AdminRequired, CurrentUser, DbDep
from app.core.exceptions import ConflictError, NotFoundError
from app.models.models import Category, IssueCategory
from app.repositories.complaint_repository import ComplaintRepository
from app.schemas.schemas import MessageResponse

router = APIRouter(prefix="/categories", tags=["Categories"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sla_hours: int
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class CategoryCreateRequest(BaseModel):
    name: IssueCategory
    display_name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    sla_hours: int = Field(48, ge=1, le=720)
    sort_order: int = Field(0, ge=0)


class CategoryUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    sla_hours: Optional[int] = Field(None, ge=1, le=720)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[CategoryOut],
    summary="List active issue categories (for the citizen report form)",
)
async def list_active_categories(db: DbDep) -> list[CategoryOut]:
    repo = ComplaintRepository(db)
    categories = await repo.get_all_categories(active_only=True)
    return [CategoryOut.model_validate(c) for c in categories]


@router.get(
    "/all",
    response_model=list[CategoryOut],
    summary="Admin: list all categories including inactive ones",
)
async def list_all_categories(admin: AdminRequired, db: DbDep) -> list[CategoryOut]:
    repo = ComplaintRepository(db)
    categories = await repo.get_all_categories(active_only=False)
    return [CategoryOut.model_validate(c) for c in categories]


@router.get(
    "/{category_id}",
    response_model=CategoryOut,
    summary="Get a single category by ID",
)
async def get_category(category_id: int, db: DbDep) -> CategoryOut:
    repo = ComplaintRepository(db)
    category = await repo.get_category_by_id(category_id)
    if not category:
        raise NotFoundError("Category", str(category_id))
    return CategoryOut.model_validate(category)


# ── Admin CRUD ────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=CategoryOut,
    status_code=201,
    summary="Admin: create a new issue category",
)
async def create_category(
    admin: AdminRequired, db: DbDep, body: CategoryCreateRequest,
) -> CategoryOut:
    repo = ComplaintRepository(db)
    existing = await repo.get_category_by_name(body.name)
    if existing:
        raise ConflictError(f"Category '{body.name}' already exists.")

    category = Category(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        icon=body.icon,
        sla_hours=body.sla_hours,
        sort_order=body.sort_order,
        is_active=True,
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    await db.commit()
    return CategoryOut.model_validate(category)


@router.patch(
    "/{category_id}",
    response_model=CategoryOut,
    summary="Admin: update a category's display name, SLA hours, or activation",
)
async def update_category(
    category_id: int, admin: AdminRequired, db: DbDep, body: CategoryUpdateRequest,
) -> CategoryOut:
    repo = ComplaintRepository(db)
    category = await repo.get_category_by_id(category_id)
    if not category:
        raise NotFoundError("Category", str(category_id))

    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(category, field, value)

    await db.flush()
    await db.refresh(category)
    await db.commit()
    return CategoryOut.model_validate(category)


@router.delete(
    "/{category_id}",
    response_model=MessageResponse,
    summary="Admin: deactivate a category (soft — existing complaints keep their category)",
)
async def deactivate_category(
    category_id: int, admin: AdminRequired, db: DbDep,
) -> dict:
    """
    Categories are never hard-deleted: complaints.category_id has
    ON DELETE RESTRICT specifically so historical complaints always retain
    a valid category reference. Deactivating just hides it from the
    citizen-facing report form going forward.
    """
    repo = ComplaintRepository(db)
    category = await repo.get_category_by_id(category_id)
    if not category:
        raise NotFoundError("Category", str(category_id))

    category.is_active = False
    await db.flush()
    await db.commit()
    return {"message": f"Category '{category.display_name}' deactivated."}
