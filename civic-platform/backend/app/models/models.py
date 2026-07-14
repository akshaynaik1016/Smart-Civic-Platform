"""
SQLAlchemy ORM models for the Smart Civic Intelligence Platform.
Maps directly to the PostgreSQL schema defined in 001_schema.sql.
"""

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime,
    ForeignKey, Integer, Numeric, SmallInteger, String, Text,
    text, Enum as SAEnum, ARRAY,
)
from sqlalchemy.dialects.postgresql import JSONB, INET
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

    email:                Mapped[str]                = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone:                Mapped[Optional[str]]      = mapped_column(String(20), unique=True, index=True)
    password_hash:        Mapped[str]                = mapped_column(String(255), nullable=False)
    full_name:            Mapped[str]                = mapped_column(String(150), nullable=False)
    role:                 Mapped[UserRole]           = mapped_column(SAEnum(UserRole), nullable=False, default=UserRole.CITIZEN)
    status:               Mapped[UserStatus]         = mapped_column(SAEnum(UserStatus), nullable=False, default=UserStatus.PENDING_VERIFICATION)
    avatar_url:           Mapped[Optional[str]]      = mapped_column(Text)
    ward_id:              Mapped[Optional[int]]      = mapped_column(Integer)
    city:                 Mapped[str]                = mapped_column(String(100), default="Hubballi")
    state:                Mapped[str]                = mapped_column(String(100), default="Karnataka")
    pincode:              Mapped[Optional[str]]      = mapped_column(String(10))
    email_verified:       Mapped[bool]               = mapped_column(Boolean, default=False, nullable=False)
    phone_verified:       Mapped[bool]               = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    phone_verified_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    date_of_birth:        Mapped[Optional[date]]     = mapped_column(Date)
    preferred_language:   Mapped[str]                = mapped_column(String(10), default="en")
    total_complaints:     Mapped[int]                = mapped_column(Integer, default=0, nullable=False)
    resolved_complaints:  Mapped[int]                = mapped_column(Integer, default=0, nullable=False)
    reputation_score:     Mapped[float]              = mapped_column(Numeric(5, 2), default=0.0, nullable=False)
    last_login_at:        Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_active_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at:           Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    complaints:      Mapped[list["Complaint"]]    = relationship("Complaint", back_populates="citizen", foreign_keys="[Complaint.citizen_id]")
    notifications:   Mapped[list["Notification"]] = relationship("Notification", back_populates="recipient")
    officer_profile: Mapped[Optional["Officer"]]  = relationship("Officer", back_populates="user", uselist=False)
    audit_logs:      Mapped[list["AuditLog"]]     = relationship("AuditLog", back_populates="user")


# ─── Category ─────────────────────────────────────────────────────────────────

class Category(Base):
    __tablename__ = "categories"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:         Mapped[IssueCategory] = mapped_column(SAEnum(IssueCategory), unique=True, nullable=False)
    display_name: Mapped[str]           = mapped_column(String(100), nullable=False)
    description:  Mapped[Optional[str]] = mapped_column(Text)
    icon_url:     Mapped[Optional[str]] = mapped_column(Text)
    color_hex:    Mapped[str]           = mapped_column(String(7), default="#FF6B35")
    sla_hours:    Mapped[int]           = mapped_column(Integer, default=48, nullable=False)
    is_active:    Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    sort_order:   Mapped[int]           = mapped_column(Integer, default=0, nullable=False)

    complaints: Mapped[list["Complaint"]] = relationship("Complaint", back_populates="category_obj")


# ─── Officer ──────────────────────────────────────────────────────────────────

class Officer(Base):
    __tablename__ = "officers"

    user_id:             Mapped[str]             = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    badge_number:        Mapped[str]             = mapped_column(String(50), unique=True, nullable=False)
    department:          Mapped[str]             = mapped_column(String(150), nullable=False)
    designation:         Mapped[Optional[str]]   = mapped_column(String(150))
    ward_ids:            Mapped[list[int]]       = mapped_column(ARRAY(Integer), default=list)
    category_ids:        Mapped[list[int]]       = mapped_column(ARRAY(Integer), default=list)
    is_available:        Mapped[bool]            = mapped_column(Boolean, default=True, nullable=False)
    max_complaints:      Mapped[int]             = mapped_column(Integer, default=20, nullable=False)
    total_assigned:      Mapped[int]             = mapped_column(Integer, default=0, nullable=False)
    total_resolved:      Mapped[int]             = mapped_column(Integer, default=0, nullable=False)
    avg_resolution_days: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    performance_score:   Mapped[float]           = mapped_column(Numeric(5, 2), default=0.0, nullable=False)
    deleted_at:          Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user:        Mapped["User"]             = relationship("User", back_populates="officer_profile")
    complaints:  Mapped[list["Complaint"]]  = relationship("Complaint", back_populates="officer", foreign_keys="[Complaint.officer_id]")
    resolutions: Mapped[list["Resolution"]] = relationship("Resolution", back_populates="officer")


# ─── Complaint ────────────────────────────────────────────────────────────────

class Complaint(Base):
    __tablename__ = "complaints"

    complaint_number:     Mapped[str]                 = mapped_column(String(20), unique=True, nullable=False)
    citizen_id:           Mapped[str]                 = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    officer_id:           Mapped[Optional[str]]       = mapped_column(String(36), ForeignKey("officers.id"))
    category_id:          Mapped[int]                 = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    status:               Mapped[ComplaintStatus]     = mapped_column(SAEnum(ComplaintStatus), default=ComplaintStatus.SUBMITTED, nullable=False)
    severity:             Mapped[SeverityLevel]       = mapped_column(SAEnum(SeverityLevel), default=SeverityLevel.MEDIUM, nullable=False)
    priority_score:       Mapped[float]               = mapped_column(Numeric(5, 2), default=0.0)
    latitude:             Mapped[float]               = mapped_column(Numeric(10, 7), nullable=False)
    longitude:            Mapped[float]               = mapped_column(Numeric(10, 7), nullable=False)
    address:              Mapped[Optional[str]]       = mapped_column(Text)
    ward_id:              Mapped[Optional[int]]       = mapped_column(Integer)
    landmark:             Mapped[Optional[str]]       = mapped_column(String(255))
    title:                Mapped[str]                 = mapped_column(String(255), nullable=False)
    description:          Mapped[str]                 = mapped_column(Text, nullable=False)
    ai_description:       Mapped[Optional[str]]       = mapped_column(Text)
    tags:                 Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    is_duplicate:         Mapped[bool]                = mapped_column(Boolean, default=False, nullable=False)
    parent_complaint_id:  Mapped[Optional[str]]       = mapped_column(String(36), ForeignKey("complaints.id"))
    support_count:        Mapped[int]                 = mapped_column(Integer, default=0, nullable=False)
    ai_confidence:        Mapped[Optional[float]]     = mapped_column(Numeric(5, 4))
    ai_processed_at:      Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))
    ai_model_version:     Mapped[Optional[str]]       = mapped_column(String(50))
    resolved_at:          Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))
    resolution_notes:     Mapped[Optional[str]]       = mapped_column(Text)
    citizen_verified:     Mapped[bool]                = mapped_column(Boolean, default=False)
    citizen_verified_at:  Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))
    citizen_rating:       Mapped[Optional[int]]       = mapped_column(SmallInteger)
    sla_deadline:         Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))
    sla_breached:         Mapped[bool]                = mapped_column(Boolean, default=False, nullable=False)
    is_flagged:           Mapped[bool]                = mapped_column(Boolean, default=False, nullable=False)
    flag_reason:          Mapped[Optional[str]]       = mapped_column(Text)
    closed_reason:        Mapped[Optional[str]]       = mapped_column(Text)
    deleted_at:           Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))

    citizen:        Mapped["User"]                         = relationship("User", back_populates="complaints", foreign_keys=[citizen_id])
    officer:        Mapped[Optional["Officer"]]            = relationship("Officer", back_populates="complaints", foreign_keys=[officer_id])
    category_obj:   Mapped["Category"]                    = relationship("Category", back_populates="complaints")
    @property
    def category(self) -> Optional[IssueCategory]:
        return self.category_obj.name if self.category_obj else None
    images:         Mapped[list["ComplaintImage"]]         = relationship("ComplaintImage", back_populates="complaint", cascade="all, delete-orphan")
    status_history: Mapped[list["ComplaintStatusHistory"]] = relationship("ComplaintStatusHistory", back_populates="complaint", order_by="ComplaintStatusHistory.created_at")
    ai_analysis:    Mapped[Optional["AIAnalysis"]]         = relationship("AIAnalysis", back_populates="complaint", uselist=False)
    resolution:     Mapped[Optional["Resolution"]]         = relationship("Resolution", back_populates="complaint", uselist=False)
    notifications:  Mapped[list["Notification"]]           = relationship("Notification", back_populates="complaint")
    supporters:     Mapped[list["ComplaintSupporter"]]     = relationship("ComplaintSupporter", back_populates="complaint")
    parent:         Mapped[Optional["Complaint"]]          = relationship("Complaint", remote_side="Complaint.id", foreign_keys=[parent_complaint_id])


# ─── ComplaintImage ───────────────────────────────────────────────────────────

class ComplaintImage(Base):
    __tablename__ = "complaint_images"

    complaint_id:      Mapped[str]               = mapped_column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    uploader_id:       Mapped[str]               = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    s3_key:            Mapped[str]               = mapped_column(String(512), unique=True, nullable=False)
    s3_bucket:         Mapped[str]               = mapped_column(String(255), nullable=False)
    cdn_url:           Mapped[Optional[str]]     = mapped_column(Text)
    thumbnail_url:     Mapped[Optional[str]]     = mapped_column(Text)
    original_filename: Mapped[Optional[str]]     = mapped_column(String(255))
    mime_type:         Mapped[str]               = mapped_column(String(100), default="image/jpeg", nullable=False)
    file_size_bytes:   Mapped[Optional[int]]     = mapped_column(BigInteger)
    width_px:          Mapped[Optional[int]]     = mapped_column(Integer)
    height_px:         Mapped[Optional[int]]     = mapped_column(Integer)
    image_hash:        Mapped[str]               = mapped_column(String(64), nullable=False)
    is_primary:        Mapped[bool]              = mapped_column(Boolean, default=False, nullable=False)
    is_resolution:     Mapped[bool]              = mapped_column(Boolean, default=False, nullable=False)
    caption:           Mapped[Optional[str]]     = mapped_column(Text)
    bounding_boxes:    Mapped[Optional[dict]]    = mapped_column(JSONB)
    exif_lat:          Mapped[Optional[float]]   = mapped_column(Numeric(10, 7))
    exif_lng:          Mapped[Optional[float]]   = mapped_column(Numeric(10, 7))
    exif_captured_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="images")
    uploader:  Mapped["User"]      = relationship("User", foreign_keys=[uploader_id])


# ─── AIAnalysis ───────────────────────────────────────────────────────────────

class AIAnalysis(Base):
    __tablename__ = "ai_analysis"

    complaint_id:          Mapped[str]                    = mapped_column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    image_id:              Mapped[Optional[str]]          = mapped_column(String(36), ForeignKey("complaint_images.id"))
    detected_category:     Mapped[Optional[IssueCategory]] = mapped_column(SAEnum(IssueCategory))
    confidence_score:      Mapped[float]                   = mapped_column(Numeric(5, 4), nullable=False)
    severity_predicted:    Mapped[SeverityLevel]           = mapped_column(SAEnum(SeverityLevel), nullable=False)
    severity_confidence:   Mapped[Optional[float]]         = mapped_column(Numeric(5, 4))
    bounding_boxes:        Mapped[Optional[dict]]          = mapped_column(JSONB)
    generated_description: Mapped[Optional[str]]           = mapped_column(Text)
    description_model:     Mapped[Optional[str]]           = mapped_column(String(100))
    duplicate_checked:     Mapped[bool]                    = mapped_column(Boolean, default=False, nullable=False)
    is_duplicate:          Mapped[bool]                    = mapped_column(Boolean, default=False, nullable=False)
    similar_complaint_ids: Mapped[Optional[list[str]]]     = mapped_column(ARRAY(String(36)))
    similarity_score:      Mapped[Optional[float]]         = mapped_column(Numeric(5, 4))
    model_name:            Mapped[str]                     = mapped_column(String(100), default="yolov8n", nullable=False)
    model_version:         Mapped[str]                     = mapped_column(String(50), default="v1.0.0", nullable=False)
    inference_time_ms:     Mapped[Optional[int]]           = mapped_column(Integer)
    raw_output:            Mapped[Optional[dict]]          = mapped_column(JSONB)
    processing_status:     Mapped[str]                     = mapped_column(String(50), default="completed", nullable=False)
    error_message:         Mapped[Optional[str]]           = mapped_column(Text)

    complaint: Mapped["Complaint"]               = relationship("Complaint", back_populates="ai_analysis")
    image:     Mapped[Optional["ComplaintImage"]] = relationship("ComplaintImage", foreign_keys=[image_id])


# ─── Resolution ───────────────────────────────────────────────────────────────

class Resolution(Base):
    __tablename__ = "resolutions"

    complaint_id:     Mapped[str]                 = mapped_column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), unique=True, nullable=False)
    officer_id:       Mapped[str]                 = mapped_column(String(36), ForeignKey("officers.id"), nullable=False)
    resolution_type:  Mapped[Optional[str]]       = mapped_column(String(100))
    work_done:        Mapped[str]                 = mapped_column(Text, nullable=False)
    materials_used:   Mapped[Optional[str]]       = mapped_column(Text)
    contractor_name:  Mapped[Optional[str]]       = mapped_column(String(200))
    estimated_cost:   Mapped[Optional[float]]     = mapped_column(Numeric(12, 2))
    actual_cost:      Mapped[Optional[float]]     = mapped_column(Numeric(12, 2))
    before_image_ids: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(36)))
    after_image_ids:  Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(36)))
    scheduled_date:   Mapped[Optional[date]]      = mapped_column(Date)
    started_at:       Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))
    completed_at:     Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))
    citizen_feedback: Mapped[Optional[str]]       = mapped_column(Text)
    citizen_rating:   Mapped[Optional[int]]       = mapped_column(SmallInteger)
    citizen_rated_at: Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))

    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="resolution")
    officer:   Mapped["Officer"]   = relationship("Officer", back_populates="resolutions")


# ─── Notification ─────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    recipient_id:   Mapped[str]                  = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    complaint_id:   Mapped[Optional[str]]        = mapped_column(String(36), ForeignKey("complaints.id"))
    type:           Mapped[NotificationType]     = mapped_column(SAEnum(NotificationType), nullable=False)
    title:          Mapped[str]                  = mapped_column(String(255), nullable=False)
    body:           Mapped[str]                  = mapped_column(Text, nullable=False)
    data:           Mapped[Optional[dict]]       = mapped_column(JSONB)
    channel:        Mapped[NotificationChannel]  = mapped_column(SAEnum(NotificationChannel), default=NotificationChannel.IN_APP, nullable=False)
    status:         Mapped[NotificationStatus]   = mapped_column(SAEnum(NotificationStatus), default=NotificationStatus.PENDING, nullable=False)
    fcm_message_id: Mapped[Optional[str]]        = mapped_column(String(255))
    sent_at:        Mapped[Optional[datetime]]   = mapped_column(DateTime(timezone=True))
    delivered_at:   Mapped[Optional[datetime]]   = mapped_column(DateTime(timezone=True))
    read_at:        Mapped[Optional[datetime]]   = mapped_column(DateTime(timezone=True))
    failed_reason:  Mapped[Optional[str]]        = mapped_column(Text)
    retry_count:    Mapped[int]                  = mapped_column(SmallInteger, default=0, nullable=False)
    scheduled_for:  Mapped[Optional[datetime]]   = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    recipient: Mapped["User"]               = relationship("User", back_populates="notifications")
    complaint: Mapped[Optional["Complaint"]] = relationship("Complaint", back_populates="notifications")


# ─── ComplaintStatusHistory ───────────────────────────────────────────────────

class ComplaintStatusHistory(Base):
    __tablename__ = "complaint_status_history"

    complaint_id: Mapped[str]                       = mapped_column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    changed_by:   Mapped[str]                       = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    officer_id:   Mapped[Optional[str]]             = mapped_column(String(36), ForeignKey("officers.id"))
    from_status:  Mapped[Optional[ComplaintStatus]] = mapped_column(SAEnum(ComplaintStatus))
    to_status:    Mapped[ComplaintStatus]           = mapped_column(SAEnum(ComplaintStatus), nullable=False)
    notes:        Mapped[Optional[str]]             = mapped_column(Text)
    attachments:  Mapped[Optional[list[str]]]       = mapped_column(ARRAY(String(36)))

    complaint:       Mapped["Complaint"] = relationship("Complaint", back_populates="status_history")
    changed_by_user: Mapped["User"]      = relationship("User", foreign_keys=[changed_by])


# ─── ComplaintSupporter ───────────────────────────────────────────────────────

class ComplaintSupporter(Base):
    __tablename__ = "complaint_supporters"

    complaint_id: Mapped[str] = mapped_column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), primary_key=True)
    user_id:      Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="supporters")
    user:      Mapped["User"]      = relationship("User")


# ─── Report ───────────────────────────────────────────────────────────────────

class Report(Base):
    __tablename__ = "reports"

    generated_by:    Mapped[str]             = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    type:            Mapped[ReportType]      = mapped_column(SAEnum(ReportType), nullable=False)
    title:           Mapped[str]             = mapped_column(String(255), nullable=False)
    description:     Mapped[Optional[str]]   = mapped_column(Text)
    parameters:      Mapped[dict]            = mapped_column(JSONB, default=dict)
    status:          Mapped[ReportStatus]    = mapped_column(SAEnum(ReportStatus), default=ReportStatus.QUEUED, nullable=False)
    s3_key:          Mapped[Optional[str]]   = mapped_column(String(512))
    s3_bucket:       Mapped[Optional[str]]   = mapped_column(String(255))
    cdn_url:         Mapped[Optional[str]]   = mapped_column(Text)
    file_format:     Mapped[str]             = mapped_column(String(20), default="pdf")
    file_size_bytes: Mapped[Optional[int]]   = mapped_column(BigInteger)
    page_count:      Mapped[Optional[int]]   = mapped_column(Integer)
    summary:         Mapped[Optional[dict]]  = mapped_column(JSONB)
    error_message:   Mapped[Optional[str]]   = mapped_column(Text)
    queued_at:       Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)
    started_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    generator: Mapped["User"] = relationship("User", foreign_keys=[generated_by])


# ─── AuditLog ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:            Mapped[int]           = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id:       Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"))
    action:        Mapped[AuditAction]   = mapped_column(SAEnum(AuditAction), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100))
    resource_id:   Mapped[Optional[str]] = mapped_column(String(255))
    old_values:    Mapped[Optional[dict]] = mapped_column(JSONB)
    new_values:    Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address:    Mapped[Optional[str]] = mapped_column(INET)
    user_agent:    Mapped[Optional[str]] = mapped_column(Text)
    request_id:    Mapped[Optional[str]] = mapped_column(String(100))
    success:       Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms:   Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
