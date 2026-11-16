-- AIDAA patch 01: audit universe model. Safe to rerun. Run after aidaa_execution.sql.

ALTER TABLE aidaa_core.ref_location ADD COLUMN IF NOT EXISTS country varchar(100) NOT NULL DEFAULT 'Indonesia';
ALTER TABLE aidaa_core.ref_location ADD COLUMN IF NOT EXISTS province varchar(100);
ALTER TABLE aidaa_core.ref_location ADD COLUMN IF NOT EXISTS city varchar(100);
ALTER TABLE aidaa_core.ref_location ADD COLUMN IF NOT EXISTS address text;

CREATE TABLE IF NOT EXISTS aidaa_core.audit_setting (root_org_id uuid PRIMARY KEY REFERENCES iam.organizations(org_id), iau_org_id uuid NOT NULL REFERENCES iam.organizations(org_id), updated_at timestamptz NOT NULL DEFAULT now(), updated_by uuid REFERENCES iam.users(user_id), CHECK (root_org_id <> iau_org_id));

CREATE UNIQUE INDEX IF NOT EXISTS uq_auditable_unit_org ON aidaa_core.ref_auditable_unit(org_id) WHERE org_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS aidaa_core.audit_plan_unit (plan_id uuid NOT NULL REFERENCES aidaa_core.audit_plan(plan_id) ON DELETE CASCADE, unit_id uuid NOT NULL REFERENCES aidaa_core.ref_auditable_unit(unit_id), created_at timestamptz NOT NULL DEFAULT now(), created_by uuid REFERENCES iam.users(user_id), PRIMARY KEY (plan_id, unit_id));

CREATE TABLE IF NOT EXISTS aidaa_core.assignment_unit (assignment_id uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id) ON DELETE CASCADE, unit_id uuid NOT NULL REFERENCES aidaa_core.ref_auditable_unit(unit_id), created_at timestamptz NOT NULL DEFAULT now(), created_by uuid REFERENCES iam.users(user_id), PRIMARY KEY (assignment_id, unit_id));

INSERT INTO aidaa_core.audit_plan_unit (plan_id, unit_id) SELECT plan_id, unit_id FROM aidaa_core.audit_plan ON CONFLICT DO NOTHING;
INSERT INTO aidaa_core.assignment_unit (assignment_id, unit_id) SELECT assignment_id, unit_id FROM aidaa_core.assignment ON CONFLICT DO NOTHING;

INSERT INTO iam.permissions (app_id, permission_code, permission_label) SELECT a.app_id, v.c, v.l FROM iam.applications a, (VALUES ('audit.setting.read','View audit setting'),('audit.setting.update','Designate the Internal Audit Unit')) AS v(c,l) WHERE a.app_code='AIDAA' ON CONFLICT (permission_code) DO NOTHING;

INSERT INTO iam.role_permissions (role_id, permission_id) SELECT r.role_id, p.permission_id FROM (VALUES ('AIDAA.ADMIN','audit.setting.read'),('AIDAA.ADMIN','audit.setting.update'),('AIDAA.HEAD_AUDIT','audit.setting.read')) AS v(rc,pc) JOIN iam.roles r ON r.role_code = v.rc JOIN iam.permissions p ON p.permission_code = v.pc ON CONFLICT (role_id, permission_id) DO NOTHING;
ALTER TABLE aidaa_core.ref_cost_rate ADD COLUMN IF NOT EXISTS origin_location_id uuid REFERENCES aidaa_core.ref_location(location_id); ALTER TABLE aidaa_core.audit_setting ADD COLUMN IF NOT EXISTS base_location_id uuid REFERENCES aidaa_core.ref_location(location_id);

-- ref_cost_rate.grade is a jsonb array of grade codes (NULL or empty = every grade). The base file creates it
-- as varchar(30); this converts it, so a fresh install matches the code in services/masters_costing.py (it was
-- documented here since the owner merged it, but the statements were never in the file). A rate that held one
-- grade becomes a one-element array. Idempotent: skipped when the column is already jsonb.
DO $$
BEGIN
  IF (SELECT data_type FROM information_schema.columns
       WHERE table_schema = 'aidaa_core' AND table_name = 'ref_cost_rate' AND column_name = 'grade') <> 'jsonb' THEN
    ALTER TABLE aidaa_core.ref_cost_rate ALTER COLUMN grade TYPE jsonb
      USING CASE WHEN grade IS NULL OR grade = '' THEN NULL ELSE jsonb_build_array(grade) END;
  END IF;
END $$;
ALTER TABLE aidaa_core.ref_cost_rate DROP CONSTRAINT IF EXISTS ck_rate_grade_array;
ALTER TABLE aidaa_core.ref_cost_rate ADD CONSTRAINT ck_rate_grade_array
  CHECK (grade IS NULL OR jsonb_typeof(grade) = 'array');

