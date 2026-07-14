"""User Pydantic schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    phone: Optional[str]
    role: str
    status: str
    avatar_url: Optional[str]
    ward_id: Optional[int]
    city: str
    email_verified: bool
    phone_verified: bool
    total_complaints: int
    resolved_complaints: int
    reputation_score: float
    last_login_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}

class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    ward_id: Optional[int] = None
    city: Optional[str] = None
    pincode: Optional[str] = None

class UserStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None

class UserFilters(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    ward_id: Optional[int] = None
    search: Optional[str] = None
    page: int = 1
    page_size: int = 20
