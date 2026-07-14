"""
SQLAlchemy ORM models for the Smart Civic Intelligence Platform.
Maps directly to the PostgreSQL schema defined in 001_schema.sql.
"""

import enum
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float,
    ForeignKey, Integer, Numeric, SmallInteger, String, Text,
    text, Enum as SAEnum, ARRAY,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── Python Enums ─────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    CITIZEN = "citizen"
    OFFICER = "officer"
    ADMIN   = "admin"

class UserStatus(str, enum.Enum):
    ACTIVE               = "active"
    INACTIVE             = "inactive"
    SUSPENDED            = "suspended"
    PENDING_VERIFICATION = "pending_verification"

class ComplaintStatus(str, enum.Enum):
    SUBMITTED      = "submitted"
    AI_PROCESSING  = "ai_processing"
    PENDING_REVIEW = "pending_review"
    ASSIGNED       = "assigned"
    IN_PROGRESS    = "in_progress"
    RESOLVED       = "resolved"
    VERIFIED       = "verified"
    CLOSED         = "closed"
    REJECTED       = "rejected"

class SeverityLevel(str, enum.Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

class IssueCategory(str, enum.Enum):
    POTHOLE              = "pothole"
    GARBAGE              = "garbage"
    WATER_LEAKAGE        = "water_leakage"
    OPEN_MANHOLE         = "open_manhole"
    BROKEN_STREETLIGHT   = "broken_streetlight"
    FALLEN_TREE          = "fallen_tree"
    DAMAGED_ROAD_SIGN    = "damaged_road_sign"
    ILLEGAL_DUMPING      = "illegal_dumping"
    OTHER                = "other"

class NotificationType(str, enum.Enum):
    COMPLAINT_SUBMITTED       = "complaint_submitted"
    COMPLAINT_ASSIGNED        = "complaint_assigned"
    COMPLAINT_STATUS_CHANGED  = "complaint_status_changed"
    COMPLAINT_RESOLVED        = "complaint_resolved"
    VERIFICATION_REQUIRED     = "verification_required"
    DUPLICATE_DETECTED        = "duplicate_detected"
    SYSTEM_ANNOUNCEMENT       = "system_announcement"

class NotificationChannel(str, enum.Enum):
    PUSH   = "push"
    EMAIL  = "email"
    SMS    = "sms"
    IN_APP = "in_app"

class NotificationStatus(str, enum.Enum):
    PENDING   = "pending"
    SENT      = "sent"
    DELIVERED = "delivered"
    FAILED    = "failed"
    READ      = "read"

class ReportType(str, enum.Enum):
    DAILY_SUMMARY       = "daily_summary"
    WEEKLY_SUMMARY      = "weekly_summary"
    MONTHLY_SUMMARY     = "monthly_summary"
    CATEGORY_ANALYSIS   = "category_analysis"
    WARD_ANALYSIS       = "ward_analysis"
    OFFICER_PERFORMANCE = "officer_performance"
    RESOLUTION_RATE     = "resolution_rate"
    CUSTOM              = "custom"

class ReportStatus(str, enum.Enum):
    QUEUED     = "queued"
    GENERATING = "generating"
    READY      = "ready"
    FAILED     = "failed"
    EXPIRED    = "expired"

class AuditAction(str, enum.Enum):
    CREATE                = "create"
    READ                  = "read"
    UPDATE                = "update"
    DELETE                = "delete"
    LOGIN                 = "login"
    LOGOUT                = "logout"
    LOGIN_FAILED          = "login_failed"
    PASSWORD_CHANGED      = "password_changed"
    ROLE_CHANGED          = "role_changed"
    COMPLAINT_ASSIGNED    = "complaint_assigned"
    COMPLAINT_RESOLVED    = "complaint_resolved"
    BULK_IMPORT           = "bulk_import"
    EXPORT                = "export"
    SYSTEM_CONFIG_CHANGED = "system_config_changed"


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    email:                str            = Column(String(255), unique=True, nullable=False, index=True)
    phone:                Optional[str]  = Column(String(20),  unique=True, index=True)
    password_hash:        str            = Column(String(255), nullable=False)
    full_name:            str            = Column(String(150), nullable=False)
    role:                 UserRole       = Column(SAEnum(UserRole), nullable=False, default=UserRole.CITIZEN)
    status:               UserStatus     = Column(SAEnum(UserStatus), nullable=False, default=UserStatus.PENDING_VERIFICATION)
    avatar_url:           Optional[str]  = Column(Text)
    ward_id:              Optional[int]  = Column(Integer)
    city:                 str            = Column(String(100), default="Hubballi")
    state:                str            = Column(String(100), default="Karnataka")
    pincode:              Optional[str]  = Column(String(10))
    email_verified:       bool           = Column(Boolean, default=False, nullable=False)
    phone_verified:       bool           = Column(Boolean, default=False, nullable=False)
    email_verified_at:    Optional[datetime] = Column(DateTime(timezone=True))
    phone_verified_at:    Optional[datetime] = Column(DateTime(timezone=True))
    date_of_birth:        Optional[date] = Column(Date)
    preferred_language:   str            = Column(String(10), default="en")
    total_complaints:     int            = Column(Integer, default=0, nullable=False)
    resolved_complaints:  int            = Column(Integer, default=0, nullable=False)
    reputation_score:     float          = Column(Numeric(5, 2), default=0.0, nullable=False)
    last_login_at:        Optional[datetime] = Column(DateTime(timezone=True))
    last_active_at:       Optional[datetime] = Column(DateTime(timezone=True))
    deleted_at:           Optional[datetime] = Column(DateTime(timezone=True))

    # Relationships
    complaints:     List["Complaint"]      = relationship("Complaint", back_populates="citizen", foreign_keys="[Complaint.citizen_id]")
    notifications:  List["Notification"]   = relationship("Notification", back_populates="recipient")
    officer_profile: Optional["Officer"]   = relationship("Officer", back_populates="user", uselist=False)
    audit_logs:     List["AuditLog"]       = relationship("AuditLog", back_populates="user")


# ─── Category ─────────────────────────────────────────────────────────────────

class Category(Base):
    __tablename__ = "categories"

    id:           int           = Column(Integer, primary_key=True, autoincrement=True)
    name:         IssueCategory = Column(SAEnum(IssueCategory), unique=True, nullable=False)
    display_name: str           = Column(String(100), nullable=False)
    description:  Optional[str] = Column(Text)
    icon_url:     Optional[str] = Column(Text)
    color_hex:    str           = Column(String(7), default="#FF6B35")
    sla_hours:    int           = Column(Integer, default=48, nullable=False)
    is_active:    bool          = Column(Boolean, default=True, nullable=False)
    sort_order:   int           = Column(Integer, default=0, nullable=False)

    complaints: List["Complaint"] = relationship("Complaint", back_populates="category_obj")


# ─── Officer ──────────────────────────────────────────────────────────────────

class Officer(Base):
    __tablename__ = "officers"

    user_id:            uuid.UUID     = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    badge_number:       str           = Column(String(50), unique=True, nullable=False)
    department:         str           = Column(String(150), nullable=False)
    designation:        Optional[str] = Column(String(150))
    ward_ids:           List[int]     = Column(ARRAY(Integer), default=list)
    category_ids:       List[int]     = Column(ARRAY(Integer), default=list)
    is_available:       bool          = Column(Boolean, default=True, nullable=False)
    max_complaints:     int           = Column(Integer, default=20, nullable=False)
    total_assigned:     int           = Column(Integer, default=0, nullable=False)
    total_resolved:     int           = Column(Integer, default=0, nullable=False)
    avg_resolution_days: Optional[float] = Column(Numeric(5, 2))
    performance_score:  float         = Column(Numeric(5, 2), default=0.0, nullable=False)
    deleted_at:         Optional[datetime] = Column(DateTime(timezone=True))

    user:        User              = relationship("User", back_populates="officer_profile")
    complaints:  List["Complaint"] = relationship("Complaint", back_populates="officer", foreign_keys="[Complaint.officer_id]")
    resolutions: List["Resolution"] = relationship("Resolution", back_populates="officer")


# ─── Complaint ────────────────────────────────────────────────────────────────

class Complaint(Base):
    __tablename__ = "complaints"

    complaint_number:     str               = Column(String(20), unique=True, nullable=False)
    citizen_id:           uuid.UUID         = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    officer_id:           Optional[uuid.UUID] = Column(UUID(as_uuid=True), ForeignKey("officers.id"))
    category_id:          int               = Column(Integer, ForeignKey("categories.id"), nullable=False)
    status:               ComplaintStatus   = Column(SAEnum(ComplaintStatus), default=ComplaintStatus.SUBMITTED, nullable=False)
    severity:             SeverityLevel     = Column(SAEnum(SeverityLevel), default=SeverityLevel.MEDIUM, nullable=False)
    priority_score:       float             = Column(Numeric(5, 2), default=0.0)
    latitude:             float             = Column(Numeric(10, 7), nullable=False)
    longitude:            float             = Column(Numeric(10, 7), nullable=False)
    address:              Optional[str]     = Column(Text)
    ward_id:              Optional[int]     = Column(Integer)
    landmark:             Optional[str]     = Column(String(255))
    title:                str               = Column(String(255), nullable=False)
    description:          str               = Column(Text, nullable=False)
    ai_description:       Optional[str]     = Column(Text)
    tags:                 Optional[List[str]] = Column(ARRAY(String))
    is_duplicate:         bool              = Column(Boolean, default=False, nullable=False)
    parent_complaint_id:  Optional[uuid.UUID] = Column(UUID(as_uuid=True), ForeignKey("complaints.id"))
    support_count:        int               = Column(Integer, default=0, nullable=False)
    ai_confidence:        Optional[float]   = Column(Numeric(5, 4))
    ai_processed_at:      Optional[datetime] = Column(DateTime(timezone=True))
    ai_model_version:     Optional[str]     = Column(String(50))
    resolved_at:          Optional[datetime] = Column(DateTime(timezone=True))
    resolution_notes:     Optional[str]     = Column(Text)
    citizen_verified:     bool              = Column(Boolean, default=False)
    citizen_verified_at:  Optional[datetime] = Column(DateTime(timezone=True))
    citizen_rating:       Optional[int]     = Column(SmallInteger)
    sla_deadline:         Optional[datetime] = Column(DateTime(timezone=True))
    sla_breached:         bool              = Column(Boolean, default=False, nullable=False)
    is_flagged:           bool              = Column(Boolean, default=False, nullable=False)
    flag_reason:          Optional[str]     = Column(Text)
    closed_reason:        Optional[str]     = Column(Text)
    deleted_at:           Optional[datetime] = Column(DateTime(timezone=True))

    citizen:        User             = relationship("User", back_populates="complaints", foreign_keys=[citizen_id])
    officer:        Optional[Officer] = relationship("Officer", back_populates="complaints", foreign_keys=[officer_id])
    category_obj:   Category         = relationship("Category", back_populates="complaints")
    images:         List["ComplaintImage"]   = relationship("ComplaintImage", back_populates="complaint", cascade="all, delete-orphan")
    status_history: List["ComplaintStatusHistory"] = relationship("ComplaintStatusHistory", back_populates="complaint", order_by="ComplaintStatusHistory.created_at")
    ai_analysis:    Optional["AIAnalysis"]   = relationship("AIAnalysis", back_populates="complaint", uselist=False)
    resolution:     Optional["Resolution"]   = relationship("Resolution", back_populates="complaint", uselist=False)
    notifications:  List["Notification"]     = relationship("Notification", back_populates="complaint")
    supporters:     List["ComplaintSupporter"] = relationship("ComplaintSupporter", back_populates="complaint")
    parent:         Optional["Complaint"]    = relationship("Complaint", remote_side="Complaint.id", foreign_keys=[parent_complaint_id])


# ─── ComplaintImage ───────────────────────────────────────────────────────────

class ComplaintImage(Base):
    __tablename__ = "complaint_images"

    complaint_id:      uuid.UUID    = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    uploader_id:       uuid.UUID    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    s3_key:            str          = Column(String(512), unique=True, nullable=False)
    s3_bucket:         str          = Column(String(255), nullable=False)
    cdn_url:           Optional[str]= Column(Text)
    thumbnail_url:     Optional[str]= Column(Text)
    original_filename: Optional[str]= Column(String(255))
    mime_type:         str          = Column(String(100), default="image/jpeg", nullable=False)
    file_size_bytes:   Optional[int]= Column(BigInteger)
    width_px:          Optional[int]= Column(Integer)
    height_px:         Optional[int]= Column(Integer)
    image_hash:        str          = Column(String(64), nullable=False)
    is_primary:        bool         = Column(Boolean, default=False, nullable=False)
    is_resolution:     bool         = Column(Boolean, default=False, nullable=False)
    caption:           Optional[str]= Column(Text)
    bounding_boxes:    Optional[dict]= Column(JSONB)
    exif_lat:          Optional[float]= Column(Numeric(10, 7))
    exif_lng:          Optional[float]= Column(Numeric(10, 7))
    exif_captured_at:  Optional[datetime]= Column(DateTime(timezone=True))

    complaint: Complaint = relationship("Complaint", back_populates="images")
    uploader:  User      = relationship("User", foreign_keys=[uploader_id])


# ─── AIAnalysis ───────────────────────────────────────────────────────────────

class AIAnalysis(Base):
    __tablename__ = "ai_analysis"

    complaint_id:         uuid.UUID         = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    image_id:             Optional[uuid.UUID]= Column(UUID(as_uuid=True), ForeignKey("complaint_images.id"))
    detected_category:    Optional[IssueCategory] = Column(SAEnum(IssueCategory))
    confidence_score:     float             = Column(Numeric(5, 4), nullable=False)
    severity_predicted:   SeverityLevel     = Column(SAEnum(SeverityLevel), nullable=False)
    severity_confidence:  Optional[float]   = Column(Numeric(5, 4))
    bounding_boxes:       Optional[dict]    = Column(JSONB)
    generated_description: Optional[str]   = Column(Text)
    description_model:    Optional[str]    = Column(String(100))
    duplicate_checked:    bool             = Column(Boolean, default=False, nullable=False)
    is_duplicate:         bool             = Column(Boolean, default=False, nullable=False)
    similar_complaint_ids: Optional[List[str]] = Column(ARRAY(UUID(as_uuid=True)))
    similarity_score:     Optional[float]  = Column(Numeric(5, 4))
    model_name:           str              = Column(String(100), default="yolov8n", nullable=False)
    model_version:        str              = Column(String(50), default="v1.0.0", nullable=False)
    inference_time_ms:    Optional[int]    = Column(Integer)
    raw_output:           Optional[dict]   = Column(JSONB)
    processing_status:    str              = Column(String(50), default="completed", nullable=False)
    error_message:        Optional[str]    = Column(Text)

    complaint: Complaint = relationship("Complaint", back_populates="ai_analysis")
    image:     Optional[ComplaintImage] = relationship("ComplaintImage", foreign_keys=[image_id])


# ─── Resolution ───────────────────────────────────────────────────────────────

class Resolution(Base):
    __tablename__ = "resolutions"

    complaint_id:      uuid.UUID    = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), unique=True, nullable=False)
    officer_id:        uuid.UUID    = Column(UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False)
    resolution_type:   Optional[str]= Column(String(100))
    work_done:         str          = Column(Text, nullable=False)
    materials_used:    Optional[str]= Column(Text)
    contractor_name:   Optional[str]= Column(String(200))
    estimated_cost:    Optional[float]= Column(Numeric(12, 2))
    actual_cost:       Optional[float]= Column(Numeric(12, 2))
    before_image_ids:  Optional[list]= Column(ARRAY(UUID(as_uuid=True)))
    after_image_ids:   Optional[list]= Column(ARRAY(UUID(as_uuid=True)))
    scheduled_date:    Optional[date]= Column(Date)
    started_at:        Optional[datetime]= Column(DateTime(timezone=True))
    completed_at:      Optional[datetime]= Column(DateTime(timezone=True))
    citizen_feedback:  Optional[str]= Column(Text)
    citizen_rating:    Optional[int]= Column(SmallInteger)
    citizen_rated_at:  Optional[datetime]= Column(DateTime(timezone=True))

    complaint: Complaint = relationship("Complaint", back_populates="resolution")
    officer:   Officer   = relationship("Officer", back_populates="resolutions")


# ─── Notification ─────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    recipient_id:  uuid.UUID          = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    complaint_id:  Optional[uuid.UUID]= Column(UUID(as_uuid=True), ForeignKey("complaints.id"))
    type:          NotificationType   = Column(SAEnum(NotificationType), nullable=False)
    title:         str                = Column(String(255), nullable=False)
    body:          str                = Column(Text, nullable=False)
    data:          Optional[dict]     = Column(JSONB)
    channel:       NotificationChannel= Column(SAEnum(NotificationChannel), default=NotificationChannel.IN_APP, nullable=False)
    status:        NotificationStatus = Column(SAEnum(NotificationStatus), default=NotificationStatus.PENDING, nullable=False)
    fcm_message_id: Optional[str]    = Column(String(255))
    sent_at:       Optional[datetime] = Column(DateTime(timezone=True))
    delivered_at:  Optional[datetime] = Column(DateTime(timezone=True))
    read_at:       Optional[datetime] = Column(DateTime(timezone=True))
    failed_reason: Optional[str]     = Column(Text)
    retry_count:   int               = Column(SmallInteger, default=0, nullable=False)
    scheduled_for: Optional[datetime] = Column(DateTime(timezone=True), server_default=text("NOW()"))

    recipient: User              = relationship("User", back_populates="notifications")
    complaint: Optional[Complaint] = relationship("Complaint", back_populates="notifications")


# ─── ComplaintStatusHistory ───────────────────────────────────────────────────

class ComplaintStatusHistory(Base):
    __tablename__ = "complaint_status_history"

    complaint_id: uuid.UUID            = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    changed_by:   uuid.UUID            = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    officer_id:   Optional[uuid.UUID]  = Column(UUID(as_uuid=True), ForeignKey("officers.id"))
    from_status:  Optional[ComplaintStatus] = Column(SAEnum(ComplaintStatus))
    to_status:    ComplaintStatus      = Column(SAEnum(ComplaintStatus), nullable=False)
    notes:        Optional[str]        = Column(Text)
    attachments:  Optional[list]       = Column(ARRAY(UUID(as_uuid=True)))

    complaint:  Complaint = relationship("Complaint", back_populates="status_history")
    changed_by_user: User = relationship("User", foreign_keys=[changed_by])


# ─── ComplaintSupporter ───────────────────────────────────────────────────────

class ComplaintSupporter(Base):
    __tablename__ = "complaint_supporters"

    complaint_id: uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), primary_key=True)
    user_id:      uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    complaint: Complaint = relationship("Complaint", back_populates="supporters")
    user:      User      = relationship("User")


# ─── Report ───────────────────────────────────────────────────────────────────

class Report(Base):
    __tablename__ = "reports"

    generated_by:   uuid.UUID    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type:           ReportType   = Column(SAEnum(ReportType), nullable=False)
    title:          str          = Column(String(255), nullable=False)
    description:    Optional[str]= Column(Text)
    parameters:     dict         = Column(JSONB, default=dict)
    status:         ReportStatus = Column(SAEnum(ReportStatus), default=ReportStatus.QUEUED, nullable=False)
    s3_key:         Optional[str]= Column(String(512))
    s3_bucket:      Optional[str]= Column(String(255))
    cdn_url:        Optional[str]= Column(Text)
    file_format:    str          = Column(String(20), default="pdf")
    file_size_bytes: Optional[int]= Column(BigInteger)
    page_count:     Optional[int]= Column(Integer)
    summary:        Optional[dict]= Column(JSONB)
    error_message:  Optional[str]= Column(Text)
    queued_at:      datetime     = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)
    started_at:     Optional[datetime]= Column(DateTime(timezone=True))
    completed_at:   Optional[datetime]= Column(DateTime(timezone=True))
    expires_at:     Optional[datetime]= Column(DateTime(timezone=True))

    generator: User = relationship("User", foreign_keys=[generated_by])


# ─── AuditLog ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:            int                 = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id:       Optional[uuid.UUID] = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action:        AuditAction         = Column(SAEnum(AuditAction), nullable=False)
    resource_type: Optional[str]       = Column(String(100))
    resource_id:   Optional[str]       = Column(String(255))
    old_values:    Optional[dict]      = Column(JSONB)
    new_values:    Optional[dict]      = Column(JSONB)
    ip_address:    Optional[str]       = Column(INET)
    user_agent:    Optional[str]       = Column(Text)
    request_id:    Optional[str]       = Column(String(100))
    success:       bool                = Column(Boolean, default=True, nullable=False)
    error_message: Optional[str]       = Column(Text)
    duration_ms:   Optional[int]       = Column(Integer)

    user: Optional[User] = relationship("User", back_populates="audit_logs")
