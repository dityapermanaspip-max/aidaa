-- AIDAA realisation (advance, accountability, cross-subsidy). Safe to rerun. Run LAST of the patches.
-- Org scope flows through the assignment owner (same rule as budget lines, trip legs, funding allocation).

CREATE TABLE IF NOT EXISTS aidaa_core.realisation_advance (
  advance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id) ON DELETE CASCADE,
  auditor_id uuid NOT NULL REFERENCES aidaa_core.auditor(auditor_id),
  amount numeric(18,2) NOT NULL CHECK (amount >= 0),
  advance_date date NOT NULL,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES iam.users(user_id)
);

CREATE INDEX IF NOT EXISTS ix_realisation_advance_assignment ON aidaa_core.realisation_advance(assignment_id);

CREATE TABLE IF NOT EXISTS aidaa_core.realisation_cost (
  rc_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id) ON DELETE CASCADE,
  auditor_id uuid NOT NULL REFERENCES aidaa_core.auditor(auditor_id),
  component_id uuid NOT NULL REFERENCES aidaa_core.ref_cost_component(component_id),
  location_id uuid REFERENCES aidaa_core.ref_location(location_id),
  quantity numeric(12,2) NOT NULL DEFAULT 1 CHECK (quantity >= 0),
  unit_rate numeric(18,2) NOT NULL DEFAULT 0 CHECK (unit_rate >= 0),
  amount numeric(18,2) GENERATED ALWAYS AS (quantity * unit_rate) STORED,
  cost_date date NOT NULL,
  evidence_url varchar(500),
  evidence_name varchar(255),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES iam.users(user_id)
);

CREATE INDEX IF NOT EXISTS ix_realisation_cost_assignment ON aidaa_core.realisation_cost(assignment_id);
CREATE INDEX IF NOT EXISTS ix_realisation_cost_component ON aidaa_core.realisation_cost(component_id);

CREATE TABLE IF NOT EXISTS aidaa_core.realisation_settlement (
  settlement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES aidaa_core.assignment(assignment_id) ON DELETE CASCADE,
  auditor_id uuid NOT NULL REFERENCES aidaa_core.auditor(auditor_id),
  status varchar(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','settled')),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES iam.users(user_id),
  settled_at timestamptz,
  settled_by uuid REFERENCES iam.users(user_id),
  UNIQUE (assignment_id, auditor_id)
);