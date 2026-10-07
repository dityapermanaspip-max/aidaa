from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit_setting import NAME_JOIN, get_root, get_iau_org

_TREE = """
    WITH RECURSIVE iau AS (
        SELECT org_id FROM iam.organizations WHERE org_id = CAST(:i AS uuid)
        UNION ALL
        SELECT c.org_id FROM iam.organizations c JOIN iau ON c.parent_id = iau.org_id
    )
"""


def _scope(db: Session, user_id: UUID):
    root = get_root(db, user_id)
    iau = get_iau_org(db, root)
    return root, iau


def list_org_options(db: Session, user_id: UUID) -> list[dict]:
    """Orgs under the caller's root (root excluded). in_iau marks the Internal Audit Unit subtree."""
    root, iau = _scope(db, user_id)
    rows = db.execute(text(f"""
        {_TREE}
        SELECT o.org_id, o.org_code, o.parent_id, d.official_name AS org_name,
               (o.org_id IN (SELECT org_id FROM iau)) AS in_iau
        FROM iam.organizations o
        {NAME_JOIN}
        WHERE o.is_active = TRUE AND COALESCE(o.root_org_id, o.org_id) = CAST(:r AS uuid)
          AND o.org_id <> CAST(:r AS uuid)
        ORDER BY o.org_code
    """), {"i": str(iau) if iau else None, "r": str(root)}).fetchall()
    return [dict(r._mapping) for r in rows]


def list_auditor_candidates(db: Session, user_id: UUID) -> list[dict]:
    """Users holding AIDAA.AUDITOR inside the IAU subtree who are not registered as auditors yet."""
    _, iau = _scope(db, user_id)
    if not iau:
        return []
    rows = db.execute(text(f"""
        {_TREE}
        SELECT * FROM (
            SELECT DISTINCT ON (u.user_id) u.user_id, u.username, u.full_name, u.email,
                   o.org_id, o.org_code, d.official_name AS org_name
            FROM iam.user_organization_roles m
            JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE AND r.role_code = 'AIDAA.AUDITOR'
            JOIN iam.users u ON u.user_id = m.user_id AND u.is_active = TRUE
            JOIN iam.organizations o ON o.org_id = m.org_id
            {NAME_JOIN}
            WHERE m.is_active = TRUE AND o.org_id IN (SELECT org_id FROM iau)
              AND NOT EXISTS (SELECT 1 FROM aidaa_core.auditor a WHERE a.user_id = u.user_id)
            ORDER BY u.user_id, m.created_at
        ) c ORDER BY c.username
    """), {"i": str(iau)}).fetchall()
    return [dict(r._mapping) for r in rows]


def assert_client_org(db: Session, user_id: UUID, org_id: UUID):
    """The org must be under the caller's root and outside the Internal Audit Unit subtree."""
    root, iau = _scope(db, user_id)
    if iau is None:
        raise HTTPException(status_code=409, detail="Designate the Internal Audit Unit first (Audit Setting)")
    row = db.execute(text(f"""
        {_TREE}
        SELECT (o.org_id IN (SELECT org_id FROM iau)) AS in_iau
        FROM iam.organizations o
        WHERE o.org_id = CAST(:o AS uuid) AND o.is_active = TRUE
          AND COALESCE(o.root_org_id, o.org_id) = CAST(:r AS uuid) AND o.org_id <> CAST(:r AS uuid)
    """), {"i": str(iau), "o": str(org_id), "r": str(root)}).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Organization is not an active org under your root")
    if row.in_iau:
        raise HTTPException(status_code=409, detail="Organizations inside the Internal Audit Unit cannot be audited")
        

def assert_owner_org(db: Session, user_id: UUID, org_id: UUID):
    """Plans and assignments belong to the audit team side: an active org inside the IAU subtree."""
    root, iau = _scope(db, user_id)
    if iau is None:
        raise HTTPException(status_code=409, detail="Designate the Internal Audit Unit first (Audit Setting)")
    row = db.execute(text(f"""
        {_TREE}
        SELECT 1 FROM iam.organizations o
        WHERE o.org_id = CAST(:o AS uuid) AND o.is_active = TRUE
          AND COALESCE(o.root_org_id, o.org_id) = CAST(:r AS uuid)
          AND o.org_id IN (SELECT org_id FROM iau)
    """), {"i": str(iau), "o": str(org_id), "r": str(root)}).fetchone()
    if not row:
        raise HTTPException(status_code=400,
                            detail="Owner organization must be an active org inside the Internal Audit Unit")