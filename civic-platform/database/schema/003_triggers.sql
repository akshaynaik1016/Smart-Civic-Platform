-- ============================================================
-- Smart Civic Intelligence Platform — Triggers & Functions
-- ============================================================

-- ─── 1. Auto-update updated_at ───────────────────────────────────────────────

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_categories_updated_at
    BEFORE UPDATE ON categories
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_officers_updated_at
    BEFORE UPDATE ON officers
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_complaints_updated_at
    BEFORE UPDATE ON complaints
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_resolutions_updated_at
    BEFORE UPDATE ON resolutions
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ─── 2. Auto-generate complaint_number ───────────────────────────────────────

CREATE SEQUENCE IF NOT EXISTS complaint_seq START 1 INCREMENT 1 NO CYCLE;

CREATE OR REPLACE FUNCTION generate_complaint_number()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.complaint_number IS NULL OR NEW.complaint_number = '' THEN
        NEW.complaint_number := 'CMP-' ||
            TO_CHAR(NOW(), 'YYYY') || '-' ||
            LPAD(NEXTVAL('complaint_seq')::TEXT, 5, '0');
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_complaints_number
    BEFORE INSERT ON complaints
    FOR EACH ROW EXECUTE FUNCTION generate_complaint_number();

-- ─── 3. Set SLA deadline on insert ───────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_sla_deadline()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_sla_hours INTEGER;
BEGIN
    SELECT sla_hours INTO v_sla_hours
    FROM categories WHERE id = NEW.category_id;

    -- Critical severity gets half the SLA time
    IF NEW.severity = 'critical' THEN
        v_sla_hours := GREATEST(v_sla_hours / 2, 4);
    ELSIF NEW.severity = 'high' THEN
        v_sla_hours := GREATEST(v_sla_hours * 3 / 4, 8);
    END IF;

    NEW.sla_deadline := NEW.created_at + (v_sla_hours || ' hours')::INTERVAL;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_complaints_sla
    BEFORE INSERT ON complaints
    FOR EACH ROW EXECUTE FUNCTION set_sla_deadline();

-- ─── 4. Denormalise citizen complaint stats ───────────────────────────────────

CREATE OR REPLACE FUNCTION update_citizen_complaint_stats()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- On insert: increment total_complaints
    IF TG_OP = 'INSERT' THEN
        UPDATE users
        SET total_complaints = total_complaints + 1
        WHERE id = NEW.citizen_id;

    -- On status change to resolved/verified: increment resolved
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.status NOT IN ('resolved','verified') AND
           NEW.status IN ('resolved','verified') THEN
            UPDATE users
            SET resolved_complaints = resolved_complaints + 1
            WHERE id = NEW.citizen_id;
        END IF;
        -- Mark SLA breach if past deadline
        IF NEW.sla_deadline IS NOT NULL AND NOW() > NEW.sla_deadline AND
           NEW.status NOT IN ('resolved','verified','closed','rejected') THEN
            NEW.sla_breached := TRUE;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_citizen_stats
    AFTER INSERT ON complaints
    FOR EACH ROW EXECUTE FUNCTION update_citizen_complaint_stats();

CREATE TRIGGER trg_citizen_stats_update
    BEFORE UPDATE OF status ON complaints
    FOR EACH ROW EXECUTE FUNCTION update_citizen_complaint_stats();

-- ─── 5. Denormalise officer stats ────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_officer_stats()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_resolution_days NUMERIC;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- New assignment
        IF OLD.officer_id IS DISTINCT FROM NEW.officer_id AND NEW.officer_id IS NOT NULL THEN
            UPDATE officers
            SET total_assigned = total_assigned + 1
            WHERE id = NEW.officer_id;

            -- Decrement previous officer's count if reassigned
            IF OLD.officer_id IS NOT NULL THEN
                UPDATE officers
                SET total_assigned = GREATEST(total_assigned - 1, 0)
                WHERE id = OLD.officer_id;
            END IF;
        END IF;

        -- Resolution
        IF OLD.status NOT IN ('resolved','verified') AND
           NEW.status IN ('resolved','verified') AND
           NEW.officer_id IS NOT NULL THEN

            v_resolution_days := EXTRACT(EPOCH FROM (NOW() - NEW.created_at)) / 86400.0;

            UPDATE officers
            SET
                total_resolved      = total_resolved + 1,
                avg_resolution_days = (
                    (COALESCE(avg_resolution_days, 0) * total_resolved + v_resolution_days)
                    / (total_resolved + 1)
                )
            WHERE id = NEW.officer_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_officer_stats
    AFTER UPDATE ON complaints
    FOR EACH ROW EXECUTE FUNCTION update_officer_stats();

-- ─── 6. Auto-record status history ───────────────────────────────────────────

CREATE OR REPLACE FUNCTION record_status_history()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO complaint_status_history
            (complaint_id, changed_by, officer_id, from_status, to_status)
        VALUES
            (NEW.id, NEW.citizen_id, NEW.officer_id, OLD.status, NEW.status);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_status_history
    AFTER UPDATE OF status ON complaints
    FOR EACH ROW EXECUTE FUNCTION record_status_history();

-- ─── 7. Update support_count when a supporter is added/removed ───────────────

CREATE OR REPLACE FUNCTION update_support_count()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE complaints
        SET support_count = support_count + 1
        WHERE id = NEW.complaint_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE complaints
        SET support_count = GREATEST(support_count - 1, 0)
        WHERE id = OLD.complaint_id;
    END IF;
    RETURN NULL;  -- AFTER trigger on DELETE must return NULL
END;
$$;

CREATE TRIGGER trg_support_count_insert
    AFTER INSERT ON complaint_supporters
    FOR EACH ROW EXECUTE FUNCTION update_support_count();

CREATE TRIGGER trg_support_count_delete
    AFTER DELETE ON complaint_supporters
    FOR EACH ROW EXECUTE FUNCTION update_support_count();

-- ─── 8. Sync geography point from lat/lng on complaint upsert ────────────────

CREATE OR REPLACE FUNCTION sync_complaint_location()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT'
       OR (TG_OP = 'UPDATE' AND
           (OLD.latitude  IS DISTINCT FROM NEW.latitude OR
            OLD.longitude IS DISTINCT FROM NEW.longitude))
    THEN
        NEW.location := ST_SetSRID(
            ST_MakePoint(NEW.longitude, NEW.latitude),
            4326
        )::GEOGRAPHY;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_complaints_location
    BEFORE INSERT OR UPDATE OF latitude, longitude ON complaints
    FOR EACH ROW EXECUTE FUNCTION sync_complaint_location();

-- ─── 9. Prevent deletion of resolved complaints (soft-delete only) ────────────

CREATE OR REPLACE FUNCTION guard_complaint_delete()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IN ('resolved','verified') THEN
        RAISE EXCEPTION
            'Cannot hard-delete a resolved complaint (id=%). Use soft-delete.', OLD.id
            USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_complaint_delete_guard
    BEFORE DELETE ON complaints
    FOR EACH ROW EXECUTE FUNCTION guard_complaint_delete();
