-- AIDAA AI suggestion table. Safe to rerun. Run after aidaa_log_approval.sql.

CREATE SCHEMA IF NOT EXISTS aidaa_ai;

CREATE TABLE IF NOT EXISTS aidaa_ai.ai_suggestion (suggestion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), feature varchar(30) NOT NULL CHECK (feature IN ('plan','team','pka','budget','report','library_improvement','expertise_extract')), record_type varchar(30) NOT NULL, record_id uuid, engine varchar(20) NOT NULL CHECK (engine IN ('ollama','cloud')), model_name varchar(100) NOT NULL, input_ref text, output jsonb NOT NULL, status varchar(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','edited','rejected')), decided_by uuid REFERENCES iam.users(user_id), decided_at timestamptz, created_by uuid REFERENCES iam.users(user_id), created_at timestamptz NOT NULL DEFAULT now());

CREATE INDEX IF NOT EXISTS ix_ai_suggestion_record ON aidaa_ai.ai_suggestion(record_type, record_id);

ALTER TABLE aidaa_core.budget_line ADD COLUMN IF NOT EXISTS ai_suggestion_id uuid REFERENCES aidaa_ai.ai_suggestion(suggestion_id);

ALTER TABLE aidaa_core.audit_plan_version ADD COLUMN IF NOT EXISTS ai_suggestion_id uuid REFERENCES aidaa_ai.ai_suggestion(suggestion_id);