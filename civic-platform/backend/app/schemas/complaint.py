"""Complaint Pydantic schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

class ComplaintCreateRequest(BaseModel):
    title: str = Field(min_length=5, max_length=255)
    description: str = Field(min_length=10)
    category: str
    severity: str = "medium"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: Optional[str] = None
    ward_id: Optional[int] = None
    landmark: Optional[str] = None
    tags: Optional[list[str]] = None

class ComplaintStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None
    officer_id: Optional[str] = None

class ComplaintAssignRequest(BaseModel):
    officer_id: str

class ComplaintVerifyRequest(BaseModel):
    is_resolved: bool
    rating: Optional[int] = Field(None, ge=1, le=5)
    feedback: Optional[str] = None

class ComplaintFilters(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    ward_id: Optional[int] = None
    officer_id: Optional[str] = None
    citizen_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    search: Optional[str] = None
    is_duplicate: Optional[bool] = None
    sla_breached: Optional[bool] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: str = "created_at"
    sort_order: str = "desc"

class ImageOut(BaseModel):
    id: str
    cdn_url: Optional[str]
    thumbnail_url: Optional[str]
    is_primary: bool
    is_resolution: bool
    caption: Optional[str]
    bounding_boxes: Optional[Any]
    created_at: datetime
    model_config = {"from_attributes": True}

class ComplaintOut(BaseModel):
    id: str
    complaint_number: str
    citizen_id: str
    officer_id: Optional[str]
    category_id: int
    category: str
    status: str
    severity: str
    priority_score: float
    latitude: float
    longitude: float
    address: Optional[str]
    ward_id: Optional[int]
    title: str
    description: str
    ai_description: Optional[str]
    tags: Optional[list[str]]
    is_duplicate: bool
    support_count: int
    ai_confidence: Optional[float]
    resolved_at: Optional[datetime]
    citizen_verified: bool
    citizen_rating: Optional[int]
    sla_deadline: Optional[datetime]
    sla_breached: bool
    images: list[ImageOut] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class PaginatedComplaints(BaseModel):
    items: list[ComplaintOut]
    total: int
    page: int
    page_size: int
    pages: int
