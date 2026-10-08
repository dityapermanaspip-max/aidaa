-- AIDAA org scope, round 2: auditors and auditable units join the root_org_id pattern of patch 03.
-- The Internal Audit Unit is usually a CHILD org reporting to the board; it audits the whole root,
-- may tag any user as an auditor (their home org can be any org inside the root) and may set any
-- child org as an auditable unit. Safe to rerun. Run AFTER aidaa_patch_03_org_scope.sql.

-- 1. auditor.root_org_id = the root of the auditor's home organisation.
ALTER TABLE aidaa_core.auditor ADD COLUMN IF NOT EXISTS root_org_id uuid REFERENCES iam.organizations(org_id);

DO $$
DECLARE n int;
BEGIN
    IF EXISTS (SELECT 1 FROM aidaa_core.auditor WHERE root_org_id IS NULL AND home_org_id IS NOT NULL) THEN
        UPDATE aidaa_core.auditor a
        SET root_org_id = o.r
        FROM (
            SELECT org_id, COALESCE(root_org_id, org_id) AS r FROM iam.organizations
        ) o
        WHERE a.home_org_id = o.org_id AND a.root_org_id IS NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM aidaa_core.auditor WHERE root_org_id IS NULL) THEN
        SELECT count(*) INTO n FROM aidaa_core.audit_setting;
        IF n <> 1 THEN
            RAISE EXCEPTION 'Auditor(s) without a root_org_id (%), set home_org_id or root_org_id first', n;
        ELSE
            UPDATE aidaa_core.auditor SET root_org_id = (SELECT root_org_id FROM aidaa_core.audit_setting)
            WHERE root_org_id IS NULL;
        END IF;
    END IF;
END $$;

ALTER TABLE aidaa_core.auditor ALTER COLUMN root_org_id SET NOT NULL;

-- 2. ref_auditable_unit.root_org_id = the root of the tagged IAM organisation.
ALTER TABLE aidaa_core.ref_auditable_unit ADD COLUMN IF NOT EXISTS root_org_id uuid REFERENCES iam.organizations(org_id);

DO $$
DECLARE n int;
BEGIN
    IF EXISTS (SELECT 1 FROM aidaa_core.ref_auditable_unit WHERE root_org_id IS NULL AND org_id IS NOT NULL) THEN
        UPDATE aidaa_core.ref_auditable_unit u
        SET root_org_id = o.r
        FROM (
            SELECT org_id, COALESCE(root_org_id, org_id) AS r FROM iam.organizations
        ) o
        WHERE u.org_id = o.org_id AND u.root_org_id IS NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM aidaa_core.ref_auditable_unit WHERE root_org_id IS NULL) THEN
        SELECT count(*) INTO n FROM aidaa_core.audit_setting;
        IF n <> 1 THEN
            RAISE EXCEPTION 'Auditable unit(s) without a root_org_id (%), tag org_id or set root_org_id first', n;
        ELSE
            UPDATE aidaa_core.ref_auditable_unit SET root_org_id = (SELECT root_org_id FROM aidaa_core.audit_setting)
            WHERE root_org_id IS NULL;
        END IF;
    END IF;
END $$;

ALTER TABLE aidaa_core.ref_auditable_unit ALTER COLUMN root_org_id SET NOT NULL;

-- 3. unit_code is unique PER root, not across the whole database (mirror uq_*_root_code of patch 03).
ALTER TABLE aidaa_core.ref_auditable_unit DROP CONSTRAINT IF EXISTS ref_auditable_unit_unit_code_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_auditable_unit_root_code
    ON aidaa_core.ref_auditable_unit (root_org_id, unit_code);