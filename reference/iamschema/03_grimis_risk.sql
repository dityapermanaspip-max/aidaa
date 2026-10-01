CREATE TABLE grimis_risk.risk_events (
    risk_event_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_code      varchar(50) NOT NULL,
    event_title    text NOT NULL,
    description    text,
    created_by     uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE CASCADE,
    org_id         uuid NOT NULL REFERENCES iam.organizations(org_id),
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_risk.process_risk_events (
    pre_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id     uuid NOT NULL REFERENCES grimis_core.business_processes(process_id) ON DELETE CASCADE,
    risk_event_id  uuid NOT NULL REFERENCES grimis_risk.risk_events(risk_event_id) ON DELETE CASCADE,
    ipm_id         uuid REFERENCES grimis_core.indicator_process_mappings(ipm_id) ON DELETE SET NULL,
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_risk.controls (
    control_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    control_code     varchar(50) NOT NULL,
    control_title    text NOT NULL,
    description      text,
    control_type     varchar(30) NOT NULL,   -- preventif / detektif / korektif
    control_category varchar(50),
    org_id           uuid REFERENCES iam.organizations(org_id),
    reference_link   text,
    created_by       uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE RESTRICT,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_risk.risk_evaluations (
    evaluation_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pre_id                    uuid NOT NULL REFERENCES grimis_risk.process_risk_events(pre_id) ON DELETE CASCADE,
    matrix_id                 uuid NOT NULL REFERENCES grimis_core.risk_matrix_configs(matrix_id) ON DELETE RESTRICT,
    fiscal_year               integer NOT NULL,
    period_quarter            integer CHECK (period_quarter BETWEEN 1 AND 4),
    current_inherent_cell_id  uuid REFERENCES grimis_core.risk_matrix_cells(cell_id),
    current_residual_cell_id  uuid REFERENCES grimis_core.risk_matrix_cells(cell_id) ON DELETE SET NULL,
    current_expected_cell_id  uuid REFERENCES grimis_core.risk_matrix_cells(cell_id) ON DELETE SET NULL,
    current_actual_cell_id    uuid REFERENCES grimis_core.risk_matrix_cells(cell_id) ON DELETE SET NULL,
    current_active_type       varchar(20),   -- pointer: INHERENT / RESIDUAL / EXPECTED / ACTUAL
    current_active_cell_id    uuid REFERENCES grimis_core.risk_matrix_cells(cell_id),
    current_trend             varchar(20) NOT NULL DEFAULT 'STABLE',
    closed_at                 timestamptz,
    closed_by                 uuid REFERENCES iam.users(user_id),
    created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_risk.risk_causes (
    cause_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_event_id       uuid NOT NULL REFERENCES grimis_risk.risk_events(risk_event_id) ON DELETE CASCADE,
    cause_level         integer NOT NULL DEFAULT 1,
    parent_cause_id     uuid REFERENCES grimis_risk.risk_causes(cause_id) ON DELETE CASCADE,
    cause_description   text NOT NULL,
    cause_category      varchar(50),
    linked_ecm_id       uuid,  -- FK ditambahkan setelah existing_control_mappings dibuat
    link_note           text,
    source              varchar(20)
);

CREATE TABLE grimis_risk.risk_impacts (
    impact_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_event_id       uuid NOT NULL REFERENCES grimis_risk.risk_events(risk_event_id) ON DELETE CASCADE,
    impact_description  text NOT NULL,
    impact_category     varchar(50),
    linked_ecm_id       uuid,  -- FK ditambahkan setelah existing_control_mappings dibuat
    link_note           text,
    source              varchar(20)
);

CREATE TABLE grimis_risk.existing_control_mappings (
    ecm_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id         uuid NOT NULL REFERENCES grimis_risk.risk_evaluations(evaluation_id) ON DELETE CASCADE,
    control_id            uuid NOT NULL REFERENCES grimis_risk.controls(control_id) ON DELETE CASCADE,
    source_plan_id        uuid,  -- FK ditambahkan setelah mitigation_plans dibuat
    effectiveness_status  varchar(30) NOT NULL DEFAULT 'EFFECTIVE',
    notes                 text,
    evidence_link         text,
    created_at            timestamptz NOT NULL DEFAULT now()
);

-- lengkapi FK yang tadi ditunda (circular: causes/impacts <-> ecm)
ALTER TABLE grimis_risk.risk_causes
    ADD CONSTRAINT risk_causes_linked_ecm_id_fkey
    FOREIGN KEY (linked_ecm_id) REFERENCES grimis_risk.existing_control_mappings(ecm_id);

ALTER TABLE grimis_risk.risk_impacts
    ADD CONSTRAINT risk_impacts_linked_ecm_id_fkey
    FOREIGN KEY (linked_ecm_id) REFERENCES grimis_risk.existing_control_mappings(ecm_id);

-- mitigation_plans: control_id DIHAPUS (redundant, plan yg jalan otomatis masuk existing_control_mappings)
-- ditambah fiscal_period_id supaya jelas plan itu diajukan di tahun/periode mana
CREATE TABLE grimis_risk.mitigation_plans (
    plan_id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id            uuid NOT NULL REFERENCES grimis_risk.risk_evaluations(evaluation_id) ON DELETE CASCADE,
    fiscal_period_id         uuid NOT NULL REFERENCES grimis_core.fiscal_periods(period_id),
    action_plan              text NOT NULL,
    pic_name				 varchar(150) NOT NULL,
    pic_email 				 varchar(100),
    target_completion_date   date NOT NULL,
    allocated_budget         numeric(15,2) NOT NULL DEFAULT 0,
    execution_status         varchar(30) NOT NULL DEFAULT 'PLANNED',
    realization_notes        text,
    evidence_link            text,
    is_migrated_to_existing  boolean NOT NULL DEFAULT false,
    migrated_at              timestamptz,
    new_control_code         varchar(50),
    new_control_title        varchar(255),
    new_control_type         varchar(30),
    created_at               timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE grimis_risk.existing_control_mappings
    ADD CONSTRAINT existing_control_mappings_source_plan_id_fkey
    FOREIGN KEY (source_plan_id) REFERENCES grimis_risk.mitigation_plans(plan_id);

CREATE TABLE grimis_risk.risk_appetite (
    appetite_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_id              uuid NOT NULL REFERENCES grimis_core.risk_matrix_configs(matrix_id) ON DELETE RESTRICT,
    org_id                 uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    threshold_score        integer NOT NULL,
    parent_appetite_id     uuid REFERENCES grimis_risk.risk_appetite(appetite_id) ON DELETE SET NULL,
    is_default             boolean NOT NULL DEFAULT false,
    effective_fiscal_year  integer NOT NULL,
    set_by                 uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE RESTRICT,
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_risk.risk_simulation_results (
    simulation_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id             uuid NOT NULL REFERENCES grimis_risk.risk_evaluations(evaluation_id) ON DELETE CASCADE,
    incident_count_used       integer NOT NULL DEFAULT 0,
    iterations                integer NOT NULL DEFAULT 10000,
    expected_likelihood       numeric(6,3),
    expected_impact           numeric(6,3),
    suggestion_percentile     integer NOT NULL DEFAULT 75,
    suggested_cell_id         uuid REFERENCES grimis_core.risk_matrix_cells(cell_id) ON DELETE SET NULL,
    raw_distribution_summary  jsonb,
    generated_at              timestamptz NOT NULL DEFAULT now()
);

