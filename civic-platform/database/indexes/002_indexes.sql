-- ============================================================
-- Smart Civic Intelligence Platform — Indexes
-- ============================================================

-- ─── USERS ───────────────────────────────────────────────────────────────────

CREATE INDEX idx_users_email        ON users (lower(email)) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_phone        ON users (phone)        WHERE phone IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX idx_users_role         ON users (role)         WHERE deleted_at IS NULL;
CREATE INDEX idx_users_status       ON users (status)       WHERE deleted_at IS NULL;
CREATE INDEX idx_users_ward         ON users (ward_id)      WHERE ward_id IS NOT NULL;
CREATE INDEX idx_users_created_at   ON users (created_at DESC);
-- Full-text search on name
CREATE INDEX idx_users_name_fts ON users
    USING GIN (to_tsvector('english', unaccent(full_name)));

-- ─── CATEGORIES ──────────────────────────────────────────────────────────────

CREATE INDEX idx_categories_active  ON categories (is_active, sort_order) WHERE is_active = TRUE;

-- ─── OFFICERS ────────────────────────────────────────────────────────────────

CREATE INDEX idx_officers_user_id       ON officers (user_id);
CREATE INDEX idx_officers_badge         ON officers (badge_number);
CREATE INDEX idx_officers_available     ON officers (is_available) WHERE deleted_at IS NULL;
-- GIN index for ward_ids and category_ids arrays
CREATE INDEX idx_officers_ward_ids      ON officers USING GIN (ward_ids);
CREATE INDEX idx_officers_category_ids  ON officers USING GIN (category_ids);
CREATE INDEX idx_officers_performance   ON officers (performance_score DESC) WHERE deleted_at IS NULL;

-- ─── COMPLAINTS ──────────────────────────────────────────────────────────────

-- Primary lookups
CREATE INDEX idx_complaints_number      ON complaints (complaint_number);
CREATE INDEX idx_complaints_citizen     ON complaints (citizen_id, created_at DESC);
CREATE INDEX idx_complaints_officer     ON complaints (officer_id, status) WHERE officer_id IS NOT NULL;
CREATE INDEX idx_complaints_category    ON complaints (category_id, status);
CREATE INDEX idx_complaints_ward        ON complaints (ward_id, status)  WHERE ward_id IS NOT NULL;
CREATE INDEX idx_complaints_status      ON complaints (status, created_at DESC);
CREATE INDEX idx_complaints_severity    ON complaints (severity, status);
CREATE INDEX idx_complaints_parent      ON complaints (parent_complaint_id) WHERE parent_complaint_id IS NOT NULL;

-- SLA monitoring
CREATE INDEX idx_complaints_sla         ON complaints (sla_deadline, sla_breached)
    WHERE status NOT IN ('resolved', 'verified', 'closed', 'rejected');

-- Geospatial (PostGIS GIST index)
CREATE INDEX idx_complaints_location    ON complaints USING GIST (location);

-- Combined status + location for map queries
CREATE INDEX idx_complaints_status_geo  ON complaints USING GIST (location)
    WHERE status NOT IN ('closed', 'rejected', 'verified');

-- Date range queries (dashboard, reports)
CREATE INDEX idx_complaints_created_at  ON complaints (created_at DESC);
CREATE INDEX idx_complaints_resolved_at ON complaints (resolved_at DESC)
    WHERE resolved_at IS NOT NULL;

-- Duplicate detection
CREATE INDEX idx_complaints_is_duplicate ON complaints (is_duplicate, category_id)
    WHERE is_duplicate = FALSE;

-- Priority score (for officer dashboard sorting)
CREATE INDEX idx_complaints_priority    ON complaints (priority_score DESC, created_at DESC)
    WHERE status IN ('pending_review', 'assigned', 'in_progress');

-- Full-text search on title + description
CREATE INDEX idx_complaints_fts ON complaints
    USING GIN (
        to_tsvector('english',
            unaccent(title) || ' ' || unaccent(coalesce(description, ''))
        )
    );

-- Tags GIN
CREATE INDEX idx_complaints_tags ON complaints USING GIN (tags);

-- ─── COMPLAINT_IMAGES ────────────────────────────────────────────────────────

CREATE INDEX idx_images_complaint   ON complaint_images (complaint_id, is_primary);
CREATE INDEX idx_images_uploader    ON complaint_images (uploader_id);
CREATE INDEX idx_images_hash        ON complaint_images (image_hash);  -- duplicate image detect
CREATE INDEX idx_images_primary     ON complaint_images (complaint_id) WHERE is_primary = TRUE;
CREATE INDEX idx_images_resolution  ON complaint_images (complaint_id) WHERE is_resolution = TRUE;
-- JSONB bounding_boxes (for AI result queries)
CREATE INDEX idx_images_bboxes      ON complaint_images USING GIN (bounding_boxes);

-- ─── AI_ANALYSIS ─────────────────────────────────────────────────────────────

CREATE INDEX idx_ai_complaint       ON ai_analysis (complaint_id);
CREATE INDEX idx_ai_image           ON ai_analysis (image_id)    WHERE image_id IS NOT NULL;
CREATE INDEX idx_ai_category        ON ai_analysis (detected_category);
CREATE INDEX idx_ai_duplicate       ON ai_analysis (is_duplicate) WHERE is_duplicate = TRUE;
CREATE INDEX idx_ai_model_version   ON ai_analysis (model_name, model_version);
-- GIN on similar_complaint_ids array
CREATE INDEX idx_ai_similar         ON ai_analysis USING GIN (similar_complaint_ids);

-- ─── RESOLUTIONS ─────────────────────────────────────────────────────────────

CREATE INDEX idx_resolutions_complaint ON resolutions (complaint_id);
CREATE INDEX idx_resolutions_officer   ON resolutions (officer_id);
CREATE INDEX idx_resolutions_completed ON resolutions (completed_at DESC)
    WHERE completed_at IS NOT NULL;
CREATE INDEX idx_resolutions_rating    ON resolutions (citizen_rating)
    WHERE citizen_rating IS NOT NULL;

-- ─── NOTIFICATIONS ───────────────────────────────────────────────────────────

CREATE INDEX idx_notif_recipient    ON notifications (recipient_id, status, created_at DESC);
CREATE INDEX idx_notif_complaint    ON notifications (complaint_id) WHERE complaint_id IS NOT NULL;
CREATE INDEX idx_notif_status       ON notifications (status, scheduled_for)
    WHERE status IN ('pending', 'failed');
CREATE INDEX idx_notif_unread       ON notifications (recipient_id, read_at)
    WHERE read_at IS NULL;
CREATE INDEX idx_notif_type         ON notifications (type, created_at DESC);

-- ─── COMPLAINT_SUPPORTERS ────────────────────────────────────────────────────

-- PK covers (complaint_id, user_id); add reverse for user's supported list
CREATE INDEX idx_supporters_user    ON complaint_supporters (user_id, created_at DESC);

-- ─── COMPLAINT_STATUS_HISTORY ────────────────────────────────────────────────

CREATE INDEX idx_history_complaint  ON complaint_status_history (complaint_id, created_at DESC);
CREATE INDEX idx_history_officer    ON complaint_status_history (officer_id)  WHERE officer_id IS NOT NULL;
CREATE INDEX idx_history_to_status  ON complaint_status_history (to_status, created_at DESC);

-- ─── REPORTS ─────────────────────────────────────────────────────────────────

CREATE INDEX idx_reports_user       ON reports (generated_by, created_at DESC);
CREATE INDEX idx_reports_status     ON reports (status, queued_at) WHERE status IN ('queued', 'generating');
CREATE INDEX idx_reports_type       ON reports (type, created_at DESC);
CREATE INDEX idx_reports_expires    ON reports (expires_at) WHERE expires_at IS NOT NULL;
-- JSONB parameters index
CREATE INDEX idx_reports_params     ON reports USING GIN (parameters);

-- ─── AUDIT_LOGS ──────────────────────────────────────────────────────────────

CREATE INDEX idx_audit_user         ON audit_logs (user_id, created_at DESC);
CREATE INDEX idx_audit_action       ON audit_logs (action, created_at DESC);
CREATE INDEX idx_audit_resource     ON audit_logs (resource_type, resource_id);
CREATE INDEX idx_audit_created      ON audit_logs (created_at DESC);
CREATE INDEX idx_audit_ip           ON audit_logs (ip_address, created_at DESC);
