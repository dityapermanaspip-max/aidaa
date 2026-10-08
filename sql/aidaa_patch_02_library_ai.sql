-- AIDAA patch 02: library AI draft. Safe to rerun. Run after aidaa_patch_01_audit_universe.sql.
ALTER TABLE aidaa_ai.ai_suggestion DROP CONSTRAINT IF EXISTS ai_suggestion_feature_check;
ALTER TABLE aidaa_ai.ai_suggestion ADD CONSTRAINT ai_suggestion_feature_check CHECK (feature IN ('plan','team','pka','budget','report','library_improvement','expertise_extract','library_draft'));
ALTER TABLE aidaa_core.library_pka ADD COLUMN IF NOT EXISTS ai_suggestion_id uuid REFERENCES aidaa_ai.ai_suggestion(suggestion_id);
ALTER TABLE aidaa_ai.ai_suggestion DROP CONSTRAINT IF EXISTS ai_suggestion_feature_check, ADD CONSTRAINT ai_suggestion_feature_check CHECK (feature IN ('plan','team','pka','budget','report','library_improvement','expertise_extract','library_draft','sbm_draft'));

ALTER TABLE aidaa_ai.ai_suggestion DROP CONSTRAINT IF EXISTS ai_suggestion_feature_check, ADD CONSTRAINT ai_suggestion_feature_check CHECK (feature IN ('plan','team','pka','budget','report','library_improvement','expertise_extract','library_draft','sbm_draft','trip_draft'));