-- AIDAA log (append-only) and approval tables. Safe to rerun. Run after aidaa_core_planning.sql.

CREATE SCHEMA IF NOT EXISTS aidaa_log;

CREATE TABLE IF NOT EXISTS aidaa_log.team_log (log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), plan_id uuid, assignment_id uuid, auditor_id uuid, action varchar(30) NOT NULL CHECK (action IN ('add','remove','replace','role_change','blocked_conflict')), role varchar(20), reason text, actor_id uuid REFERENCES iam.users(user_id), created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS aidaa_log.approval_log (log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), record_type varchar(30) NOT NULL, record_id uuid NOT NULL, step_code varchar(50), decision varchar(20) NOT NULL CHECK (decision IN ('submitted','approved','rejected','returned')), reason text, actor_id uuid REFERENCES iam.users(user_id), created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS aidaa_log.edit_log (log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), table_name varchar(80) NOT NULL, record_id uuid NOT NULL, field_name varchar(80) NOT NULL, old_value text, new_value text, reason text, actor_id uuid REFERENCES iam.users(user_id), created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS aidaa_log.comment_log (log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), record_type varchar(30) NOT NULL, record_id uuid NOT NULL, comment_text text NOT NULL, actor_id uuid REFERENCES iam.users(user_id), created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS aidaa_log.status_log (log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), record_type varchar(30) NOT NULL, record_id uuid NOT NULL, old_status varchar(30), new_status varchar(30) NOT NULL, by_ai boolean NOT NULL DEFAULT false, actor_id uuid REFERENCES iam.users(user_id), created_at timestamptz NOT NULL DEFAULT now());

CREATE OR REPLACE FUNCTION aidaa_log.block_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'aidaa_log is append-only'; END $$;

DROP TRIGGER IF EXISTS trg_team_log_ro ON aidaa_log.team_log; CREATE TRIGGER trg_team_log_ro BEFORE UPDATE OR DELETE ON aidaa_log.team_log FOR EACH ROW EXECUTE FUNCTION aidaa_log.block_change();
DROP TRIGGER IF EXISTS trg_approval_log_ro ON aidaa_log.approval_log; CREATE TRIGGER trg_approval_log_ro BEFORE UPDATE OR DELETE ON aidaa_log.approval_log FOR EACH ROW EXECUTE FUNCTION aidaa_log.block_change();
DROP TRIGGER IF EXISTS trg_edit_log_ro ON aidaa_log.edit_log; CREATE TRIGGER trg_edit_log_ro BEFORE UPDATE OR DELETE ON aidaa_log.edit_log FOR EACH ROW EXECUTE FUNCTION aidaa_log.block_change();
DROP TRIGGER IF EXISTS trg_comment_log_ro ON aidaa_log.comment_log; CREATE TRIGGER trg_comment_log_ro BEFORE UPDATE OR DELETE ON aidaa_log.comment_log FOR EACH ROW EXECUTE FUNCTION aidaa_log.block_change();
DROP TRIGGER IF EXISTS trg_status_log_ro ON aidaa_log.status_log; CREATE TRIGGER trg_status_log_ro BEFORE UPDATE OR DELETE ON aidaa_log.status_log FOR EACH ROW EXECUTE FUNCTION aidaa_log.block_change();

CREATE TABLE IF NOT EXISTS aidaa_core.approval_step (step_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), record_type varchar(30) NOT NULL, step_no int NOT NULL, step_code varchar(50) NOT NULL, approver_kind varchar(20) NOT NULL CHECK (approver_kind IN ('global_role','assignment_role')), approver_role varchar(60) NOT NULL, is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (record_type, step_no));

CREATE TABLE IF NOT EXISTS aidaa_core.approval_task (task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), record_type varchar(30) NOT NULL, record_id uuid NOT NULL, step_id uuid NOT NULL REFERENCES aidaa_core.approval_step(step_id), assigned_user_id uuid REFERENCES iam.users(user_id), requested_by uuid NOT NULL REFERENCES iam.users(user_id), status varchar(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','returned','cancelled')), due_date date, decided_by uuid REFERENCES iam.users(user_id), decided_at timestamptz, decision_note text, created_at timestamptz NOT NULL DEFAULT now(), CHECK (decided_by IS NULL OR decided_by <> requested_by));

CREATE INDEX IF NOT EXISTS ix_approval_task_user_status ON aidaa_core.approval_task(assigned_user_id, status);

INSERT INTO aidaa_core.approval_step (record_type, step_no, step_code, approver_kind, approver_role) VALUES ('plan',1,'finance_verify','global_role','AIDAA.FINANCE'),('plan',2,'board_approve','global_role','AIDAA.BOARD'),('assignment_change',1,'supervisor_approve','assignment_role','supervisor'),('budget',1,'finance_verify','global_role','AIDAA.FINANCE'),('pka',1,'supervisor_approve','assignment_role','supervisor'),('report',1,'supervisor_review','assignment_role','supervisor'),('report',2,'head_approve','global_role','AIDAA.HEAD_AUDIT'),('cost_rate',1,'board_approve','global_role','AIDAA.BOARD'),('expertise',1,'hr_verify','global_role','AIDAA.HR') ON CONFLICT (record_type, step_no) DO NOTHING;