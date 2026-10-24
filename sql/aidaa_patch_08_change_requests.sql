-- Assignment change requests (batch: wire the seeded approval steps; patch 08, safe to rerun).
-- Post-issue edits are staged here and applied only when the supervisor approves the
-- approval_task linked through task_id (record_type 'assignment_change', step 1).

CREATE TABLE IF NOT EXISTS aidaa_core.assignment_change (
    change_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id  uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id),
    requested_by   uuid NOT NULL REFERENCES iam.users(user_id),
    reason         text NOT NULL,
    payload        jsonb NOT NULL,
    task_id        uuid,
    status         varchar(20) NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','approved','rejected','cancelled')),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_assignment_change_assignment
    ON aidaa_core.assignment_change(assignment_id);
