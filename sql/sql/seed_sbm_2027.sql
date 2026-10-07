-- AIDAA seed: Standar Biaya Masukan (SBM) for ONE root organisation. Safe to rerun, never edits or deletes rows.
-- Source: PMK <number>/<year>. Name the annex and table of every block in a comment.
-- Run after aidaa_patch_03_org_scope.sql. To seed another organisation, change ONLY the org code in step 0.
-- SBM amounts are reference standards: the app flags lines above them but never blocks (no hard block).
--
-- RULES FOR THE WRITER (human or AI)
-- 1. Only these tables: aidaa_core.ref_cost_component, aidaa_core.ref_location, aidaa_core.ref_cost_rate.
-- 2. Every component and location row carries the root organisation from step 0. Rates inherit it from their component.
--    Codes are unique PER root organisation, so the ON CONFLICT clauses below must stay (root_org_id, code).
-- 3. Cost component = one cost TYPE. component_code: UPPER_SNAKE_CASE, max 30 chars. calc_basis is exactly one of:
--      per_day_worked  daily allowance and representation (amount x days)
--      per_travel_day  transit-day stipend (travel days only)
--      per_night       lodging (amount x nights)
--      at_cost         actual cost typed by the user (tickets, taxi). No rate rows needed.
--      fixed           one-off lump sums
--    Daily allowance categories are SEPARATE components (outside the city, inside the city over 8 hours, training...).
-- 4. Province rates use a PROVINCE-LEVEL location: location_code 'PROV-' + ISO 3166-2 suffix (PROV-JK, PROV-JB),
--    country 'Indonesia', province filled, city NULL. A rate on such a location covers every place in that province.
--    A rate with location '' is national (no province).
-- 5. grade is '' when the amount does not depend on rank. When it does, use ONLY these codes:
--      PEJABAT_NEGARA_ESELON_I | ESELON_II | ESELON_III_GOL_IV | ESELON_IV_GOL_III_II_I
-- 6. amount: plain rupiah number (no separators). Foreign currency: put the currency in the component name,
--    one component per currency.
-- 7. effective_from / effective_to: the budget year of the PMK (YYYY-01-01 to YYYY-12-31).
-- 8. Rates are seeded as 'approved' because the regulation is the approval (approved_by stays NULL).
--    Change that literal to 'draft' if the Board should approve them in the app instead.
-- 9. Copy amounts exactly from the annex. Never guess or interpolate. Leave a missing value out and list it
--    in a comment block named MISSING at the end of the file.
-- 10. End the file with the verification queries.

-- ---------------------------------------------------------------- 0. ROOT ORGANISATION (the only line to change per organisation)
DROP TABLE IF EXISTS pg_temp.seed_root;
CREATE TEMP TABLE seed_root AS SELECT org_id AS root_org_id FROM iam.organizations WHERE org_code = 'PUT_ROOT_ORG_CODE_HERE' AND is_active = TRUE AND COALESCE(root_org_id, org_id) = org_id;
DO $$ BEGIN IF (SELECT count(*) FROM seed_root) <> 1 THEN RAISE EXCEPTION 'Root organisation not found: check the org code and that it is a root organisation'; END IF; END $$;

-- ---------------------------------------------------------------- 1. COST COMPONENTS
INSERT INTO aidaa_core.ref_cost_component (root_org_id, component_code, component_name, calc_basis, sort_order)
SELECT (SELECT root_org_id FROM seed_root), v.code, v.name, v.basis, v.sort
FROM (VALUES
  ('UH_LUAR_KOTA', 'Uang Harian Perjalanan Dinas Luar Kota', 'per_day_worked', 10),
  ('PENGINAPAN',   'Biaya Penginapan',                       'per_night',      20)
  -- add more rows here
) AS v(code, name, basis, sort)
ON CONFLICT (root_org_id, component_code) DO NOTHING;

-- ---------------------------------------------------------------- 2. PROVINCE LOCATIONS
INSERT INTO aidaa_core.ref_location (root_org_id, location_code, location_name, country, province)
SELECT (SELECT root_org_id FROM seed_root), v.code, v.name, v.country, v.province
FROM (VALUES
  ('PROV-JK', 'Provinsi DKI Jakarta', 'Indonesia', 'DKI Jakarta')
  -- one row per province in the annex
) AS v(code, name, country, province)
ON CONFLICT (root_org_id, location_code) DO NOTHING;

-- ---------------------------------------------------------------- 3. RATES
-- VALUES columns: component_code, location_code ('' = national), grade ('' = any), amount.
INSERT INTO aidaa_core.ref_cost_rate
    (component_id, location_id, grade, amount, effective_from, effective_to, approval_status, approved_at)
SELECT c.component_id, l.location_id, NULLIF(v.grade, ''), v.amount,
       DATE '2027-01-01', DATE '2027-12-31', 'approved', now()
FROM (VALUES
  ('UH_LUAR_KOTA', 'PROV-JK', '',          0),   -- replace 0 with the annex amount
  ('PENGINAPAN',   'PROV-JK', 'ESELON_II', 0)    -- replace 0 with the annex amount
  -- one row per component x province x grade
) AS v(comp, loc, grade, amount)
JOIN aidaa_core.ref_cost_component c ON c.component_code = v.comp AND c.root_org_id = (SELECT root_org_id FROM seed_root)
LEFT JOIN aidaa_core.ref_location l ON l.location_code = v.loc AND l.root_org_id = (SELECT root_org_id FROM seed_root)
WHERE (v.loc = '' OR l.location_id IS NOT NULL)   -- a mistyped location code skips the row instead of making it national
  AND NOT EXISTS (
        SELECT 1 FROM aidaa_core.ref_cost_rate r
        WHERE r.component_id = c.component_id
          AND r.location_id IS NOT DISTINCT FROM l.location_id
          AND r.grade IS NOT DISTINCT FROM NULLIF(v.grade, '')
          AND r.effective_from = DATE '2027-01-01');

-- ---------------------------------------------------------------- 4. VERIFICATION (run after the seed)
-- Rows per component for this year (compare with the number of rows written above):
-- SELECT c.component_code, count(*) FROM aidaa_core.ref_cost_rate r JOIN aidaa_core.ref_cost_component c USING (component_id) WHERE c.root_org_id = (SELECT root_org_id FROM seed_root) AND r.effective_from = DATE '2027-01-01' GROUP BY 1 ORDER BY 1;
-- Province-based components with a rate that has no location (expected 0):
-- SELECT c.component_code, count(*) FROM aidaa_core.ref_cost_rate r JOIN aidaa_core.ref_cost_component c USING (component_id) WHERE c.root_org_id = (SELECT root_org_id FROM seed_root) AND r.location_id IS NULL AND r.effective_from = DATE '2027-01-01' GROUP BY 1;