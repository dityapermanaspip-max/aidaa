CREATE TABLE grimis_log.context_log (
    context_log_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name   varchar(50) NOT NULL,
    record_id    uuid NOT NULL,
    old_values   jsonb NOT NULL, -- ini all in buat log dari tabel di grimis_core
    changed_by   uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE RESTRICT,
    changed_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_log.risk_evaluation_logs (
    ev_log_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id             uuid NOT NULL REFERENCES grimis_risk.risk_evaluations(evaluation_id) ON DELETE CASCADE,
    evaluation_type           varchar(30) NOT NULL,  -- INHERENT/RESIDUAL/EXPECTED/ACTUAL
    previous_cell_id          uuid REFERENCES grimis_core.risk_matrix_cells(cell_id) ON DELETE SET NULL,
    new_cell_id               uuid NOT NULL REFERENCES grimis_core.risk_matrix_cells(cell_id) ON DELETE RESTRICT,
    likelihood_value          integer NOT NULL,
    impact_value              integer NOT NULL,
    change_reason             text NOT NULL,
    supporting_incident_id    uuid,  -- FK ditambahkan di 04_grimis_incident.sql
    supporting_simulation_id  uuid,  -- FK ditambahkan di bawah
    evaluated_by              uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE RESTRICT,
    created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_log.incident_report_audit_log (
    audit_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_report_id   uuid NOT NULL REFERENCES grimis_incident.incident_reports(incident_report_id) ON DELETE CASCADE,
    actor_user_id        uuid REFERENCES iam.users(user_id),
    action               varchar(30) NOT NULL,
    note                 text,
    created_at           timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE grimis_log.risk_evaluation_logs
    ADD CONSTRAINT risk_evaluation_logs_supporting_simulation_id_fkey
    FOREIGN KEY (supporting_simulation_id) REFERENCES grimis_risk.risk_simulation_results(simulation_id) ON DELETE SET NULL;
	
ALTER TABLE grimis_log.risk_evaluation_logs
    ADD CONSTRAINT risk_evaluation_logs_supporting_incident_id_fkey
    FOREIGN KEY (supporting_incident_id) REFERENCES grimis_incident.risk_incidents(incident_id) ON DELETE SET NULL;	
	
CREATE TABLE IF NOT EXISTS iam.password_reset_tokens (token_hash varchar(64) PRIMARY KEY, user_id uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE CASCADE, expires_at timestamptz NOT NULL, used_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());




ALTER TABLE grimis_risk.risk_appetite ADD CONSTRAINT uq_appetite UNIQUE (org_id, matrix_id, effective_fiscal_year); ALTER TABLE grimis_core.risk_matrix_criteria_details ADD CONSTRAINT uq_criteria_detail UNIQUE (category_id, level_value); ALTER TABLE grimis_core.risk_matrix_dimension_labels ADD CONSTRAINT uq_dim_label UNIQUE (matrix_id, dimension_type, level_value);

ALTER TABLE grimis_risk.process_risk_events ADD CONSTRAINT uq_pre UNIQUE (process_id, risk_event_id); ALTER TABLE grimis_core.indicator_process_mappings ADD CONSTRAINT uq_ipm UNIQUE (indicator_id, process_id);

ALTER TABLE grimis_risk.risk_evaluations ADD CONSTRAINT uq_eval_pre_year UNIQUE (pre_id, fiscal_year);

ALTER TABLE grimis_risk.controls ADD CONSTRAINT uq_control_code UNIQUE (org_id, control_code); ALTER TABLE grimis_risk.existing_control_mappings ADD CONSTRAINT uq_ecm_eval_control UNIQUE (evaluation_id, control_id);

ALTER TABLE iam.users ADD COLUMN IF NOT EXISTS token_version integer NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS iam.login_attempts (id bigserial PRIMARY KEY, identifier varchar(150) NOT NULL, ip varchar(64), attempted_at timestamptz NOT NULL DEFAULT now());

CREATE INDEX IF NOT EXISTS ix_login_attempts ON iam.login_attempts(identifier, attempted_at);