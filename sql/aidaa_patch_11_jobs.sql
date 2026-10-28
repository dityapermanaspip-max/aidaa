-- AIDAA patch 11: background jobs. Safe to rerun. Run after aidaa_patch_10_location_master.sql.
--
-- AI generation and PDF/OCR extraction were running on the request thread: one call could hold a
-- pooled database connection for minutes (the AI retry loop alone allowed 15 minutes). The endpoint
-- now inserts a row here and answers 202 with the job id; `python -m app.worker` picks the row up
-- (FOR UPDATE SKIP LOCKED, several worker processes are safe) and writes the result back.
--
-- status: queued -> running -> done | failed. locked_at lets a crashed worker be reclaimed after
-- JOB_STALE_MINUTES (app/services/jobs.py), so a killed process never parks a job forever.
-- payload holds the service arguments plus the audit entry to replay; result holds the exact JSON
-- the old synchronous endpoint returned. Prune finished rows periodically if the table grows.

CREATE TABLE IF NOT EXISTS aidaa_core.job (
    job_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type    text NOT NULL,
    status      text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    user_id     uuid NOT NULL REFERENCES iam.users(user_id),
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    result      jsonb,
    error       text,
    attempts    int NOT NULL DEFAULT 0,
    locked_at   timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz
);

-- The worker's claim query: oldest queued row (plus stale running rows) first.
CREATE INDEX IF NOT EXISTS idx_job_queue ON aidaa_core.job (created_at) WHERE status IN ('queued', 'running');
-- The owner-scoped poll: GET /jobs/{id} only ever looks up one user's rows.
CREATE INDEX IF NOT EXISTS idx_job_user ON aidaa_core.job (user_id, created_at DESC);
