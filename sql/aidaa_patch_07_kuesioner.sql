-- AIDAA patch 07: kuesioner (procedure-linked questionnaires).
-- Safe to rerun. Run after aidaa_patch_06_korespondensi.sql. Local DB first, then the VPS.
-- ONE questionnaire per PKA procedure (procedure_id UNIQUE), hard cap of 5 questions.
-- Question kinds: single_choice + multi_select (2..5 options), free_text, scale (max 4/5/6).
-- Answering works through a public token link (/q/<token> in the frontend) that expires 40 hours
-- after issuing or renewing; regenerating the link instantly invalidates the previous token.
-- Public respondents never authenticate: submitted_by stays NULL; the auditee PIC may also enter
-- a response in-app (submitted_via = 'pic').

-- The team flags every procedure that needs a questionnaire (on the per-assignment procedure
-- copy). No backfill on purpose: existing procedures start unmarked, the feature begins empty.
ALTER TABLE aidaa_core.exe_procedure
  ADD COLUMN IF NOT EXISTS needs_questionnaire boolean NOT NULL DEFAULT false;

-- The questionnaire, anchored to the audited unit like doc requests and interviews so PIC lists
-- can be org-filtered. status: draft (team builds questions) -> issued (link is live) -> closed.
CREATE TABLE IF NOT EXISTS aidaa_core.assignment_questionnaire (
  questionnaire_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- ONE questionnaire per procedure: the UNIQUE here IS the per-procedure cap.
  procedure_id uuid NOT NULL UNIQUE REFERENCES aidaa_core.exe_procedure(procedure_id) ON DELETE CASCADE,
  assignment_id uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id) ON DELETE CASCADE,
  unit_id uuid NOT NULL REFERENCES aidaa_core.ref_auditable_unit(unit_id),
  title varchar(255) NOT NULL,
  intro text,
  status varchar(10) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','closed')),
  respondents_needed int NOT NULL DEFAULT 1 CHECK (respondents_needed >= 1),
  public_token uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  link_expires_at timestamptz,
  issued_at timestamptz,
  issued_by uuid REFERENCES iam.users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES iam.users(user_id)
);

CREATE INDEX IF NOT EXISTS ix_assignment_questionnaire_assignment ON aidaa_core.assignment_questionnaire(assignment_id);

-- Questions, numbered per questionnaire. The 5-question cap is enforced in the service; the kind
-- columns are constrained per kind below (choices for choice kinds, scale_max for scale only).
CREATE TABLE IF NOT EXISTS aidaa_core.questionnaire_question (
  question_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  questionnaire_id uuid NOT NULL REFERENCES aidaa_core.assignment_questionnaire(questionnaire_id) ON DELETE CASCADE,
  question_no int NOT NULL,
  kind varchar(20) NOT NULL CHECK (kind IN ('single_choice','multi_select','free_text','scale')),
  question_text varchar(500) NOT NULL,
  scale_max smallint CHECK (scale_max IN (4,5,6)),
  choices jsonb CHECK (choices IS NULL OR (jsonb_typeof(choices) = 'array'
                  AND jsonb_array_length(choices) BETWEEN 2 AND 5)),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES iam.users(user_id),
  UNIQUE (questionnaire_id, question_no),
  CHECK (kind IN ('single_choice','multi_select') = (choices IS NOT NULL)),
  CHECK ((kind = 'scale') = (scale_max IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_question_questionnaire ON aidaa_core.questionnaire_question(questionnaire_id);

-- One response row per respondent with the identity block as plain columns; several respondents
-- past the target are allowed (the counter just reads 12/5-style).
CREATE TABLE IF NOT EXISTS aidaa_core.questionnaire_response (
  response_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  questionnaire_id uuid NOT NULL REFERENCES aidaa_core.assignment_questionnaire(questionnaire_id) ON DELETE CASCADE,
  name varchar(150) NOT NULL,
  position varchar(150) NOT NULL,
  age int NOT NULL CHECK (age BETWEEN 0 AND 130),
  last_degree varchar(100) NOT NULL,
  gender varchar(1) NOT NULL CHECK (gender IN ('L','P')),
  -- public submissions have no actor: submitted_by stays NULL, the PIC in-app entry records its user.
  submitted_via varchar(10) NOT NULL DEFAULT 'public' CHECK (submitted_via IN ('public','pic')),
  submitted_by uuid REFERENCES iam.users(user_id),
  submitted_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_response_questionnaire ON aidaa_core.questionnaire_response(questionnaire_id);

-- Answers keyed per question; exactly the column matching the question's kind is filled
-- (the pairing is validated in the service, one answer row per question of the questionnaire).
CREATE TABLE IF NOT EXISTS aidaa_core.questionnaire_answer (
  answer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id uuid NOT NULL REFERENCES aidaa_core.questionnaire_response(response_id) ON DELETE CASCADE,
  question_id uuid NOT NULL REFERENCES aidaa_core.questionnaire_question(question_id) ON DELETE CASCADE,
  single_index smallint CHECK (single_index IS NULL OR single_index >= 1),
  multi_indexes jsonb CHECK (multi_indexes IS NULL OR jsonb_typeof(multi_indexes) = 'array'),
  scale_value smallint CHECK (scale_value IS NULL OR scale_value >= 1),
  text_value text,
  UNIQUE (response_id, question_id)
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_answer_response ON aidaa_core.questionnaire_answer(response_id);
CREATE INDEX IF NOT EXISTS ix_questionnaire_answer_question ON aidaa_core.questionnaire_answer(question_id);
