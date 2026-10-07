from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

_MEMBER = {
    "audit.assignment.read", "audit.team.read", "audit.budget.read", "audit.deviation.read",
    "audit.task.read", "audit.pka.read", "audit.pka.create", "audit.pka.update",
    "audit.paper.read", "audit.paper.create", "audit.paper.update",
    "audit.finding.read", "audit.finding.create", "audit.finding.update",
    "audit.rekomend.read", "audit.rekomend.create", "audit.rekomend.update",
    "audit.report.read",
}
_LEADER = _MEMBER | {
    "audit.paper.review", "audit.budget.draft", "audit.finding.communicate",
    "audit.report.create", "audit.report.update",
}
_SUPERVISOR = _MEMBER | {
    "audit.paper.review", "audit.pka.approve", "audit.finding.approve",
    "audit.rekomend.close", "audit.assignment.approve_change", "audit.team.approve_replace",
    "audit.finding.communicate",
}

# Starting matrix, adjust to the real rules.
ROLE_ACTIONS = {"member": _MEMBER, "leader": _LEADER, "supervisor": _SUPERVISOR}
BOUND = set().union(*ROLE_ACTIONS.values())  # codes that need an assignment role (unless read)
AUDITEE_ONLY = {"audit.finding.respond", "audit.rekomend.followup"}


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
    row = db.execute(text("""
        WITH RECURSIVE anc AS (
            SELECT org_id, parent_id FROM iam.organizations WHERE org_id = CAST(:o AS uuid)
            UNION ALL
            SELECT o.org_id, o.parent_id FROM iam.organizations o JOIN anc a ON o.org_id = a.parent_id
        )
        SELECT 1 FROM iam.active_user_roles m
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        WHERE m.user_id = CAST(:u AS uuid) AND r.role_code = 'AIDAA.AUDITEE_PIC'
          AND m.org_id IS NOT NULL AND m.org_id IN (SELECT org_id FROM anc)
        LIMIT 1
    """), {"o": str(unit_org_id), "u": str(user_id)}).fetchone()
    return row is not None


def pic_unit_orgs(db: Session, user_id: UUID, unit_org_ids: list) -> list:
    """The audited unit orgs (of the given list) where this user is the auditee PIC."""
    return [o for o in unit_org_ids if is_auditee_pic(db, user_id, o)]


def _perm_codes(db: Session, user_id: UUID, org_id: UUID) -> set:
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


def _global_roles(db: Session, user_id: UUID) -> list[str]:
    rows = db.execute(text("""
        SELECT DISTINCT r.role_code FROM iam.active_user_roles m
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        WHERE m.user_id = CAST(:u AS uuid) AND r.role_code LIKE 'AIDAA.%'
        ORDER BY r.role_code
    """), {"u": str(user_id)}).fetchall()
    return [r.role_code for r in rows]


def get_my_access(db: Session, user_id: UUID, assignment_id: UUID) -> dict:
    scope = assignment_scope(db, assignment_id)
    role = my_assignment_role(db, user_id, assignment_id)
    pic_orgs = pic_unit_orgs(db, user_id, scope["unit_org_ids"])
    pic = bool(pic_orgs)

    codes = _perm_codes(db, user_id, scope["owner_org_id"])
    for org_id in pic_orgs:
        codes |= _perm_codes(db, user_id, org_id)
    if not codes:
        raise HTTPException(status_code=403, detail="No access to this assignment")

    allowed_by_role = ROLE_ACTIONS.get(role, set())
    actions = {
        c for c in codes
        if (c.endswith(".read") or c not in BOUND or c in allowed_by_role)
        and (c not in AUDITEE_ONLY or pic)
    }
    return {
        "assignment_id": assignment_id,
        "assignment_role": role,
        "is_auditee_pic": pic,
        "global_roles": _global_roles(db, user_id),
        "actions": sorted(actions),
    }


def assert_assignment_visible(db: Session, user_id: UUID, assignment_id: UUID) -> Optional[str]:
    """Layer 2 for reads: an AUDITOR-only user must be on the assignment team."""
    role = my_assignment_role(db, user_id, assignment_id)
    if role:
        return role
    if set(_global_roles(db, user_id)) == {"AIDAA.AUDITOR"}:
        raise HTTPException(status_code=403, detail="You are not on this assignment's team")
    return None