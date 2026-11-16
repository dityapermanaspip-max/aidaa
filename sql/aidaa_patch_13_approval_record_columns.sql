-- AIDAA patch 13: dedicated record columns on approval_task. Safe to rerun (ADD COLUMN IF NOT EXISTS).
-- Was sql/item3_approval_record_columns.sql, renamed 2026-11-16 so it sits in the install order. Run after
-- aidaa_patch_05_realisation.sql (it references realisation_settlement).
-- Run once against the AIDAA database. Adds dedicated record columns to approval_task
-- so the inbox can link directly to plan / finding / report / settlement instead of
-- inferring from record_type + sliced record_id.
ALTER TABLE aidaa_core.approval_task
  ADD COLUMN IF NOT EXISTS plan_id uuid REFERENCES aidaa_core.audit_plan(plan_id),
  ADD COLUMN IF NOT EXISTS finding_id uuid REFERENCES aidaa_core.finding(finding_id),
  ADD COLUMN IF NOT EXISTS report_id uuid REFERENCES aidaa_core.audit_report(report_id),
  ADD COLUMN IF NOT EXISTS settlement_id uuid REFERENCES aidaa_core.realisation_settlement(settlement_id);
