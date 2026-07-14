"""
Pydantic v2 schemas for request validation and response serialisation.
"""

import uuid
from datetime import date, datetime
from typing import Any, Optional, List, Generic, TypeVar

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict

from app.models.models import (
    UserRole, UserStatus, ComplaintStatus, SeverityLevel,
    IssueCategory, NotificationType, NotificationChannel,
    NotificationStatus, ReportType, ReportStatus, AuditAction,
)

T = TypeVar("T")

# ─── Base ─────────────────────────────────────────────────────────────────────

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class PaginatedResponse(BaseModel, Generic[T]):
    items:    List[T]
    total:    int
    page:     int
    page_size: int
    pages:    int

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str
    success: bool = True


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    full_name: str  = Field(min_length=2, max_length=150)
    email:     EmailStr
    phone:     str  = Field(min_length=10, max_length=15)
    password:  str  = Field(min_length=8, max_length=128)
    ward_id:   Optional[int] = None
    city:      str  = "Hubballi"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return digits


class OtpVerifyRequest(BaseModel):
    otp:      str  = Field(min_length=6, max_length=6)
    email:    Optional[EmailStr] = None
    phone:    Optional[str]      = None
    purpose:  str = "verify"


class RefreshTokenRequest(BaseModel):
    refresh_token: str
    device_id:     Optional[str] = None


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "Bearer"
    expires_in:    int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6)
    new_password:     str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("New password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("New password must contain at least one digit")
        return v


# ─── User ─────────────────────────────────────────────────────────────────────

class UserBase(BaseSchema):
    email:              str
    phone:              Optional[str]
    full_name:          str
    role:               UserRole
    status:             UserStatus
    avatar_url:         Optional[str]
    ward_id:            Optional[int]
    city:               str
    email_verified:     bool
    phone_verified:     bool
    total_complaints:   int
    resolved_complaints: int
    reputation_score:   float
    last_login_at:      Optional[datetime]
    created_at:         datetime


class UserOut(UserBase):
    id: uuid.UUID


class UserUpdateRequest(BaseModel):
    full_name:          Optional[str] = Field(None, min_length=2, max_length=150)
    phone:              Optional[str] = None
    avatar_url:         Optional[str] = None
    ward_id:            Optional[int] = None
    city:               Optional[str] = None
    preferred_language: Optional[str] = None


class UserStatusUpdateRequest(BaseModel):
    status: UserStatus
    reason: Optional[str] = None


# ─── Complaint ────────────────────────────────────────────────────────────────

class ComplaintCreateRequest(BaseModel):
    title:       str          = Field(min_length=5, max_length=255)
    description: str          = Field(min_length=10)
    category:    IssueCategory
    severity:    SeverityLevel = SeverityLevel.MEDIUM
    latitude:    float         = Field(ge=-90.0, le=90.0)
    longitude:   float         = Field(ge=-180.0, le=180.0)
    address:     Optional[str] = None
    ward_id:     Optional[int] = None
    landmark:    Optional[str] = Field(None, max_length=255)
    tags:        Optional[List[str]] = None

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        return v.strip()


class ComplaintUpdateRequest(BaseModel):
    title:       Optional[str]          = Field(None, min_length=5, max_length=255)
    description: Optional[str]          = Field(None, min_length=10)
    severity:    Optional[SeverityLevel] = None
    address:     Optional[str]          = None
    ward_id:     Optional[int]          = None
    landmark:    Optional[str]          = None
    tags:        Optional[List[str]]    = None


class StatusUpdateRequest(BaseModel):
    status:     ComplaintStatus
    notes:      Optional[str]      = None
    officer_id: Optional[uuid.UUID] = None


class AssignOfficerRequest(BaseModel):
    officer_id: uuid.UUID


class BulkAssignRequest(BaseModel):
    complaint_ids: List[uuid.UUID] = Field(min_length=1, max_length=100)
    officer_id:    uuid.UUID


class VerifyResolutionRequest(BaseModel):
    is_resolved: bool
    feedback:    Optional[str] = None
    rating:      Optional[int] = Field(None, ge=1, le=5)


class ComplaintImageOut(BaseSchema):
    id:               uuid.UUID
    cdn_url:          Optional[str]
    thumbnail_url:    Optional[str]
    is_primary:       bool
    is_resolution:    bool
    caption:          Optional[str]
    bounding_boxes:   Optional[Any]
    created_at:       datetime


class StatusHistoryOut(BaseSchema):
    id:           uuid.UUID
    from_status:  Optional[ComplaintStatus]
    to_status:    ComplaintStatus
    notes:        Optional[str]
    changed_by:   UserOut
    created_at:   datetime


class AIAnalysisOut(BaseSchema):
    id:                    uuid.UUID
    detected_category:     Optional[IssueCategory]
    confidence_score:      float
    severity_predicted:    SeverityLevel
    generated_description: Optional[str]
    is_duplicate:          bool
    model_name:            str
    model_version:         str
    inference_time_ms:     Optional[int]
    created_at:            datetime


class ResolutionOut(BaseSchema):
    id:               uuid.UUID
    officer_id:       uuid.UUID
    resolution_type:  Optional[str]
    work_done:        str
    estimated_cost:   Optional[float]
    actual_cost:      Optional[float]
    scheduled_date:   Optional[date]
    started_at:       Optional[datetime]
    completed_at:     Optional[datetime]
    citizen_rating:   Optional[int]
    citizen_feedback: Optional[str]
    created_at:       datetime


class ComplaintOut(BaseSchema):
    id:                  uuid.UUID
    complaint_number:    str
    citizen_id:          uuid.UUID
    citizen:             UserOut
    officer_id:          Optional[uuid.UUID]
    officer:             Optional[Any]   # OfficerOut — avoids circular import
    category:            IssueCategory
    status:              ComplaintStatus
    severity:            SeverityLevel
    priority_score:      float
    latitude:            float
    longitude:           float
    address:             Optional[str]
    ward_id:             Optional[int]
    landmark:            Optional[str]
    title:               str
    description:         str
    ai_description:      Optional[str]
    tags:                Optional[List[str]]
    is_duplicate:        bool
    parent_complaint_id: Optional[uuid.UUID]
    support_count:       int
    ai_confidence:       Optional[float]
    sla_deadline:        Optional[datetime]
    sla_breached:        bool
    resolved_at:         Optional[datetime]
    citizen_verified:    bool
    citizen_rating:      Optional[int]
    images:              List[ComplaintImageOut]
    status_history:      List[StatusHistoryOut]
    ai_analysis:         Optional[AIAnalysisOut]
    resolution:          Optional[ResolutionOut]
    created_at:          datetime
    updated_at:          datetime


class ComplaintListOut(BaseSchema):
    """Lightweight schema for list endpoints (no heavy relations)."""
    id:               uuid.UUID
    complaint_number: str
    title:            str
    category:         IssueCategory
    status:           ComplaintStatus
    severity:         SeverityLevel
    address:          Optional[str]
    ward_id:          Optional[int]
    support_count:    int
    sla_breached:     bool
    ai_confidence:    Optional[float]
    is_duplicate:     bool
    citizen_id:       uuid.UUID
    officer_id:       Optional[uuid.UUID]
    created_at:       datetime
    updated_at:       datetime


# ─── Officer ──────────────────────────────────────────────────────────────────

class OfficerCreateRequest(BaseModel):
    full_name:   str       = Field(min_length=2, max_length=150)
    email:       EmailStr
    phone:       str       = Field(min_length=10, max_length=15)
    password:    str       = Field(min_length=8)
    badge_number: str      = Field(min_length=3, max_length=50)
    department:  str       = Field(min_length=2, max_length=150)
    designation: Optional[str] = None
    ward_ids:    List[int] = Field(default_factory=list)
    category_ids: List[int] = Field(default_factory=list)
    max_complaints: int    = Field(default=20, ge=1, le=100)


class OfficerUpdateRequest(BaseModel):
    department:     Optional[str]      = None
    designation:    Optional[str]      = None
    ward_ids:       Optional[List[int]]= None
    category_ids:   Optional[List[int]]= None
    is_available:   Optional[bool]     = None
    max_complaints: Optional[int]      = Field(None, ge=1, le=100)


class OfficerOut(BaseSchema):
    id:                  uuid.UUID
    user_id:             uuid.UUID
    user:                UserOut
    badge_number:        str
    department:          str
    designation:         Optional[str]
    ward_ids:            List[int]
    category_ids:        List[int]
    is_available:        bool
    max_complaints:      int
    total_assigned:      int
    total_resolved:      int
    avg_resolution_days: Optional[float]
    performance_score:   float
    created_at:          datetime


# ─── Notification ─────────────────────────────────────────────────────────────

class NotificationOut(BaseSchema):
    id:          uuid.UUID
    type:        NotificationType
    title:       str
    body:        str
    channel:     NotificationChannel
    status:      NotificationStatus
    complaint_id: Optional[uuid.UUID]
    data:        Optional[Any]
    read_at:     Optional[datetime]
    created_at:  datetime


class NotificationReadRequest(BaseModel):
    notification_ids: Optional[List[uuid.UUID]] = None  # None = mark all


# ─── Report ───────────────────────────────────────────────────────────────────

class ReportCreateRequest(BaseModel):
    type:        ReportType
    title:       str         = Field(min_length=3, max_length=255)
    description: Optional[str] = None
    parameters:  dict        = Field(default_factory=dict)
    file_format: str         = Field(default="pdf", pattern="^(pdf|xlsx|csv)$")
    email_to:    Optional[List[EmailStr]] = None


class ReportOut(BaseSchema):
    id:           uuid.UUID
    type:         ReportType
    title:        str
    status:       ReportStatus
    cdn_url:      Optional[str]
    file_format:  str
    file_size_bytes: Optional[int]
    summary:      Optional[Any]
    queued_at:    datetime
    completed_at: Optional[datetime]
    expires_at:   Optional[datetime]


# ─── Analytics ────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_complaints:     int
    open_complaints:      int
    resolved_today:       int
    avg_resolution_days:  Optional[float]
    sla_breach_rate:      float
    citizen_satisfaction: Optional[float]
    total_citizens:       int
    active_officers:      int
    change_vs_prev_week: dict


class CategoryCount(BaseModel):
    category:   IssueCategory
    count:      int
    resolved:   int
    pending:    int
    percentage: float


class MonthlyTrend(BaseModel):
    month:     str
    submitted: int
    resolved:  int
    pending:   int


class WardSummary(BaseModel):
    ward_id:          int
    ward_name:        str
    total_complaints: int
    resolved:         int
    pending:          int
    resolution_rate:  float
    lat:              Optional[float]
    lng:              Optional[float]


class HeatmapPoint(BaseModel):
    lat:    float
    lng:    float
    weight: float


class SeverityDistribution(BaseModel):
    severity:   SeverityLevel
    count:      int
    percentage: float


class OfficerPerformance(BaseModel):
    officer_id:          uuid.UUID
    officer_name:        str
    badge_number:        str
    total_assigned:      int
    total_resolved:      int
    avg_resolution_days: Optional[float]
    performance_score:   float
    satisfaction_rating: Optional[float]


# ─── Resolution creation ─────────────────────────────────────────────────────

class ResolutionCreateRequest(BaseModel):
    complaint_id:    uuid.UUID
    resolution_type: Optional[str] = None
    work_done:       str           = Field(min_length=10)
    materials_used:  Optional[str] = None
    estimated_cost:  Optional[float] = Field(None, ge=0)
    actual_cost:     Optional[float] = Field(None, ge=0)
    scheduled_date:  Optional[date]  = None


# ─── Complaint filters ────────────────────────────────────────────────────────

class ComplaintFilters(BaseModel):
    status:     Optional[ComplaintStatus]  = None
    severity:   Optional[SeverityLevel]    = None
    category:   Optional[IssueCategory]    = None
    ward_id:    Optional[int]              = None
    officer_id: Optional[uuid.UUID]        = None
    date_from:  Optional[datetime]         = None
    date_to:    Optional[datetime]         = None
    search:     Optional[str]              = Field(None, max_length=200)
    is_duplicate: Optional[bool]           = None
    sla_breached: Optional[bool]           = None
    page:       int                        = Field(default=1, ge=1)
    page_size:  int                        = Field(default=20, ge=1, le=100)
    sort_by:    str                        = "created_at"
    sort_order: str                        = Field(default="desc", pattern="^(asc|desc)$")

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        allowed = {"created_at", "updated_at", "severity", "status", "priority_score", "support_count"}
        if v not in allowed:
            raise ValueError(f"sort_by must be one of: {', '.join(allowed)}")
        return v
