from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.budget import BudgetLineCreate
from app.services.masters import _exists
from app.services.plans import get_plan, _assert_editable
from app.services.budget_core import LINE_COLS, resolve_price, insert_line
from app.services.scope import root_of_org


def assert_plan_drafter(db: Session, user_id: UUID, plan_id: UUID):
    ok = db.execute(text("""
        SELECT 1 FROM aidaa_core.audit_plan_member m
        JOIN aidaa_core.auditor a ON a.auditor_id = m.auditor_id
        WHERE m.plan_id = CAST(:p AS uuid) AND a.user_id = CAST(:u AS uuid) AND m.is_budget_drafter = TRUE
    """), {"p": str(plan_id), "u": str(user_id)}).fetchone()
    if not ok:
        raise HTTPException(status_code=403, detail="Only the plan's budget drafter can change its budget lines")


def _draft_version(db: Session, plan_id: UUID) -> int:
    return db.execute(text("""
        SELECT COALESCE(MAX(version_no), 0) + 1 AS n FROM aidaa_core.audit_plan_version
        WHERE plan_id = CAST(:p AS uuid)
    """), {"p": str(plan_id)}).fetchone().n


def editable_plan(db: Session, plan_id: UUID, user_id: UUID) -> int:
    """Checks the plan can take budget lines from this user. Returns the draft version number."""
    plan = get_plan(db, plan_id)
    _assert_editable(plan)
    if plan["budget_mode"] != "detailed":
        raise HTTPException(status_code=409, detail="Plan budget_mode is lumpsum, switch it to detailed first")
    assert_plan_drafter(db, user_id, plan_id)
    return _draft_version(db, plan_id)


def list_plan_lines(db: Session, plan_id: UUID, version_no: Optional[int] = None) -> list[dict]:
    _exists(db, "aidaa_core.audit_plan", "plan_id", plan_id, "Plan")
    rows = db.execute(text(f"""
        SELECT {LINE_COLS} FROM aidaa_core.budget_line
        WHERE plan_id = CAST(:p AS uuid) AND (CAST(:v AS int) IS NULL OR version_no = CAST(:v AS int))
        ORDER BY version_no DESC, created_at
    """), {"p": str(plan_id), "v": version_no}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_plan_line(db: Session, plan_id: UUID, payload: BudgetLineCreate, user_id: UUID) -> dict:
    version = editable_plan(db, plan_id, user_id)
    if payload.auditor_id:
        ok = db.execute(text("""
            SELECT 1 FROM aidaa_core.audit_plan_member
            WHERE plan_id = CAST(:p AS uuid) AND auditor_id = CAST(:a AS uuid)
        """), {"p": str(plan_id), "a": str(payload.auditor_id)}).fetchone()
        if not ok:
            raise HTTPException(status_code=400, detail="Auditor is not a member of this plan")
    plan = get_plan(db, plan_id)
    price = resolve_price(db, payload.component_id, payload.rate_id, payload.unit_rate, payload.location_id,
                          root_id=root_of_org(db, plan["owner_org_id"]), period_start=plan["period_start"])
    return insert_line(db, plan_id, None, version, payload, price, user_id)


def carry_over_plan_lines(db: Session, plan_id: UUID, user_id: UUID) -> list[dict]:
    version = editable_plan(db, plan_id, user_id)
    if list_plan_lines(db, plan_id, version):
        raise HTTPException(status_code=409, detail="The draft version already has lines")
    prev = db.execute(text("""
        SELECT MAX(version_no) AS v FROM aidaa_core.budget_line
        WHERE plan_id = CAST(:p AS uuid) AND version_no < :v
    """), {"p": str(plan_id), "v": version}).fetchone().v
    if prev is None:
        raise HTTPException(status_code=404, detail="No earlier version to carry over")
    db.execute(text("""
        INSERT INTO aidaa_core.budget_line
            (plan_id, version_no, auditor_id, component_id, location_id, rate_id, copied_from_line_id,
             quantity, unit_rate, basis, source, notes, created_by, updated_by)
        SELECT plan_id, :v, auditor_id, component_id, location_id, rate_id, line_id,
               quantity, unit_rate, basis, source, notes, CAST(:u AS uuid), CAST(:u AS uuid)
        FROM aidaa_core.budget_line WHERE plan_id = CAST(:p AS uuid) AND version_no = :prev
    """), {"p": str(plan_id), "v": version, "prev": prev, "u": str(user_id)})
    return list_plan_lines(db, plan_id, version)