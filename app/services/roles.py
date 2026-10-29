from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.request_memo import memo

# Write permission gates live in the routers (require_permission + authorize_assignment role
# checks). The old guessed ROLE_ACTIONS/BOUND/actions matrix was removed (2026-10-25): nothing
# consumed it and it had drifted from the real gates.
#
# Only IAM-derived answers are memoised (upscale audit finding 7). Assignment and member rows are
# written by this same app, so my_assignment_role and assignment_scope stay uncached: a request
# that changes the team must not read its old role back from a cache.


def my_assignment_role(db: Session, user_id: UUID, assignment_id: UUID) -> Optional[str]:
    """Layer 2 helper: caller's role in this assignment today, or None."""
    row = db.execute(text("""
        SELECT m.role FROM aidaa_core.assignment_member m
        JOIN aidaa_core.auditor a ON a.auditor_id = m.auditor_id
        WHERE m.assignment_id = CAST(:a AS uuid) AND a.user_id = CAST(:u AS uuid)
          AND m.start_date <= CURRENT_DATE
          AND (m.end_date IS NULL OR m.end_date >= CURRENT_DATE)
        LIMIT 1
    """), {"a": str(assignment_id), "u": str(user_id)}).fetchone()
    return row.role if row else None


def assignment_scope(db: Session, assignment_id: UUID) -> dict:
    """Owner org, status and the orgs of ALL audited units (usually one) of an assignment."""
    row = db.execute(text("""
        SELECT owner_org_id, status FROM aidaa_core.assignment WHERE assignment_id = CAST(:a AS uuid)
    """), {"a": str(assignment_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    orgs = db.execute(text("""
        SELECT DISTINCT u.org_id FROM aidaa_core.ref_auditable_unit u
        WHERE u.org_id IS NOT NULL AND u.unit_id IN (
            SELECT unit_id FROM aidaa_core.assignment_unit WHERE assignment_id = CAST(:a AS uuid)
            UNION
            SELECT unit_id FROM aidaa_core.assignment WHERE assignment_id = CAST(:a AS uuid))
    """), {"a": str(assignment_id)}).fetchall()
    return {"owner_org_id": row.owner_org_id, "status": row.status,
            "unit_org_ids": [r.org_id for r in orgs]}


def is_auditee_pic(db: Session, user_id: UUID, unit_org_id: Optional[UUID]) -> bool:
    if unit_org_id is None:
        return False
    return bool(pic_unit_orgs(db, user_id, [unit_org_id]))


def pic_unit_orgs(db: Session, user_id: UUID, unit_org_ids: list) -> list:
    """The audited unit orgs (of the given list) where this user is the auditee PIC.

    One recursive query for the whole list instead of one per unit (upscale audit
    finding 14). Each unit org walks its own ancestor chain, so a user holding the
    PIC role in a parent org covers every unit below it, exactly like is_auditee_pic.
    """
    if not unit_org_ids:
        return []
    rows = db.execute(text("""
        WITH RECURSIVE anc AS (
            SELECT u.org_id AS unit_org_id, o.org_id, o.parent_id
            FROM unnest(CAST(:orgs AS uuid[])) AS u(org_id)
            JOIN iam.organizations o ON o.org_id = u.org_id
            UNION ALL
            SELECT a.unit_org_id, o.org_id, o.parent_id
            FROM anc a JOIN iam.organizations o ON o.org_id = a.parent_id
        )
        SELECT DISTINCT a.unit_org_id
        FROM anc a
        JOIN iam.active_user_roles m ON m.org_id = a.org_id
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        WHERE m.user_id = CAST(:u AS uuid) AND r.role_code = 'AIDAA.AUDITEE_PIC'
    """), {"u": str(user_id), "orgs": [str(o) for o in unit_org_ids]}).fetchall()
    found = {row.unit_org_id for row in rows}
    return [o for o in unit_org_ids if o in found]


def _perm_codes(db: Session, user_id: UUID, org_id: UUID) -> set:
    def load() -> set:
        rows = db.execute(text("""
            WITH RECURSIVE anc AS (
                SELECT org_id, parent_id FROM iam.organizations WHERE org_id = CAST(:o AS uuid)
                UNION ALL
                SELECT o.org_id, o.parent_id FROM iam.organizations o JOIN anc a ON o.org_id = a.parent_id
            )
            SELECT DISTINCT p.permission_code
            FROM iam.active_user_roles m
            JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
            JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
            JOIN iam.permissions p ON p.permission_id = rp.permission_id
            WHERE m.user_id = CAST(:u AS uuid)
              AND p.permission_code LIKE 'audit.%'
              AND (m.org_id IS NULL OR m.org_id IN (SELECT org_id FROM anc))
        """), {"o": str(org_id), "u": str(user_id)}).fetchall()
        return {r.permission_code for r in rows}

    return memo(db, ("perm_codes", str(user_id), str(org_id)), load)


def _global_roles(db: Session, user_id: UUID) -> list[str]:
    def load() -> list[str]:
        rows = db.execute(text("""
            SELECT DISTINCT r.role_code FROM iam.active_user_roles m
            JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
            WHERE m.user_id = CAST(:u AS uuid) AND r.role_code LIKE 'AIDAA.%'
            ORDER BY r.role_code
        """), {"u": str(user_id)}).fetchall()
        return [r.role_code for r in rows]

    return memo(db, ("global_roles", str(user_id)), load)


def get_my_access(db: Session, user_id: UUID, assignment_id: UUID) -> dict:
    scope = assignment_scope(db, assignment_id)
    role = my_assignment_role(db, user_id, assignment_id)
    pic_orgs = pic_unit_orgs(db, user_id, scope["unit_org_ids"])

    # Scope probe on the owner org plus the caller's PIC unit orgs: no effective audit.*
    # permission there means 403.
    # Copy before the union: _perm_codes returns the memoised set, and `|=` would
    # otherwise write the PIC org codes into the cache entry of the owner org.
    codes = set(_perm_codes(db, user_id, scope["owner_org_id"]))
    for org_id in pic_orgs:
        codes |= _perm_codes(db, user_id, org_id)
    if not codes:
        raise HTTPException(status_code=403, detail="No access to this assignment")

    return {
        "assignment_id": assignment_id,
        "assignment_role": role,
        "is_auditee_pic": bool(pic_orgs),
        "global_roles": _global_roles(db, user_id),
    }


def assert_assignment_visible(db: Session, user_id: UUID, assignment_id: UUID) -> Optional[str]:
    """Layer 2 for reads: an AUDITOR-only user must be on the assignment team."""
    role = my_assignment_role(db, user_id, assignment_id)
    if role:
        return role
    if set(_global_roles(db, user_id)) == {"AIDAA.AUDITOR"}:
        raise HTTPException(status_code=403, detail="You are not on this assignment's team")
    return None