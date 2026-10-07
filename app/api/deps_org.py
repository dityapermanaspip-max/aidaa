"""Layer 1 for records: which orgs the caller may act in, and the org of a record."""
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

# Table-to-org whitelist: resource -> (table, pk column, org column). Names never come from input.
_ORG_RESOURCES = {
    "plan": ("aidaa_core.audit_plan", "plan_id", "owner_org_id"),
    "assignment": ("aidaa_core.assignment", "assignment_id", "owner_org_id"),
}


def get_user_accessible_org_ids(
    db: Session, user_id: UUID, permission_code: str
) -> Optional[List[UUID]]:
    """None = all orgs (global mapping with the permission). List = allowed orgs."""
    global_check = db.execute(text("""
        SELECT 1
        FROM iam.active_user_roles m
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
        JOIN iam.permissions p ON p.permission_id = rp.permission_id
        WHERE m.user_id = :user_id AND m.org_id IS NULL
          AND p.permission_code IN (:code, '*')
        LIMIT 1
    """), {"user_id": user_id, "code": permission_code}).fetchone()

    if global_check:
        return None

    rows = db.execute(text("""
        WITH RECURSIVE assigned_orgs AS (
            SELECT DISTINCT m.org_id
            FROM iam.active_user_roles m
            JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
            JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
            JOIN iam.permissions p ON p.permission_id = rp.permission_id
            JOIN iam.v_active_organization_applications voa
              ON voa.org_id = m.org_id AND voa.app_id = m.app_id
            WHERE m.user_id = :user_id
              AND p.permission_code IN (:code, '*')
              AND m.org_id IS NOT NULL
        ),
        org_hierarchy AS (
            SELECT o.org_id FROM iam.organizations o
            JOIN assigned_orgs ao ON o.org_id = ao.org_id
            UNION
            SELECT child.org_id FROM iam.organizations child
            JOIN org_hierarchy parent ON child.parent_id = parent.org_id
        )
        SELECT org_id FROM org_hierarchy
    """), {"user_id": user_id, "code": permission_code}).fetchall()

    return [row.org_id for row in rows]


def get_resource_org_id(db: Session, resource: str, resource_id: UUID) -> UUID:
    """Find the org of a record through the whitelist (never use raw table names from input)."""
    if resource not in _ORG_RESOURCES:
        raise HTTPException(status_code=500, detail=f"Resource '{resource}' not in org whitelist")
    table, pk, org_col = _ORG_RESOURCES[resource]
    row = db.execute(
        text(f"SELECT {org_col} AS org_id FROM {table} WHERE {pk} = CAST(:id AS uuid)"),
        {"id": str(resource_id)},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"{resource} not found")
    return row.org_id


def check_org_permission(db: Session, user, permission_code: str, resource: str, resource_id: UUID) -> UUID:
    """Layer 1 for a specific record: user must hold the permission in the record's org."""
    org_id = get_resource_org_id(db, resource, resource_id)
    allowed = get_user_accessible_org_ids(db, user.user_id, permission_code)
    if allowed is not None and org_id not in allowed:
        raise HTTPException(status_code=403, detail=f"Access denied: '{permission_code}' not held for this {resource}")
    return org_id


def check_org_any_permission(db: Session, user, permission_codes, resource: str, resource_id: UUID) -> UUID:
    last = None
    for code in permission_codes:
        try:
            return check_org_permission(db, user, code, resource, resource_id)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            last = exc
    raise last


def assert_org_access(db: Session, user, permission_code: str, org_id: UUID):
    """Layer 1 for a NEW record: user must hold the permission in the org being written to."""
    allowed = get_user_accessible_org_ids(db, user.user_id, permission_code)
    if allowed is not None and org_id not in allowed:
        raise HTTPException(status_code=403, detail=f"Access denied: '{permission_code}' not held in this organization")