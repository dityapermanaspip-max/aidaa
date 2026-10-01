CREATE TABLE iam.organizations (
    org_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_code     varchar(50) NOT NULL,
    parent_id    uuid REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    root_org_id  uuid,
    is_active    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE iam.organizations
    ADD CONSTRAINT organizations_root_org_id_fkey
    FOREIGN KEY (root_org_id) REFERENCES iam.organizations(org_id);

CREATE TABLE iam.organization_details_log (
    log_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    official_name  varchar(255) NOT NULL,
    short_name     varchar(50),
    address        text,
    leader_name    varchar(150),
    phone_number   varchar(30),
    email          varchar(100),
    fax_number     varchar(30),
    logo_url       varchar(255),
    valid_from     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid
);

CREATE TABLE iam.users (
    user_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username       varchar(50) NOT NULL UNIQUE,
    email          varchar(100) NOT NULL UNIQUE,
    password_hash  varchar(255) NOT NULL,
    full_name      varchar(150) NOT NULL,
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.user_details_log (
    log_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE CASCADE,
    full_name       varchar(150) NOT NULL,
    identity_number varchar(50),
    position_title  varchar(150),
    phone_number    varchar(30),
    avatar_url      varchar(255),
    valid_from      timestamptz NOT NULL DEFAULT now(),
    updated_by      uuid
);

CREATE TABLE iam.user_preferences (
    user_id       uuid PRIMARY KEY REFERENCES iam.users(user_id) ON DELETE CASCADE,
    theme_mode    varchar(20) NOT NULL DEFAULT 'dark',
    custom_theme  jsonb,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.applications (
    app_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_code     varchar(50) NOT NULL UNIQUE,
    app_name     varchar(100) NOT NULL,
    description  text,
    is_active    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.organization_applications (
    org_app_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    app_id        uuid NOT NULL REFERENCES iam.applications(app_id) ON DELETE CASCADE,
    is_active     boolean NOT NULL DEFAULT true,
    activated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.roles (
    role_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id            uuid REFERENCES iam.applications(app_id) ON DELETE CASCADE,
    role_code         varchar(50) NOT NULL,
    role_name         varchar(100) NOT NULL,
    description       text,
    permission_flags  jsonb NOT NULL DEFAULT '[]'::jsonb,
    is_active         boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.permissions (
    permission_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id            uuid NOT NULL REFERENCES iam.applications(app_id),
    permission_code   varchar(100) NOT NULL,
    permission_label  varchar(150) NOT NULL,
    description       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.role_permissions (
    role_permission_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id             uuid NOT NULL REFERENCES iam.roles(role_id),
    permission_id       uuid NOT NULL REFERENCES iam.permissions(permission_id),
    is_allowed          boolean NOT NULL DEFAULT true,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.user_organization_roles (
    mapping_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES iam.users(user_id) ON DELETE CASCADE,
    org_id      uuid REFERENCES iam.organizations(org_id) ON DELETE CASCADE,
    app_id      uuid REFERENCES iam.applications(app_id) ON DELETE CASCADE,
    role_id     uuid NOT NULL REFERENCES iam.roles(role_id) ON DELETE CASCADE,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE iam.audit_log (
    log_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id     uuid REFERENCES iam.users(user_id),
    action       varchar(100) NOT NULL,
    target_type  varchar(50) NOT NULL,
    target_id    uuid,
    metadata     jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE VIEW iam.active_user_roles AS
SELECT mapping_id, user_id, org_id, app_id, role_id, created_at, is_active
FROM iam.user_organization_roles
WHERE is_active = true;

CREATE VIEW iam.v_active_organization_applications AS
SELECT DISTINCT o.org_id, oa.app_id, a.app_code, a.app_name, oa.is_active
FROM iam.organizations o
JOIN iam.organizations root_org ON root_org.org_id = COALESCE(o.root_org_id, o.org_id)
JOIN iam.organization_applications oa ON oa.org_id = root_org.org_id
JOIN iam.applications a ON oa.app_id = a.app_id
WHERE oa.is_active = true AND a.is_active = true;