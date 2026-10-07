from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.budget import BudgetLineCreate
from app.services.plans import get_plan
from app.services.roles import my_assignment_role
from app.services.budget_core import LINE_COLS, get_assignment_row, resolve_price, insert_line
from app.services.scope import root_of_org


def assert_assignment_leader(db: Session, user_id: UUID, assignment_id: UUID):
    if my_assignment_role(db, user_id, assignment_id) != "leader":
        raise HTTPException(status_code=403, detail="Only the assignment leader can change its budget lines")


def draft_assignment(db: Session, assignment_id: UUID, user_id: UUID):
    """Budget lines change only while the assignment is draft, and only by its leader."""
    a = get_assignment_row(db, assignment_id)
    if a.status != "draft":
        raise HTTPException(status_code=409,
                            detail="Budget lines can only be changed while the assignment is draft")
    assert_assignment_leader(db, user_id, assignment_id)
    return a


def list_assignment_lines(db: Session, assignment_id: UUID) -> list[dict]:
    get_assignment_row(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {LINE_COLS} FROM aidaa_core.budget_line
        WHERE assignment_id = CAST(:a AS uuid) ORDER BY created_at
    """), {"a": str(assignment_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_assignment_line(db: Session, assignment_id: UUID, payload: BudgetLineCreate, user_id: UUID) -> dict:
    a = draft_assignment(db, assignment_id, user_id)
    if payload.auditor_id:
        ok = db.execute(text("""
            SELECT 1 FROM aidaa_core.assignment_member
            WHERE assignment_id = CAST(:a AS uuid) AND auditor_id = CAST(:au AS uuid) AND end_date IS NULL
        """), {"a": str(assignment_id), "au": str(payload.auditor_id)}).fetchone()
        if not ok:
            raise HTTPException(status_code=400, detail="Auditor is not an active team member")
    price = resolve_price(db, payload.component_id, payload.rate_id, payload.unit_rate, payload.location_id,
                          root_id=root_of_org(db, a.owner_org_id), period_start=a.start_date)
    return insert_line(db, None, assignment_id, 1, payload, price, user_id)
    

def copy_plan_lines(db: Session, a: dict, user_id: UUID) -> int:
    """Called at issue: copies the approved plan version's lines into the assignment (rate frozen as in the plan)."""
    plan = get_plan(db, a["plan_id"])
    if plan["budget_mode"] != "detailed":
        return 0
    res = db.execute(text("""
        INSERT INTO aidaa_core.budget_line
            (assignment_id, version_no, auditor_id, component_id, location_id, rate_id,
             copied_from_line_id, quantity, unit_rate, basis, source, approval_status, notes,
             created_by, updated_by)
        SELECT CAST(:a AS uuid), 1, l.auditor_id, l.component_id, l.location_id, l.rate_id,
               l.line_id, l.quantity, l.unit_rate, l.basis, l.source, 'approved', l.notes,
               CAST(:u AS uuid), CAST(:u AS uuid)
        FROM aidaa_core.budget_line l
        WHERE l.plan_id = CAST(:p AS uuid) AND l.version_no = :v
          AND NOT EXISTS (SELECT 1 FROM aidaa_core.budget_line c
                          WHERE c.assignment_id = CAST(:a AS uuid) AND c.copied_from_line_id = l.line_id)
    """), {"a": str(a["assignment_id"]), "p": str(a["plan_id"]),
           "v": plan["current_version_no"], "u": str(user_id)})
    return res.rowcount