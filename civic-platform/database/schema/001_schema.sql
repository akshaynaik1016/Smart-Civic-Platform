-- ============================================================
-- Smart Civic Intelligence Platform — PostgreSQL Schema
-- Version : 1.0.0
-- Encoding: UTF-8
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";       -- UUID generation
CREATE EXTENSION IF NOT EXISTS "postgis";          -- Geospatial queries
CREATE EXTENSION IF NOT EXISTS "pg_trgm";          -- Trigram fuzzy search
CREATE EXTENSION IF NOT EXISTS "btree_gist";       -- GiST index for exclusion constraints
CREATE EXTENSION IF NOT EXISTS "unaccent";         -- Accent-insensitive search

-- ============================================================
-- ENUMERATIONS
-- ============================================================

CREATE TYPE user_role AS ENUM ('citizen', 'officer', 'admin');
CREATE TYPE user_status AS ENUM ('active', 'inactive', 'suspended', 'pending_verification');

CREATE TYPE complaint_status AS ENUM (
    'submitted',        -- Just filed by citizen
    'ai_processing',    -- AI analysis in progress
    'pending_review',   -- Awaiting officer assignment
    'assigned',         -- Assigned to an officer
    'in_progress',      -- Officer actively working on it
    'resolved',         -- Issue fixed, pending citizen verification
    'verified',         -- Citizen confirmed resolution
    'closed',           -- Admin closed (duplicate / invalid)
    'rejected'          -- Rejected with reason
);

CREATE TYPE severity_level AS ENUM ('low', 'medium', 'high', 'critical');

CREATE TYPE issue_category AS ENUM (
    'pothole',
    'garbage',
    'water_leakage',
    'open_manhole',
    'broken_streetlight',
    'fallen_tree',
    'damaged_road_sign',
    'illegal_dumping',
    'other'
);

CREATE TYPE notification_type AS ENUM (
    'complaint_submitted',
    'complaint_assigned',
    'complaint_status_changed',
    'complaint_resolved',
    'verification_required',
    'duplicate_detected',
    'system_announcement'
);

CREATE TYPE notification_channel AS ENUM ('push', 'email', 'sms', 'in_app');
CREATE TYPE notification_status AS ENUM ('pending', 'sent', 'delivered', 'failed', 'read');

CREATE TYPE report_type AS ENUM (
    'daily_summary',
    'weekly_summary',
    'monthly_summary',
    'category_analysis',
    'ward_analysis',
    'officer_performance',
    'resolution_rate',
    'custom'
);

CREATE TYPE report_status AS ENUM ('queued', 'generating', 'ready', 'failed', 'expired');

CREATE TYPE audit_action AS ENUM (
    'create', 'read', 'update', 'delete',
    'login', 'logout', 'login_failed',
    'password_changed', 'role_changed',
    'complaint_assigned', 'complaint_resolved',
    'bulk_import', 'export', 'system_config_changed'
);

-- ============================================================
-- TABLE 1 — USERS
-- ============================================================

CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email               VARCHAR(255) NOT NULL,
    phone               VARCHAR(20),
    password_hash       VARCHAR(255) NOT NULL,
    full_name           VARCHAR(150) NOT NULL,
    role                user_role NOT NULL DEFAULT 'citizen',
    status              user_status NOT NULL DEFAULT 'pending_verification',
    avatar_url          TEXT,

    -- Address / Location
    ward_id             INTEGER,
    city                VARCHAR(100) DEFAULT 'Hubballi',
    state               VARCHAR(100) DEFAULT 'Karnataka',
    pincode             VARCHAR(10),

    -- Verification
    email_verified      BOOLEAN NOT NULL DEFAULT FALSE,
    phone_verified      BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified_at   TIMESTAMPTZ,
    phone_verified_at   TIMESTAMPTZ,

    -- Profile
    date_of_birth       DATE,
    preferred_language  VARCHAR(10) DEFAULT 'en',

    -- Stats (denormalised for performance)
    total_complaints    INTEGER NOT NULL DEFAULT 0 CHECK (total_complaints >= 0),
    resolved_complaints INTEGER NOT NULL DEFAULT 0 CHECK (resolved_complaints >= 0),
    reputation_score    NUMERIC(5,2) NOT NULL DEFAULT 0.00,

    -- Timestamps
    last_login_at       TIMESTAMPTZ,
    last_active_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ  -- soft delete

    CONSTRAINT users_email_unique UNIQUE (email),
    CONSTRAINT users_phone_unique UNIQUE (phone),
    CONSTRAINT users_reputation_range CHECK (reputation_score BETWEEN 0 AND 100),
    CONSTRAINT users_resolved_lte_total
        CHECK (resolved_complaints <= total_complaints)
);

COMMENT ON TABLE  users IS 'All platform users — citizens, officers, and admins.';
COMMENT ON COLUMN users.reputation_score IS 'Citizen trust score 0–100 based on accurate reporting history.';
COMMENT ON COLUMN users.ward_id IS 'References wards table (managed externally by municipality).';

-- ============================================================
-- TABLE 2 — CATEGORIES
-- ============================================================

CREATE TABLE categories (
    id              SERIAL PRIMARY KEY,
    name            issue_category NOT NULL UNIQUE,
    display_name    VARCHAR(100) NOT NULL,
    description     TEXT,
    icon_url        TEXT,
    color_hex       VARCHAR(7) DEFAULT '#FF6B35',
    sla_hours       INTEGER NOT NULL DEFAULT 48
                        CHECK (sla_hours BETWEEN 1 AND 720),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN categories.sla_hours IS 'Target resolution time in hours per municipality SLA.';

-- ============================================================
-- TABLE 3 — OFFICERS
-- ============================================================

CREATE TABLE officers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_number    VARCHAR(50) NOT NULL,
    department      VARCHAR(150) NOT NULL,
    designation     VARCHAR(150),
    ward_ids        INTEGER[] NOT NULL DEFAULT '{}',   -- assigned wards
    category_ids    INTEGER[] NOT NULL DEFAULT '{}',   -- assigned issue categories
    is_available    BOOLEAN NOT NULL DEFAULT TRUE,
    max_complaints  INTEGER NOT NULL DEFAULT 20 CHECK (max_complaints BETWEEN 1 AND 100),

    -- Performance stats (denormalised)
    total_assigned      INTEGER NOT NULL DEFAULT 0 CHECK (total_assigned >= 0),
    total_resolved      INTEGER NOT NULL DEFAULT 0 CHECK (total_resolved >= 0),
    avg_resolution_days NUMERIC(5,2),
    performance_score   NUMERIC(5,2) NOT NULL DEFAULT 0.00
                            CHECK (performance_score BETWEEN 0 AND 100),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT officers_user_unique   UNIQUE (user_id),
    CONSTRAINT officers_badge_unique  UNIQUE (badge_number),
    CONSTRAINT officers_resolved_lte_assigned
        CHECK (total_resolved <= total_assigned)
);

COMMENT ON COLUMN officers.ward_ids   IS 'PostgreSQL integer array of ward IDs this officer is responsible for.';
COMMENT ON COLUMN officers.category_ids IS 'Issue category IDs (FK to categories.id) this officer handles.';

-- ============================================================
-- TABLE 4 — COMPLAINTS
-- ============================================================

CREATE TABLE complaints (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    complaint_number    VARCHAR(20) NOT NULL,   -- human-readable e.g. CMP-2025-00001

    -- Citizen & Officer
    citizen_id          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    officer_id          UUID REFERENCES officers(id) ON DELETE SET NULL,
    category_id         INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,

    -- Status & Severity
    status              complaint_status NOT NULL DEFAULT 'submitted',
    severity            severity_level NOT NULL DEFAULT 'medium',
    priority_score      NUMERIC(5,2) NOT NULL DEFAULT 0.00,  -- computed by AI

    -- Location (PostGIS point + human fields)
    location            GEOGRAPHY(POINT, 4326) NOT NULL,
    latitude            NUMERIC(10,7) NOT NULL,
    longitude           NUMERIC(10,7) NOT NULL,
    address             TEXT,
    ward_id             INTEGER,
    landmark            VARCHAR(255),

    -- Content
    title               VARCHAR(255) NOT NULL,
    description         TEXT NOT NULL,
    ai_description      TEXT,          -- auto-generated by AI
    tags                TEXT[],        -- e.g. {'road','night'}

    -- Duplicate detection
    is_duplicate        BOOLEAN NOT NULL DEFAULT FALSE,
    parent_complaint_id UUID REFERENCES complaints(id) ON DELETE SET NULL,
    support_count       INTEGER NOT NULL DEFAULT 0 CHECK (support_count >= 0),

    -- AI metadata
    ai_confidence       NUMERIC(5,4) CHECK (ai_confidence BETWEEN 0 AND 1),
    ai_processed_at     TIMESTAMPTZ,
    ai_model_version    VARCHAR(50),

    -- Resolution
    resolved_at         TIMESTAMPTZ,
    resolution_notes    TEXT,
    citizen_verified    BOOLEAN DEFAULT FALSE,
    citizen_verified_at TIMESTAMPTZ,
    citizen_rating      SMALLINT CHECK (citizen_rating BETWEEN 1 AND 5),

    -- SLA tracking
    sla_deadline        TIMESTAMPTZ,
    sla_breached        BOOLEAN NOT NULL DEFAULT FALSE,

    -- Soft delete / moderation
    is_flagged          BOOLEAN NOT NULL DEFAULT FALSE,
    flag_reason         TEXT,
    closed_reason       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,

    CONSTRAINT complaints_number_unique UNIQUE (complaint_number),
    CONSTRAINT complaints_lat_range CHECK (latitude  BETWEEN -90  AND  90),
    CONSTRAINT complaints_lng_range CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT complaints_resolved_date
        CHECK (resolved_at IS NULL OR resolved_at >= created_at),
    CONSTRAINT complaints_verified_after_resolved
        CHECK (citizen_verified_at IS NULL OR resolved_at IS NOT NULL),
    CONSTRAINT complaints_no_self_parent
        CHECK (parent_complaint_id IS NULL OR parent_complaint_id <> id)
);

COMMENT ON TABLE  complaints IS 'Core complaint entity. Each row represents one civic issue report.';
COMMENT ON COLUMN complaints.location IS 'PostGIS geography point (SRID 4326) for spatial queries.';
COMMENT ON COLUMN complaints.complaint_number IS 'Human-readable ID e.g. CMP-2025-00042.';
COMMENT ON COLUMN complaints.priority_score IS 'Composite score (0–100) computed from severity + support_count + SLA.';

-- ============================================================
-- TABLE 5 — COMPLAINT_IMAGES
-- ============================================================

CREATE TABLE complaint_images (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    complaint_id    UUID NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    uploader_id     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    -- Storage
    s3_key          VARCHAR(512) NOT NULL UNIQUE,
    s3_bucket       VARCHAR(255) NOT NULL,
    cdn_url         TEXT,
    thumbnail_url   TEXT,

    -- Image metadata
    original_filename VARCHAR(255),
    mime_type       VARCHAR(100) NOT NULL DEFAULT 'image/jpeg',
    file_size_bytes BIGINT CHECK (file_size_bytes > 0),
    width_px        INTEGER CHECK (width_px > 0),
    height_px       INTEGER CHECK (height_px > 0),
    image_hash      VARCHAR(64) NOT NULL,   -- SHA-256, for duplicate image detection

    -- Role in complaint
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,  -- main evidence photo
    is_resolution   BOOLEAN NOT NULL DEFAULT FALSE,  -- officer's "after" photo
    caption         TEXT,

    -- AI bounding boxes (stored as JSONB)
    -- [{"label":"pothole","confidence":0.93,"bbox":[x1,y1,x2,y2]}]
    bounding_boxes  JSONB,

    -- GPS from EXIF (may differ from complaint location)
    exif_lat        NUMERIC(10,7),
    exif_lng        NUMERIC(10,7),
    exif_captured_at TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN complaint_images.image_hash     IS 'SHA-256 of image bytes — used by AI duplicate detector.';
COMMENT ON COLUMN complaint_images.bounding_boxes IS 'YOLOv8 detection output stored as JSONB array.';
COMMENT ON COLUMN complaint_images.is_resolution  IS 'TRUE for officer "after repair" evidence photos.';

-- ============================================================
-- TABLE 6 — AI_ANALYSIS
-- ============================================================

CREATE TABLE ai_analysis (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    complaint_id        UUID NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    image_id            UUID REFERENCES complaint_images(id) ON DELETE SET NULL,

    -- Detection results
    detected_category   issue_category,
    confidence_score    NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    severity_predicted  severity_level NOT NULL,
    severity_confidence NUMERIC(5,4) CHECK (severity_confidence BETWEEN 0 AND 1),

    -- Bounding boxes (same as image but stored here for query convenience)
    bounding_boxes      JSONB,

    -- Description generation
    generated_description TEXT,
    description_model   VARCHAR(100),

    -- Duplicate detection
    duplicate_checked   BOOLEAN NOT NULL DEFAULT FALSE,
    is_duplicate        BOOLEAN NOT NULL DEFAULT FALSE,
    similar_complaint_ids UUID[],
    similarity_score    NUMERIC(5,4),

    -- Model metadata
    model_name          VARCHAR(100) NOT NULL DEFAULT 'yolov8n',
    model_version       VARCHAR(50)  NOT NULL DEFAULT 'v1.0.0',
    inference_time_ms   INTEGER,

    -- Raw output (full model JSON for debugging)
    raw_output          JSONB,

    processing_status   VARCHAR(50) NOT NULL DEFAULT 'completed',
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ai_analysis IS 'Stores every AI inference result per complaint image.';
COMMENT ON COLUMN ai_analysis.similar_complaint_ids IS 'Array of complaint UUIDs that were flagged as potential duplicates.';

-- ============================================================
-- TABLE 7 — RESOLUTIONS
-- ============================================================

CREATE TABLE resolutions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    complaint_id        UUID NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    officer_id          UUID NOT NULL REFERENCES officers(id) ON DELETE RESTRICT,

    -- Resolution details
    resolution_type     VARCHAR(100),   -- 'repair', 'replaced', 'cleaned', etc.
    work_done           TEXT NOT NULL,
    materials_used      TEXT,
    contractor_name     VARCHAR(200),
    estimated_cost      NUMERIC(12,2) CHECK (estimated_cost >= 0),
    actual_cost         NUMERIC(12,2) CHECK (actual_cost >= 0),

    -- Evidence
    before_image_ids    UUID[] DEFAULT '{}',
    after_image_ids     UUID[] DEFAULT '{}',

    -- Scheduling
    scheduled_date      DATE,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,

    -- Citizen feedback
    citizen_feedback    TEXT,
    citizen_rating      SMALLINT CHECK (citizen_rating BETWEEN 1 AND 5),
    citizen_rated_at    TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT resolutions_one_per_complaint UNIQUE (complaint_id),
    CONSTRAINT resolutions_completed_after_started
        CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)
);

COMMENT ON TABLE resolutions IS 'Resolution record created by the officer when marking a complaint as resolved.';

-- ============================================================
-- TABLE 8 — NOTIFICATIONS
-- ============================================================

CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recipient_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    complaint_id    UUID REFERENCES complaints(id) ON DELETE SET NULL,

    -- Content
    type            notification_type NOT NULL,
    title           VARCHAR(255) NOT NULL,
    body            TEXT NOT NULL,
    data            JSONB,           -- extra payload for deep-link etc.

    -- Delivery
    channel         notification_channel NOT NULL DEFAULT 'in_app',
    status          notification_status NOT NULL DEFAULT 'pending',
    fcm_message_id  VARCHAR(255),
    sent_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    read_at         TIMESTAMPTZ,
    failed_reason   TEXT,
    retry_count     SMALLINT NOT NULL DEFAULT 0 CHECK (retry_count BETWEEN 0 AND 5),

    -- Scheduled delivery
    scheduled_for   TIMESTAMPTZ DEFAULT NOW(),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN notifications.data IS 'JSON payload forwarded to mobile app for deep-link routing.';
COMMENT ON COLUMN notifications.channel IS 'Delivery channel: push (FCM), email, sms, or in_app.';

-- ============================================================
-- TABLE 9 — REPORTS
-- ============================================================

CREATE TABLE reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    generated_by    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    -- Report definition
    type            report_type NOT NULL,
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    parameters      JSONB NOT NULL DEFAULT '{}',
    -- e.g. {"ward_id":3,"from":"2025-01-01","to":"2025-03-31","category":"pothole"}

    -- Output
    status          report_status NOT NULL DEFAULT 'queued',
    s3_key          VARCHAR(512),
    s3_bucket       VARCHAR(255),
    cdn_url         TEXT,
    file_format     VARCHAR(20) DEFAULT 'pdf',   -- pdf | xlsx | csv
    file_size_bytes BIGINT,
    page_count      INTEGER,

    -- Summary stats embedded in report
    summary         JSONB,

    error_message   TEXT,
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN reports.parameters IS 'Arbitrary filter params used to generate this report.';
COMMENT ON COLUMN reports.summary    IS 'Key metrics extracted from the report for API quick-access.';

-- ============================================================
-- TABLE 10 — COMPLAINT_SUPPORTERS
-- (Citizens who "+1" / upvote an existing complaint)
-- ============================================================

CREATE TABLE complaint_supporters (
    complaint_id    UUID NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (complaint_id, user_id)
);

COMMENT ON TABLE complaint_supporters IS 'Many-to-many: citizens who confirm / upvote a complaint.';

-- ============================================================
-- TABLE 11 — COMPLAINT_STATUS_HISTORY
-- ============================================================

CREATE TABLE complaint_status_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    complaint_id    UUID NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    changed_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    officer_id      UUID REFERENCES officers(id) ON DELETE SET NULL,

    from_status     complaint_status,
    to_status       complaint_status NOT NULL,
    notes           TEXT,
    attachments     UUID[],  -- image IDs attached to this status change

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE complaint_status_history IS 'Immutable audit trail of every complaint status change.';

-- ============================================================
-- TABLE 12 — AUDIT_LOGS
-- ============================================================

CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,  -- high-volume; use BIGSERIAL not UUID
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          audit_action NOT NULL,
    resource_type   VARCHAR(100),           -- 'complaint', 'user', 'officer', etc.
    resource_id     VARCHAR(255),           -- UUID or other ID as text
    old_values      JSONB,
    new_values      JSONB,
    ip_address      INET,
    user_agent      TEXT,
    request_id      VARCHAR(100),
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    error_message   TEXT,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);         -- partition by month for performance

COMMENT ON TABLE audit_logs IS 'Append-only audit trail. Range-partitioned by month.';

-- Monthly partitions (create new ones ahead of time via scheduled job)
CREATE TABLE audit_logs_2025_01 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE audit_logs_2025_02 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE audit_logs_2025_03 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE audit_logs_2025_04 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE audit_logs_2025_05 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE audit_logs_2025_06 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
CREATE TABLE audit_logs_2025_07 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');
CREATE TABLE audit_logs_2025_08 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');
CREATE TABLE audit_logs_2025_09 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');
CREATE TABLE audit_logs_2025_10 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE audit_logs_2025_11 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
CREATE TABLE audit_logs_2025_12 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');
CREATE TABLE audit_logs_2026_01 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE audit_logs_default  PARTITION OF audit_logs DEFAULT;
