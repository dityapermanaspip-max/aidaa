-- AIDAA patch 03: organisation scope. Safe to rerun. Run after aidaa_patch_02_library_ai.sql.
-- Five master tables belong to ONE root organisation. Cost rates inherit the root of their cost component.
ALTER TABLE aidaa_core.ref_location ADD COLUMN IF NOT EXISTS root_org_id uuid REFERENCES iam.organizations(org_id);
ALTER TABLE aidaa_core.ref_audit_type ADD COLUMN IF NOT EXISTS root_org_id uuid REFERENCES iam.organizations(org_id);
ALTER TABLE aidaa_core.ref_cost_component ADD COLUMN IF NOT EXISTS root_org_id uuid REFERENCES iam.organizations(org_id);
ALTER TABLE aidaa_core.ref_funding_source ADD COLUMN IF NOT EXISTS root_org_id uuid REFERENCES iam.organizations(org_id);
ALTER TABLE aidaa_core.library_pka ADD COLUMN IF NOT EXISTS root_org_id uuid REFERENCES iam.organizations(org_id);

-- Backfill: existing rows go to the root in aidaa_core.audit_setting. Stops with a message when there is not exactly one.
DO $$ DECLARE n int; r uuid; BEGIN IF EXISTS (SELECT 1 FROM aidaa_core.ref_location WHERE root_org_id IS NULL UNION ALL SELECT 1 FROM aidaa_core.ref_audit_type WHERE root_org_id IS NULL UNION ALL SELECT 1 FROM aidaa_core.ref_cost_component WHERE root_org_id IS NULL UNION ALL SELECT 1 FROM aidaa_core.ref_funding_source WHERE root_org_id IS NULL UNION ALL SELECT 1 FROM aidaa_core.library_pka WHERE root_org_id IS NULL) THEN SELECT count(*) INTO n FROM aidaa_core.audit_setting; IF n <> 1 THEN RAISE EXCEPTION 'Expected exactly one row in aidaa_core.audit_setting (found %), designate the Internal Audit Unit first', n; END IF; SELECT root_org_id INTO r FROM aidaa_core.audit_setting; UPDATE aidaa_core.ref_location SET root_org_id = r WHERE root_org_id IS NULL; UPDATE aidaa_core.ref_audit_type SET root_org_id = r WHERE root_org_id IS NULL; UPDATE aidaa_core.ref_cost_component SET root_org_id = r WHERE root_org_id IS NULL; UPDATE aidaa_core.ref_funding_source SET root_org_id = r WHERE root_org_id IS NULL; UPDATE aidaa_core.library_pka SET root_org_id = r WHERE root_org_id IS NULL; END IF; END $$;

ALTER TABLE aidaa_core.ref_location ALTER COLUMN root_org_id SET NOT NULL;
ALTER TABLE aidaa_core.ref_audit_type ALTER COLUMN root_org_id SET NOT NULL;
ALTER TABLE aidaa_core.ref_cost_component ALTER COLUMN root_org_id SET NOT NULL;
ALTER TABLE aidaa_core.ref_funding_source ALTER COLUMN root_org_id SET NOT NULL;
ALTER TABLE aidaa_core.library_pka ALTER COLUMN root_org_id SET NOT NULL;

-- Codes were unique across the whole database, now they are unique per root organisation.
ALTER TABLE aidaa_core.ref_location DROP CONSTRAINT IF EXISTS ref_location_location_code_key;
ALTER TABLE aidaa_core.ref_audit_type DROP CONSTRAINT IF EXISTS ref_audit_type_type_code_key;
ALTER TABLE aidaa_core.ref_cost_component DROP CONSTRAINT IF EXISTS ref_cost_component_component_code_key;
ALTER TABLE aidaa_core.ref_funding_source DROP CONSTRAINT IF EXISTS ref_funding_source_funding_code_key;
ALTER TABLE aidaa_core.library_pka DROP CONSTRAINT IF EXISTS library_pka_pka_code_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_location_root_code ON aidaa_core.ref_location(root_org_id, location_code);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_audit_type_root_code ON aidaa_core.ref_audit_type(root_org_id, type_code);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_cost_component_root_code ON aidaa_core.ref_cost_component(root_org_id, component_code);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_funding_source_root_code ON aidaa_core.ref_funding_source(root_org_id, funding_code);
CREATE UNIQUE INDEX IF NOT EXISTS uq_library_pka_root_code ON aidaa_core.library_pka(root_org_id, pka_code);