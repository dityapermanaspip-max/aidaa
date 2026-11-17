-- AIDAA seed: DEMO data for the root organisation "Instansi Demo", so a first try works end to end.
-- A separate entry on purpose: nothing here is shared with another seed, and every row is demo content.
-- Safe to rerun (ON CONFLICT DO NOTHING / WHERE NOT EXISTS everywhere). Run after the base files, patches 01-13 and
-- seed_locations_indonesia.sql (the national location tier). Contains no BEGIN or COMMIT (apply_schema.py wraps the file).
--
-- WHAT IT ADDS (all under the one root named in step 0):
--   A. Needs only the root: audit types, cost components, APPROVED demo rates, funding sources, a small PKA library.
--   B. Needs IAM data that the owner creates in the web UI (this file never writes to iam):
--      auditors = users who hold AIDAA.AUDITOR in an org under the root;
--      units    = every active org under the root outside the Internal Audit Unit (IAU) subtree.
--      B is skipped for what is missing (no auditor grants, no IAU designated yet). Designate the IAU in the app
--      (Pengaturan Audit), then run this file again: it adds only what is new.
-- DEMO AMOUNTS: the rates below are round placeholders, NOT taken from a PMK/SBM. Real rates come from the SBM AI helper.
-- Known exception to the seed rules: step 7 reads audit_setting of THE NAMED ROOT only (to leave the IAU out of the
-- units). It never uses audit_setting to find the root; the root is named in step 0.

-- 0. ROOT ORGANISATION (the only line to change per organisation: the official name; or compare org_code instead)
DROP TABLE IF EXISTS pg_temp.seed_root;
CREATE TEMP TABLE seed_root AS
SELECT o.org_id AS root_org_id
FROM iam.organizations o
WHERE o.is_active = TRUE AND COALESCE(o.root_org_id, o.org_id) = o.org_id
  AND lower((SELECT l.official_name FROM iam.organization_details_log l
             WHERE l.org_id = o.org_id ORDER BY l.valid_from DESC LIMIT 1)) = lower('Instansi Demo');
DO $$ BEGIN IF (SELECT count(*) FROM seed_root) <> 1 THEN RAISE EXCEPTION 'Root organisation not found (or more than one): check the official name and that it is an active ROOT organisation'; END IF; END $$;

-- 1. AUDIT TYPES
INSERT INTO aidaa_core.ref_audit_type (root_org_id, type_code, type_name, description)
SELECT (SELECT root_org_id FROM seed_root), v.code, v.name, v.descr
FROM (VALUES
  ('KEU',   'Audit Keuangan',                'Menilai kewajaran penyajian laporan keuangan dan kepatuhan pengelolaan keuangan.'),
  ('KIN',   'Audit Kinerja',                 'Menilai ekonomi, efisiensi, dan efektivitas pelaksanaan program atau kegiatan.'),
  ('PDTT',  'Audit dengan Tujuan Tertentu',  'Audit di luar keuangan dan kinerja, misalnya kepatuhan atau pengadaan barang/jasa.'),
  ('REVIU', 'Reviu',                         'Penelaahan atas laporan atau dokumen agar sesuai dengan ketentuan.')
) AS v(code, name, descr)
ON CONFLICT (root_org_id, type_code) DO NOTHING;

-- 2. COST COMPONENTS (UANG_HARIAN and PENGINAPAN carry the demo rates of step 3; the six at_cost ones carry none,
--    the real cost is typed at budget and realisation; TRANSPORT is the one the trip helper falls back to)
INSERT INTO aidaa_core.ref_cost_component (root_org_id, component_code, component_name, calc_basis, sort_order)
SELECT (SELECT root_org_id FROM seed_root), v.code, v.name, v.basis, v.sort
FROM (VALUES
  ('UANG_HARIAN',                   'Uang Harian Perjalanan Dinas (contoh demo)',               'per_travel_day', 10),
  ('PENGINAPAN',                    'Biaya Penginapan Perjalanan Dinas (contoh demo)',          'per_night',      20),
  ('TRANSPORT',                     'Transportasi (cadangan perjalanan)',                       'at_cost',        30),
  ('TIKET_PESAWAT_EKONOMI',         'Tiket Pesawat PP Kelas Ekonomi (Lampiran 17)',             'at_cost',        40),
  ('TIKET_PESAWAT_BISNIS',          'Tiket Pesawat PP Kelas Bisnis (Lampiran 17)',              'at_cost',        50),
  ('TRANSPORT_DARAT_ANTAR_KOTA',    'Transportasi Darat Ibukota Provinsi ke Kab/Kota (Lampiran 1)', 'at_cost',  60),
  ('TRANSPORT_TERMINAL',            'Transportasi ke/dari Terminal, Stasiun, Bandara, Pelabuhan (Lampiran 16)', 'at_cost', 70),
  ('TRANSPORT_KEGIATAN_DALAM_KOTA', 'Transpor Kegiatan dalam Kab/Kota PP (Lampiran 3)',        'at_cost',        80)
) AS v(code, name, basis, sort)
ON CONFLICT (root_org_id, component_code) DO NOTHING;

-- 3. DEMO RATES: one national amount (no location) per grade, approved, valid 2026 and 2027.
--    The grade codes are the ones used by the SBM seeds; an auditor's grade must equal one of them exactly.
INSERT INTO aidaa_core.ref_cost_rate
    (component_id, location_id, grade, amount, effective_from, effective_to, approval_status, approved_at)
SELECT c.component_id, NULL, to_jsonb(ARRAY[v.grade]), v.amount, DATE '2026-01-01', DATE '2027-12-31', 'approved', now()
FROM (VALUES
  ('UANG_HARIAN', 'PEJABAT_NEGARA_ESELON_I',     530000),
  ('UANG_HARIAN', 'ESELON_II',                   430000),
  ('UANG_HARIAN', 'ESELON_III_GOL_IV',           370000),
  ('UANG_HARIAN', 'ESELON_IV_GOL_III_II_I',      300000),
  ('PENGINAPAN',  'PEJABAT_NEGARA_ESELON_I',    4500000),
  ('PENGINAPAN',  'ESELON_II',                  3000000),
  ('PENGINAPAN',  'ESELON_III_GOL_IV',          1500000),
  ('PENGINAPAN',  'ESELON_IV_GOL_III_II_I',      800000)
) AS v(code, grade, amount)
JOIN aidaa_core.ref_cost_component c
  ON c.root_org_id = (SELECT root_org_id FROM seed_root) AND c.component_code = v.code
WHERE NOT EXISTS (
  SELECT 1 FROM aidaa_core.ref_cost_rate r
  WHERE r.component_id = c.component_id AND r.location_id IS NULL
    AND r.grade = to_jsonb(ARRAY[v.grade]) AND r.effective_from = DATE '2026-01-01');

-- 4. FUNDING SOURCES (the DIPA ceilings are enforced when an assignment is funded)
INSERT INTO aidaa_core.ref_funding_source (root_org_id, funding_code, funding_name, fiscal_year, funding_type, ceiling_amount)
SELECT (SELECT root_org_id FROM seed_root), v.code, v.name, v.fy, v.ftype, v.ceiling
FROM (VALUES
  ('DIPA-2026',    'DIPA Satuan Pengawasan 2026 (contoh demo)', 2026, 'budget',          2000000000),
  ('DIPA-2027',    'DIPA Satuan Pengawasan 2027 (contoh demo)', 2027, 'budget',          2000000000),
  ('AUDITEE-2027', 'Dibiayai Auditee 2027 (contoh demo)',       2027, 'paid_by_auditee', NULL)
) AS v(code, name, fy, ftype, ceiling)
ON CONFLICT (root_org_id, funding_code) DO NOTHING;

-- 5. PKA LIBRARY: five programs of work with three procedures each (generic, to be adapted by the team)
INSERT INTO aidaa_core.library_pka (root_org_id, type_id, pka_code, title, objective)
SELECT (SELECT root_org_id FROM seed_root), t.type_id, v.pka_code, v.title, v.objective
FROM (VALUES
  ('KEU',   'KEU-001',   'Audit atas Kas dan Setara Kas',
   'Meyakinkan bahwa saldo kas dan setara kas disajikan wajar dan pengelolaannya sesuai ketentuan.'),
  ('KEU',   'KEU-002',   'Audit atas Pendapatan',
   'Meyakinkan bahwa pendapatan ditetapkan, dipungut, dan disetor sesuai ketentuan dan dicatat lengkap.'),
  ('KIN',   'KIN-001',   'Audit Kinerja atas Pencapaian Sasaran Program',
   'Menilai apakah sasaran dan target program tercapai secara ekonomis, efisien, dan efektif.'),
  ('PDTT',  'PDTT-001',  'Pemeriksaan Kepatuhan Pengadaan Barang/Jasa',
   'Menilai kepatuhan proses pengadaan dan pelaksanaan kontrak terhadap ketentuan yang berlaku.'),
  ('REVIU', 'REVIU-001', 'Reviu atas Laporan Keuangan',
   'Memberikan keyakinan terbatas bahwa laporan keuangan disajikan sesuai standar akuntansi pemerintah.')
) AS v(type_code, pka_code, title, objective)
JOIN aidaa_core.ref_audit_type t
  ON t.root_org_id = (SELECT root_org_id FROM seed_root) AND t.type_code = v.type_code
ON CONFLICT (root_org_id, pka_code) DO NOTHING;

INSERT INTO aidaa_core.library_procedure (library_pka_id, step_no, procedure_text, expected_evidence, estimated_hours)
SELECT p.library_pka_id, v.step_no, v.procedure_text, v.expected_evidence, v.hours
FROM (VALUES
  ('KEU-001', 1, 'Lakukan kas opname dan cocokkan hasilnya dengan buku kas pada tanggal yang sama.', 'Berita acara kas opname', 4),
  ('KEU-001', 2, 'Cocokkan saldo rekening bank dengan rekening koran dan periksa rekonsiliasi bank.', 'Rekening koran dan rekonsiliasi bank', 6),
  ('KEU-001', 3, 'Uji sampel penerimaan dan pengeluaran kas terhadap bukti pendukung dan otorisasinya.', 'Bukti kas masuk dan keluar', 10),
  ('KEU-002', 1, 'Pelajari dasar hukum dan tarif pendapatan, lalu bandingkan dengan tarif yang diterapkan.', 'Peraturan dan daftar tarif', 4),
  ('KEU-002', 2, 'Uji sampel pendapatan dari penetapan sampai disetor ke kas negara/daerah, termasuk ketepatan waktu.', 'Dokumen penetapan dan bukti setor', 10),
  ('KEU-002', 3, 'Rekonsiliasi pendapatan menurut pembukuan dengan laporan dan rekening penampungan.', 'Rekonsiliasi pendapatan', 6),
  ('KIN-001', 1, 'Identifikasi sasaran, indikator, dan target kinerja program.', 'Dokumen perencanaan dan perjanjian kinerja', 6),
  ('KIN-001', 2, 'Bandingkan realisasi dengan target dan telusuri penyebab deviasi yang signifikan.', 'Laporan kinerja dan data realisasi', 12),
  ('KIN-001', 3, 'Nilai ekonomi, efisiensi, dan efektivitas penggunaan sumber daya untuk program.', 'Data anggaran, keluaran, dan hasil wawancara', 12),
  ('PDTT-001', 1, 'Petakan paket pengadaan pada periode audit dan pilih sampel berdasarkan nilai dan risiko.', 'Daftar paket pengadaan', 4),
  ('PDTT-001', 2, 'Uji proses pemilihan penyedia terhadap ketentuan pengadaan.', 'Dokumen pemilihan dan berita acara', 12),
  ('PDTT-001', 3, 'Uji pelaksanaan kontrak: kesesuaian pekerjaan, pembayaran, dan denda keterlambatan.', 'Kontrak, BAST, dan bukti bayar', 12),
  ('REVIU-001', 1, 'Pahami entitas dan lakukan prosedur analitis atas akun-akun utama.', 'Laporan keuangan dan kertas kerja analitis', 6),
  ('REVIU-001', 2, 'Tanyakan dan telaah akun yang berfluktuasi signifikan beserta penjelasan manajemen.', 'Catatan wawancara dan dokumen pendukung', 6),
  ('REVIU-001', 3, 'Susun ikhtisar hasil reviu dan simpulkan kewajaran penyajian laporan.', 'Ikhtisar hasil reviu', 4)
) AS v(pka_code, step_no, procedure_text, expected_evidence, hours)
JOIN aidaa_core.library_pka p
  ON p.root_org_id = (SELECT root_org_id FROM seed_root) AND p.pka_code = v.pka_code
ON CONFLICT (library_pka_id, step_no) DO NOTHING;

-- 6. AUDITORS (B): users holding AIDAA.AUDITOR in an org under the root. Grades rotate over three codes so the demo
--    prices differ; home location is the national Jakarta Pusat row. Edit both afterwards in Master > Auditor.
INSERT INTO aidaa_core.auditor (user_id, root_org_id, home_org_id, home_location_id, grade)
SELECT c.user_id, (SELECT root_org_id FROM seed_root), c.org_id,
       (SELECT location_id FROM aidaa_core.ref_location WHERE root_org_id IS NULL AND location_code = 'KOTA-JAKARTA_PUSAT'),
       (ARRAY['ESELON_II', 'ESELON_III_GOL_IV', 'ESELON_IV_GOL_III_II_I'])[1 + mod(c.n - 1, 3)::int]
FROM (
  SELECT x.user_id, x.org_id, row_number() OVER (ORDER BY x.username) AS n
  FROM (
    SELECT DISTINCT ON (u.user_id) u.user_id, m.org_id, u.username
    FROM iam.user_organization_roles m
    JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE AND r.role_code = 'AIDAA.AUDITOR'
    JOIN iam.users u ON u.user_id = m.user_id AND u.is_active = TRUE
    JOIN iam.organizations o ON o.org_id = m.org_id AND o.is_active = TRUE
    WHERE m.is_active = TRUE AND COALESCE(o.root_org_id, o.org_id) = (SELECT root_org_id FROM seed_root)
    ORDER BY u.user_id, m.created_at
  ) x
) c
ON CONFLICT DO NOTHING;

-- 7. AUDITABLE UNITS (B): one per active org under the root, outside the IAU subtree, with the org's official name.
--    Only runs when this root has an IAU designated (otherwise the audit team itself would become a unit).
INSERT INTO aidaa_core.ref_auditable_unit (root_org_id, org_id, unit_code, unit_name, location_id)
WITH RECURSIVE iau AS (
  SELECT s.iau_org_id AS org_id FROM aidaa_core.audit_setting s WHERE s.root_org_id = (SELECT root_org_id FROM seed_root)
  UNION ALL
  SELECT c.org_id FROM iam.organizations c JOIN iau ON c.parent_id = iau.org_id
)
SELECT (SELECT root_org_id FROM seed_root), o.org_id, left('UNIT-' || o.org_code, 30),
       left(COALESCE((SELECT l.official_name FROM iam.organization_details_log l
                      WHERE l.org_id = o.org_id ORDER BY l.valid_from DESC LIMIT 1), o.org_code), 200),
       (SELECT location_id FROM aidaa_core.ref_location WHERE root_org_id IS NULL AND location_code = 'KOTA-JAKARTA_PUSAT')
FROM iam.organizations o
WHERE o.is_active = TRUE AND COALESCE(o.root_org_id, o.org_id) = (SELECT root_org_id FROM seed_root)
  AND o.org_id <> (SELECT root_org_id FROM seed_root)
  AND EXISTS (SELECT 1 FROM aidaa_core.audit_setting s WHERE s.root_org_id = (SELECT root_org_id FROM seed_root))
  AND o.org_id NOT IN (SELECT org_id FROM iau)
ON CONFLICT DO NOTHING;

-- Verification (run by hand; the apply script prints no notices, so check what B added):
-- SELECT (SELECT count(*) FROM aidaa_core.ref_audit_type    WHERE root_org_id = r.root_org_id) AS types,
--        (SELECT count(*) FROM aidaa_core.ref_cost_component WHERE root_org_id = r.root_org_id) AS components,
--        (SELECT count(*) FROM aidaa_core.ref_cost_rate x JOIN aidaa_core.ref_cost_component c USING (component_id)
--          WHERE c.root_org_id = r.root_org_id AND x.approval_status = 'approved') AS approved_rates,
--        (SELECT count(*) FROM aidaa_core.ref_funding_source WHERE root_org_id = r.root_org_id) AS funding,
--        (SELECT count(*) FROM aidaa_core.library_pka        WHERE root_org_id = r.root_org_id) AS pka,
--        (SELECT count(*) FROM aidaa_core.auditor            WHERE root_org_id = r.root_org_id) AS auditors,
--        (SELECT count(*) FROM aidaa_core.ref_auditable_unit WHERE root_org_id = r.root_org_id) AS units
-- FROM seed_root r;
-- Expected on a first full run: 4, 8, 8, 3, 5 (15 procedures), then auditors and units from your IAM data.
