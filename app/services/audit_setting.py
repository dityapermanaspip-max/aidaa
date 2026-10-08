from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

NAME_JOIN = """
    LEFT JOIN LATERAL (
        SELECT official_name FROM iam.organization_details_log
        WHERE org_id = o.org_id ORDER BY valid_from DESC LIMIT 1
    ) d ON TRUE
"""

_ROOTS = """
    SELECT DISTINCT COALESCE(o.root_org_id, o.org_id) AS root_id
    FROM iam.active_user_roles m
    JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
    JOIN iam.organizations o ON o.org_id = m.org_id
    WHERE m.user_id = CAST(:u AS uuid) AND left(r.role_code, 6) = 'AIDAA.' AND m.org_id IS NOT NULL
"""

# Per-request override set by the resolve_root dependency (app/api/deps_root.py).
# get_root returns it verbatim, so a multi-root user's calls stay inside the root they picked.
ROOT_ATTR = "_aidaa_root"


def _roots(db: Session, user_id: UUID):
    return db.execute(text(_ROOTS), {"u": str(user_id)}).fetchall()


def get_accessible_roots(db: Session, user_id: UUID) -> list[UUID]:
    return [r.root_id for r in _roots(db, user_id)]


def get_root(db: Session, user_id: UUID) -> UUID:
    active = getattr(db, ROOT_ATTR, None)
    if active is not None:
        return active
    rows = _roots(db, user_id)
    if not rows:
        raise HTTPException(status_code=403, detail="No AIDAA role is assigned in an organization")
    if len(rows) > 1:
        raise HTTPException(status_code=409,
                            detail="Your AIDAA roles span more than one root organization; "
                                   "send the active root_id (query parameter or X-DH-Root header)")
    return rows[0].root_id


def get_iau_org(db: Session, root_id: UUID) -> Optional[UUID]:
    r = db.execute(text("SELECT iau_org_id FROM aidaa_core.audit_setting WHERE root_org_id = CAST(:r AS uuid)"),
                   {"r": str(root_id)}).fetchone()
    return r.iau_org_id if r else None


def get_setting(db: Session, user_id: UUID) -> dict:
    root = get_root(db, user_id)
    row = db.execute(text(f"""
        SELECT s.root_org_id, s.iau_org_id, o.org_code AS iau_org_code, d.official_name AS iau_org_name, s.updated_at
        FROM aidaa_core.audit_setting s
        JOIN iam.organizations o ON o.org_id = s.iau_org_id
        {NAME_JOIN}
        WHERE s.root_org_id = CAST(:r AS uuid)
    """), {"r": str(root)}).fetchone()
    if row:
        return dict(row._mapping)
    return {"root_org_id": root, "iau_org_id": None, "iau_org_code": None, "iau_org_name": None, "updated_at": None}


def set_iau(db: Session, user_id: UUID, iau_org_id: UUID) -> dict:
    root = get_root(db, user_id)
    ok = db.execute(text("""
        SELECT 1 FROM iam.organizations
        WHERE org_id = CAST(:i AS uuid) AND is_active = TRUE
          AND COALESCE(root_org_id, org_id) = CAST(:r AS uuid) AND org_id <> CAST(:r AS uuid)
    """), {"i": str(iau_org_id), "r": str(root)}).fetchone()
    if not ok:
        raise HTTPException(status_code=400,
                            detail="The Internal Audit Unit must be an active descendant of your root organization")

    current = get_iau_org(db, root)
    if current is not None and str(current) != str(iau_org_id):
        used = db.execute(text("""
            SELECT 1 FROM (
                SELECT p.plan_id AS id FROM aidaa_core.audit_plan p
                JOIN iam.organizations o ON o.org_id = p.owner_org_id
                WHERE COALESCE(o.root_org_id, o.org_id) = CAST(:r AS uuid)
                UNION ALL
                SELECT a.assignment_id FROM aidaa_core.assignment a
                JOIN iam.organizations o ON o.org_id = a.owner_org_id
                WHERE COALESCE(o.root_org_id, o.org_id) = CAST(:r AS uuid)
            ) x LIMIT 1
        """), {"r": str(root)}).fetchone()
        if used:
            raise HTTPException(status_code=409,
                                detail="Plans or assignments already exist, the Internal Audit Unit can no longer change")

    clash = db.execute(text("""
        WITH RECURSIVE sub AS (
            SELECT org_id FROM iam.organizations WHERE org_id = CAST(:i AS uuid)
            UNION ALL
            SELECT c.org_id FROM iam.organizations c JOIN sub ON c.parent_id = sub.org_id
        )
        SELECT u.unit_code FROM aidaa_core.ref_auditable_unit u
        WHERE u.org_id IN (SELECT org_id FROM sub) LIMIT 1
    """), {"i": str(iau_org_id)}).fetchone()
    if clash:
        raise HTTPException(status_code=409,
                            detail=f"Unit {clash.unit_code} is tagged inside this organization, untag or move it first")

    db.execute(text("""
        INSERT INTO aidaa_core.audit_setting (root_org_id, iau_org_id, updated_by)
        VALUES (CAST(:r AS uuid), CAST(:i AS uuid), CAST(:u AS uuid))
        ON CONFLICT (root_org_id) DO UPDATE
        SET iau_org_id = EXCLUDED.iau_org_id, updated_at = now(), updated_by = EXCLUDED.updated_by
    """), {"r": str(root), "i": str(iau_org_id), "u": str(user_id)})
    return get_setting(db, user_id)