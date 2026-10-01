CREATE TABLE grimis_ai.ai_bowtie_drafts (
    draft_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_event_id  uuid NOT NULL REFERENCES grimis_risk.risk_events(risk_event_id) ON DELETE CASCADE,
    source_engine  varchar(20) NOT NULL,
    model_used     varchar(100) NOT NULL,
    prompt_used    text NOT NULL,
    raw_response   jsonb NOT NULL,
    created_by     uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE RESTRICT,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_ai.ai_bowtie_draft_branches (
    branch_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id          uuid NOT NULL REFERENCES grimis_ai.ai_bowtie_drafts(draft_id) ON DELETE CASCADE,
    branch_type       varchar(10) NOT NULL,     -- CAUSE / IMPACT
    parent_branch_id  uuid REFERENCES grimis_ai.ai_bowtie_draft_branches(branch_id) ON DELETE RESTRICT,
    level             integer NOT NULL DEFAULT 1,
    description       text NOT NULL,
    category          varchar(100),
    status            varchar(20) NOT NULL DEFAULT 'PENDING',
    linked_cause_id   uuid REFERENCES grimis_risk.risk_causes(cause_id) ON DELETE SET NULL,
    linked_impact_id  uuid REFERENCES grimis_risk.risk_impacts(impact_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS grimis_ai.ai_context_drafts (draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE, doc_types text[] NOT NULL, source_text text NOT NULL, model_used varchar(100) NOT NULL, prompt_used text NOT NULL, raw_response jsonb NOT NULL, created_by uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE RESTRICT, created_at timestamptz NOT NULL DEFAULT now());
