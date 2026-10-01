CREATE TABLE grimis_core.mandates (
    mandate_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    mandate_code       varchar(50) NOT NULL,
    mandate_name       text NOT NULL,
    issuing_authority  varchar(150),
    description        text,
    is_active          boolean NOT NULL DEFAULT true,
    created_by         uuid REFERENCES iam.users(user_id) ON DELETE RESTRICT,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_core.strategic_objectives (
    objective_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mandate_id         uuid REFERENCES grimis_core.mandates(mandate_id) ON DELETE SET NULL,
    org_id             uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    assigned_position  varchar(150) NOT NULL,
    objective_title    text NOT NULL,
    fiscal_year        integer NOT NULL,
    is_active          boolean NOT NULL DEFAULT true,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_core.business_processes (
    process_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    process_code           varchar(50) NOT NULL,
    process_name           text NOT NULL,
    process_owner_org_id   uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    description            text,
    execution_type         varchar(50),
    is_active              boolean NOT NULL DEFAULT true,
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_core.performance_indicators (
    indicator_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    objective_id         uuid NOT NULL REFERENCES grimis_core.strategic_objectives(objective_id) ON DELETE CASCADE,
    indicator_code       varchar(50) NOT NULL,
    indicator_name       text NOT NULL,
    target_value         numeric(15,2) NOT NULL,
    unit_of_measurement  varchar(50) NOT NULL,
    baseline_value       numeric(15,2),
    is_active            boolean NOT NULL DEFAULT true,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_core.indicator_process_mappings (
    ipm_id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_id         uuid NOT NULL REFERENCES grimis_core.performance_indicators(indicator_id) ON DELETE CASCADE,
    process_id           uuid NOT NULL REFERENCES grimis_core.business_processes(process_id) ON DELETE CASCADE,
    contribution_weight  numeric(5,2),
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_core.fiscal_periods (
    period_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    root_org_id   uuid NOT NULL REFERENCES iam.organizations(org_id),
    fiscal_year   integer NOT NULL,
    is_open       boolean NOT NULL DEFAULT true,
    opened_by     uuid NOT NULL REFERENCES iam.users(user_id),
    opened_at     timestamptz NOT NULL DEFAULT now(),
    closed_at     timestamptz
);

CREATE TABLE grimis_core.risk_matrix_configs (
    matrix_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_name           varchar(100) NOT NULL,
    max_likelihood_level  integer NOT NULL DEFAULT 5,
    max_impact_level      integer NOT NULL DEFAULT 5,
    is_active             boolean NOT NULL DEFAULT true,
    org_id                uuid NOT NULL REFERENCES iam.organizations(org_id),
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_core.risk_matrix_cells (
    cell_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_id         uuid NOT NULL REFERENCES grimis_core.risk_matrix_configs(matrix_id) ON DELETE CASCADE,
    likelihood_level  integer NOT NULL,
    impact_level      integer NOT NULL,
    cell_score        integer NOT NULL,
    zone_label        varchar(50) NOT NULL,
    color_hex         varchar(7) NOT NULL
);

CREATE TABLE grimis_core.risk_matrix_criteria_categories (
    category_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_id       uuid NOT NULL REFERENCES grimis_core.risk_matrix_configs(matrix_id) ON DELETE CASCADE,
    dimension_type  varchar(20) NOT NULL,
    category_name   varchar(150) NOT NULL,
    row_order       integer NOT NULL
);

CREATE TABLE grimis_core.risk_matrix_criteria_details (
    detail_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id   uuid NOT NULL REFERENCES grimis_core.risk_matrix_criteria_categories(category_id) ON DELETE CASCADE,
    level_value   integer NOT NULL,
    criteria_text text NOT NULL
);

CREATE TABLE grimis_core.risk_matrix_dimension_labels (
    label_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_id       uuid NOT NULL REFERENCES grimis_core.risk_matrix_configs(matrix_id) ON DELETE CASCADE,
    dimension_type  varchar(20) NOT NULL,
    level_value     integer NOT NULL,
    label_name      varchar(100) NOT NULL
);