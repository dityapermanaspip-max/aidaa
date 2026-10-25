-- AIDAA patch 10: global location tier. Safe to rerun. Run after aidaa_patch_09_expertise_ai.sql.
-- One ref_location table, two tiers:
--   root_org_id IS NULL  -> shared national master (BPS provinces/kab-kota), owned by the seed,
--                           read-only in the app; the owner reruns the seed to update it.
--   root_org_id = <root> -> the organisation's own locations, created in the app as before.
-- Kept as ONE table so every foreign key (rates, visits, trip legs, units, auditor home) stays valid.
-- Do NOT rerun patch 03 after this patch: its backfill would move the global rows into the org again.

ALTER TABLE aidaa_core.ref_location ALTER COLUMN root_org_id DROP NOT NULL;

-- Codes were unique per root; split the rule by tier.
DROP INDEX IF EXISTS aidaa_core.uq_ref_location_root_code;

-- The organisation's own codes stay unique inside the organisation.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_location_org_code
    ON aidaa_core.ref_location (root_org_id, location_code) WHERE root_org_id IS NOT NULL;

-- The national master's codes are unique among themselves. A code may exist in BOTH tiers at
-- once: the org keeps its own row even when the same code also exists in the master
-- (resolution reads the org row first, so this is safe).
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_location_global_code
    ON aidaa_core.ref_location (location_code) WHERE root_org_id IS NULL;
