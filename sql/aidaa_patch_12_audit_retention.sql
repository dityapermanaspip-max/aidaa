-- AIDAA patch 12: audit-log retention. Safe to rerun. Run after aidaa_patch_11_jobs.sql.
-- ---------------------------------------------------------------------------
-- (Moved from the IAM repo's schemasql/10_audit_retention.sql, upscale audit #12.)
--
-- The five aidaa_log tables are append-only and grow with every write. They had no index on
-- created_at, so the audit screens and a retention DELETE would seq-scan once they are large.
--
-- Two changes:
--   1. created_at indexes on the five tables.
--   2. a purge gate: DELETE stays blocked by the append-only trigger unless the session opts in with
--      `SET LOCAL aidaa.allow_log_purge = 'on'`. UPDATE is never allowed, so the log is still
--      append-only for the application. darkhive-bev2/scripts/archive_audit_logs.py sets the gate,
--      exports the rows to .ndjson.gz, fsyncs, and only then deletes exactly those rows.
--
-- The five triggers keep pointing at the same function name, so they pick up the new body without
-- being recreated.
--
-- Verify after applying:
--   SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_%_created_at';
--   -- should raise "aidaa_log is append-only":
--   DELETE FROM aidaa_log.status_log WHERE false;
-- ---------------------------------------------------------------------------

create index if not exists ix_team_log_created_at
    on aidaa_log.team_log (created_at);

create index if not exists ix_approval_log_created_at
    on aidaa_log.approval_log (created_at);

create index if not exists ix_edit_log_created_at
    on aidaa_log.edit_log (created_at);

create index if not exists ix_comment_log_created_at
    on aidaa_log.comment_log (created_at);

create index if not exists ix_status_log_created_at
    on aidaa_log.status_log (created_at);

create or replace function aidaa_log.block_change() returns trigger
language plpgsql as $$
begin
    if tg_op = 'UPDATE' then
        raise exception 'aidaa_log is append-only';
    end if;
    -- DELETE only for the archiver's own transaction (scripts/archive_audit_logs.py).
    if coalesce(current_setting('aidaa.allow_log_purge', true), 'off') = 'on' then
        return old;
    end if;
    raise exception 'aidaa_log is append-only';
end $$;
