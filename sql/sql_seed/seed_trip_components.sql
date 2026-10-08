-- AIDAA seed: trip cost components (no amounts, rates come from the SBM AI helper). Safe to rerun.
-- All at_cost: the rate is a MAXIMUM reference for the budget, the real cost is entered at realisation.
-- To seed another organisation, change ONLY the org code in step 0.

DROP TABLE IF EXISTS pg_temp.seed_root;
CREATE TEMP TABLE seed_root AS SELECT org_id AS root_org_id FROM iam.organizations WHERE org_code = 'PDGRPT' AND is_active = TRUE AND COALESCE(root_org_id, org_id) = org_id;
DO $$ BEGIN IF (SELECT count(*) FROM seed_root) <> 1 THEN RAISE EXCEPTION 'Root organisation not found: check the org code and that it is a root organisation'; END IF; END $$;

INSERT INTO aidaa_core.ref_cost_component (root_org_id, component_code, component_name, calc_basis, sort_order)
SELECT (SELECT root_org_id FROM seed_root), v.code, v.name, 'at_cost', v.sort
FROM (VALUES
  ('TRANSPORT',                     'Transportasi (cadangan perjalanan)',                      30),
  ('TIKET_PESAWAT_EKONOMI',         'Tiket Pesawat PP Kelas Ekonomi (Lampiran 17)',            40),
  ('TIKET_PESAWAT_BISNIS',          'Tiket Pesawat PP Kelas Bisnis (Lampiran 17)',             50),
  ('TRANSPORT_DARAT_ANTAR_KOTA',    'Transportasi Darat Ibukota Provinsi ke Kab/Kota (Lampiran 1)', 60),
  ('TRANSPORT_TERMINAL',            'Transportasi ke/dari Terminal, Stasiun, Bandara, Pelabuhan (Lampiran 16)', 70),
  ('TRANSPORT_KEGIATAN_DALAM_KOTA', 'Transpor Kegiatan dalam Kab/Kota PP (Lampiran 3)',       80)
) AS v(code, name, sort)
ON CONFLICT (root_org_id, component_code) DO NOTHING;

-- Verification:
-- SELECT component_code, calc_basis FROM aidaa_core.ref_cost_component WHERE root_org_id = (SELECT root_org_id FROM seed_root) AND calc_basis = 'at_cost' ORDER BY sort_order;