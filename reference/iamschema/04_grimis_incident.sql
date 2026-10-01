CREATE TABLE grimis_incident.risk_incidents (
    incident_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pre_id                  uuid NOT NULL REFERENCES grimis_risk.process_risk_events(pre_id) ON DELETE CASCADE,
    incident_date           date NOT NULL,
    incident_description    text NOT NULL,
    actual_impact_value     integer NOT NULL,
    impact_category         varchar(50),
    reported_by             uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE RESTRICT,
    is_used_in_simulation   boolean NOT NULL DEFAULT true,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_incident.incident_reports (
    incident_report_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    reporter_name           varchar(255),
    description             text NOT NULL,
    location                varchar(255),
    incident_time           timestamptz NOT NULL,
    photo_url               text,
    status                  varchar(20) NOT NULL DEFAULT 'PENDING',
    linked_risk_event_id    uuid REFERENCES grimis_risk.risk_events(risk_event_id) ON DELETE SET NULL,
    financial_loss_estimate numeric,
    linked_impact_ids       jsonb NOT NULL DEFAULT '[]'::jsonb,
    linked_cause_ids        jsonb NOT NULL DEFAULT '[]'::jsonb,
    reviewed_by             uuid REFERENCES iam.users(user_id),
    reviewed_at             timestamptz,
    decision_note           text,
    submitted_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grimis_incident.incident_ai_matches (
    match_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_report_id       uuid NOT NULL REFERENCES grimis_incident.incident_reports(incident_report_id) ON DELETE CASCADE,
    suggested_risk_event_id  uuid REFERENCES grimis_risk.risk_events(risk_event_id) ON DELETE SET NULL,
    confidence_note          text,
    rank                     integer NOT NULL,
    status                   varchar(20) NOT NULL DEFAULT 'SUGGESTED',
    model_used               varchar(100),
    created_at               timestamptz NOT NULL DEFAULT now()
);