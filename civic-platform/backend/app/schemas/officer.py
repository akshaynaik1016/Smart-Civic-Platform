"""Officer Pydantic schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class OfficerCreateRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str = Field(min_length=8)
    badge_number: str
    department: str
    designation: Optional[str] = None
    ward_ids: list[int] = []
    category_ids: list[int] = []
    max_complaints: int = 20

class OfficerUpdateRequest(BaseModel):
    department: Optional[str] = None
    designation: Optional[str] = None
    ward_ids: Optional[list[int]] = None
    category_ids: Optional[list[int]] = None
    is_available: Optional[bool] = None
    max_complaints: Optional[int] = None

class OfficerOut(BaseModel):
    id: str
    user_id: str
    badge_number: str
    department: str
    designation: Optional[str]
    ward_ids: list[int]
    category_ids: list[int]
    is_available: bool
    max_complaints: int
    total_assigned: int
    total_resolved: int
    avg_resolution_days: Optional[float]
    performance_score: float
    created_at: datetime
    model_config = {"from_attributes": True}
