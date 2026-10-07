-- AIDAA seed: SBM TA 2026, Lampiran I No. 30 (Satuan Biaya Penginapan Perjalanan Dinas Dalam Negeri, 38 provinsi).
-- Safe to rerun. Run after aidaa_patch_03_org_scope.sql. TRIAL DATA: amounts not yet checked against the PMK.

-- 0. ROOT ORGANISATION (the only line to change per organisation: the org code)
DROP TABLE IF EXISTS pg_temp.seed_root;
CREATE TEMP TABLE seed_root AS SELECT org_id AS root_org_id FROM iam.organizations WHERE org_code = 'PDGRPT' AND is_active = TRUE AND COALESCE(root_org_id, org_id) = org_id;
DO $$ BEGIN IF (SELECT count(*) FROM seed_root) <> 1 THEN RAISE EXCEPTION 'Root organisation not found: check the org code and that it is a root organisation'; END IF; END $$;

-- 1. COST COMPONENT (Lampiran I No. 30, lodging, per night)
INSERT INTO aidaa_core.ref_cost_component (root_org_id, component_code, component_name, calc_basis, sort_order)
SELECT (SELECT root_org_id FROM seed_root), 'PENGINAPAN', 'Biaya Penginapan Perjalanan Dinas Dalam Negeri', 'per_night', 20
ON CONFLICT (root_org_id, component_code) DO NOTHING;

-- 2. PROVINCE LOCATIONS (38, code PROV- + ISO 3166-2 suffix)
INSERT INTO aidaa_core.ref_location (root_org_id, location_code, location_name, country, province)
SELECT (SELECT root_org_id FROM seed_root), v.code, 'Provinsi ' || v.province, 'Indonesia', v.province
FROM (VALUES
  ('PROV-AC','Aceh'),('PROV-SU','Sumatera Utara'),('PROV-RI','Riau'),('PROV-KR','Kepulauan Riau'),
  ('PROV-JA','Jambi'),('PROV-SB','Sumatera Barat'),('PROV-SS','Sumatera Selatan'),('PROV-LA','Lampung'),
  ('PROV-BE','Bengkulu'),('PROV-BB','Kepulauan Bangka Belitung'),('PROV-BT','Banten'),('PROV-JB','Jawa Barat'),
  ('PROV-JK','DKI Jakarta'),('PROV-JT','Jawa Tengah'),('PROV-YO','DI Yogyakarta'),('PROV-JI','Jawa Timur'),
  ('PROV-BA','Bali'),('PROV-NB','Nusa Tenggara Barat'),('PROV-NT','Nusa Tenggara Timur'),('PROV-KB','Kalimantan Barat'),
  ('PROV-KT','Kalimantan Tengah'),('PROV-KS','Kalimantan Selatan'),('PROV-KI','Kalimantan Timur'),('PROV-KU','Kalimantan Utara'),
  ('PROV-SA','Sulawesi Utara'),('PROV-GO','Gorontalo'),('PROV-SR','Sulawesi Barat'),('PROV-SN','Sulawesi Selatan'),
  ('PROV-ST','Sulawesi Tengah'),('PROV-SG','Sulawesi Tenggara'),('PROV-MA','Maluku'),('PROV-MU','Maluku Utara'),
  ('PROV-PA','Papua'),('PROV-PB','Papua Barat'),('PROV-PD','Papua Barat Daya'),('PROV-PT','Papua Tengah'),
  ('PROV-PS','Papua Selatan'),('PROV-PE','Papua Pegunungan')
) AS v(code, province)
ON CONFLICT (root_org_id, location_code) DO NOTHING;

-- 3. RATES (one row per province, four grades expanded below)
-- Columns: location_code, PEJABAT_NEGARA_ESELON_I, ESELON_II, ESELON_III_GOL_IV, ESELON_IV_GOL_III_II_I
INSERT INTO aidaa_core.ref_cost_rate
    (component_id, location_id, grade, amount, effective_from, effective_to, approval_status, approved_at)
SELECT c.component_id, l.location_id, g.grade, g.amount, DATE '2026-01-01', DATE '2026-12-31', 'approved', now()
FROM (VALUES
  ('PROV-AC',5109000,3526000,1578000,770000),
  ('PROV-SU',4960000,2195000,1188000,699000),
  ('PROV-RI',3820000,3119000,1650000,852000),
  ('PROV-KR',6177000,2481000,1388000,792000),
  ('PROV-JA',5004000,4102000,1252000,580000),
  ('PROV-SB',5603000,3373000,1353000,701000),
  ('PROV-SS',6298000,3134000,1966000,861000),
  ('PROV-LA',4806000,2663000,1539000,621000),
  ('PROV-BE',2140000,1628000,1546000,692000),
  ('PROV-BB',4424000,2838000,1957000,724000),
  ('PROV-BT',5725000,2373000,1301000,775000),
  ('PROV-JB',5812000,2755000,1366000,735000),
  ('PROV-JK',9331000,2084000,1062000,730000),
  ('PROV-JT',6129000,2138000,1286000,810000),
  ('PROV-YO',5100000,2695000,1600000,845000),
  ('PROV-JI',4449000,2007000,1234000,814000),
  ('PROV-BA',7328000,2433000,1754000,1138000),
  ('PROV-NB',4682000,2648000,1418000,907000),
  ('PROV-NT',4013000,2283000,1450000,737000),
  ('PROV-KB',2654000,1923000,1125000,576000),
  ('PROV-KT',4901000,3391000,1189000,706000),
  ('PROV-KS',4797000,3316000,1500000,746000),
  ('PROV-KI',4000000,2342000,1507000,804000),
  ('PROV-KU',4000000,2854000,1507000,904000),
  ('PROV-SA',5264000,2290000,1270000,978000),
  ('PROV-GO',4168000,3107000,1606000,955000),
  ('PROV-SR',4076000,3098000,1344000,704000),
  ('PROV-SN',4820000,1938000,1423000,745000),
  ('PROV-ST',2309000,2166000,1679000,951000),
  ('PROV-SG',3089000,2755000,1297000,786000),
  ('PROV-MA',3467000,3240000,1059000,667000),
  ('PROV-MU',4612000,3843000,1160000,654000),
  ('PROV-PA',3859000,3318000,2521000,1038000),
  ('PROV-PB',3872000,3575000,2056000,967000),
  ('PROV-PD',3872000,3575000,2056000,967000),
  ('PROV-PT',3859000,3318000,2521000,1038000),
  ('PROV-PS',5673000,4877000,3706000,1526000),
  ('PROV-PE',5711000,4911000,3731000,1536000)
) AS v(loc, e1, e2, e3, e4)
CROSS JOIN LATERAL (VALUES
  ('PEJABAT_NEGARA_ESELON_I', v.e1), ('ESELON_II', v.e2),
  ('ESELON_III_GOL_IV', v.e3), ('ESELON_IV_GOL_III_II_I', v.e4)
) AS g(grade, amount)
JOIN aidaa_core.ref_cost_component c ON c.component_code = 'PENGINAPAN' AND c.root_org_id = (SELECT root_org_id FROM seed_root)
JOIN aidaa_core.ref_location l ON l.location_code = v.loc AND l.root_org_id = (SELECT root_org_id FROM seed_root)
WHERE NOT EXISTS (
  SELECT 1 FROM aidaa_core.ref_cost_rate r
  WHERE r.component_id = c.component_id AND r.location_id = l.location_id
    AND r.grade = g.grade AND r.effective_from = DATE '2026-01-01');

-- 4. VERIFICATION (run after the seed)
-- Expect 38 locations and 152 rates for 2026:
-- SELECT (SELECT count(*) FROM aidaa_core.ref_location WHERE location_code LIKE 'PROV-%') AS provinces, (SELECT count(*) FROM aidaa_core.ref_cost_rate WHERE effective_from = DATE '2026-01-01') AS rates_2026;
-- Cutoff test: rates valid on a 2026 date (expect 152) and on a 2027 date (expect 0 until you add 2027 data):
-- SELECT count(*) FILTER (WHERE DATE '2026-06-15' BETWEEN effective_from AND effective_to) AS valid_2026, count(*) FILTER (WHERE DATE '2027-06-15' BETWEEN effective_from AND COALESCE(effective_to, DATE '9999-12-31')) AS valid_2027 FROM aidaa_core.ref_cost_rate WHERE approval_status = 'approved';