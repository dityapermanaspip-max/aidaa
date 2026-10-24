-- Expertise rows created from an accepted AI suggestion (todo-5 helpers; patch 09, safe to rerun).
-- The linked suggestion lets the HR verification task (record_type 'expertise', step 1 'hr_verify')
-- find and decide the whole batch of rows created by one acceptance.

ALTER TABLE aidaa_core.expertise ADD COLUMN IF NOT EXISTS ai_suggestion_id uuid
    REFERENCES aidaa_ai.ai_suggestion(suggestion_id);

ALTER TABLE aidaa_core.expertise DROP CONSTRAINT IF EXISTS expertise_source_check;
ALTER TABLE aidaa_core.expertise ADD CONSTRAINT expertise_source_check
    CHECK (source IN ('manual', 'system_credit', 'ai_suggestion'));
