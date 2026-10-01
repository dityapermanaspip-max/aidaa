-- ==================================================
-- aidaa_core.sql: Core Schema Definitions
-- Dependencies Reference:
-- - iam.organization (Unit information)
-- - iam.user (User information)
-- ==================================================

-- Tables for Core Auditing Entities

-- 1. ref_auditable_unit
-- Tracks the specific unit entity under audit, referencing the primary IAM organization.
CREATE TABLE aidaa_core.ref_auditable_unit (
    unit_record_id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL UNIQUE, -- FK to iam.organization.id
    audit_scope_start_date DATE NOT NULL,
    audit_scope_end_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by BIGINT NOT NULL, -- FK to iam.user.id
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_auditable_unit_org FOREIGN KEY (organization_id) REFERENCES iam.organization (id) ON DELETE RESTRICT
);


-- 2. auditor
-- Maps a general IAM user to their specific role and unit context within an audited assignment.
CREATE TABLE aidaa_core.auditor (
    auditor_record_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- FK to iam.user.id
    user_role_id VARCHAR(50) NOT NULL, -- e.g., 'aidaa_auditor'
    assigned_org_id BIGINT NOT NULL, -- Context for conflict checking
    is_currently_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_auditor_user FOREIGN KEY (user_id) REFERENCES iam.user (id) ON DELETE CASCADE,
    CONSTRAINT fk_auditor_org FOREIGN KEY (assigned_org_id) REFERENCES iam.organization (id) ON DELETE RESTRICT
);
