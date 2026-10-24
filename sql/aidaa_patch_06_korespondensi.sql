-- AIDAA patch 06: korespondensi (document requests, interview schedules, berita acara penyampaian notisi).
-- Safe to rerun. Run after aidaa_patch_05_realisation.sql.
-- NOTE: the owner asked for "sql fix batch 4", but patch 04/05 already exist (org_scope2, realisation),
-- so this is numbered 06. Run it on the local DB first, then on the VPS.

-- A: permintaan dokumen awal, per audited unit. requested -> submitted (PIC) -> verified (auditor).
CREATE TABLE IF NOT EXISTS aidaa_core.assignment_doc_req (
  doc_req_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id) ON DELETE CASCADE,
  unit_id uuid NOT NULL REFERENCES aidaa_core.ref_auditable_unit(unit_id),
  item varchar(255) NOT NULL,
  notes text,
  deadline date NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','submitted','verified')),
  submitted_at timestamptz,
  submitted_by uuid REFERENCES iam.users(user_id),
  submitted_url varchar(500),
  submitted_desc text,
  verified_at timestamptz,
  verified_by uuid REFERENCES iam.users(user_id),
  verify_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES iam.users(user_id)
);

CREATE INDEX IF NOT EXISTS ix_assignment_doc_req_assignment ON aidaa_core.assignment_doc_req(assignment_id);

-- C: jadwal wawancara, per audited unit. planned -> held -> done; planned/held -> cancelled (reason required).
-- start_time/end_time are display strings (e.g. HH:MM), deliberately NOT TIME columns.
CREATE TABLE IF NOT EXISTS aidaa_core.assignment_interview (
  interview_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id) ON DELETE CASCADE,
  unit_id uuid NOT NULL REFERENCES aidaa_core.ref_auditable_unit(unit_id),
  topic varchar(255) NOT NULL,
  agenda text,
  held_date date NOT NULL,
  start_time varchar(8),
  end_time varchar(8),
  mode varchar(20) NOT NULL DEFAULT 'onsite' CHECK (mode IN ('onsite','online')),
  location varchar(500),
  attendees text,
  status varchar(20) NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','held','done','cancelled')),
  cancel_reason text,
  result text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES iam.users(user_id)
);

CREATE INDEX IF NOT EXISTS ix_assignment_interview_assignment ON aidaa_core.assignment_interview(assignment_id);

-- D: berita acara penyampaian notisi, ONE per finding, created manually at/after communicate.
-- THE RESOLVE GATE: findings.resolve_finding refuses to resolve (responded -> open) an item whose
-- berita acara has no recorded stance_result yet.
CREATE TABLE IF NOT EXISTS aidaa_core.finding_bap (
  bap_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id uuid NOT NULL UNIQUE REFERENCES aidaa_core.finding(finding_id) ON DELETE CASCADE,
  -- bap_no is WITHOUT a unique constraint on purpose: numbers repeat across assignments (BAP-F-001).
  bap_no varchar(50) NOT NULL,
  kepada varchar(255),
  presented_date date,
  deadline date,
  stance_result varchar(20) CHECK (stance_result IN ('agree','partially_agree','disagree')),
  response_id uuid REFERENCES aidaa_core.finding_response(response_id),
  document_url varchar(500),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES iam.users(user_id)
);

-- Backfill: findings already communicated (or later) get a BAP skeleton, filled in by the team later.
INSERT INTO aidaa_core.finding_bap (finding_id, bap_no, presented_date, deadline)
SELECT f.finding_id, 'BAP-' || f.finding_no, COALESCE(f.communicated_at::date, CURRENT_DATE), f.response_due_date
FROM aidaa_core.finding f
WHERE f.status IN ('communicated','responded','open','closed')
ON CONFLICT (finding_id) DO NOTHING;
