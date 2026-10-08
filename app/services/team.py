from datetime import date
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.team import MemberAdd, MemberEnd, MemberReplace, MemberRoleChange
from app.services.assignments import get_assignment
from app.services.conflict import check_conflict
from app.services.logs import log_team
from app.services.plans import list_members as list_plan_members
from app.services.scope import root_of_org

_OPEN = ("draft", "issued", "ongoing")

_MEM_SQL = """
    SELECT m.member_id, m.assignment_id, m.auditor_id, u.username, m.role, m.start_date,
           m.end_date, m.end_reason, m.created_at
    FROM aidaa_core.assignment_member m
    JOIN aidaa_core.auditor a ON a.auditor_id = m.auditor_id
    JOIN iam.users u ON u.user_id = a.user_id
"""


def _open_assignment(db: Session, assignment_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in _OPEN:
        raise HTTPException(status_code=409, detail="Assignment is finished or cancelled, team is locked")
    return a


def _default_start(a: dict) -> date:
    return a["start_date"] if a["status"] == "draft" else date.today()


def list_team(db: Session, assignment_id: UUID, current_only: bool = True) -> list[dict]:
    get_assignment(db, assignment_id)  # 404 if missing
    rows = db.execute(text(f"""{_MEM_SQL}
        WHERE m.assignment_id = CAST(:a AS uuid) AND (:cur = FALSE OR m.end_date IS NULL)
        ORDER BY m.start_date, m.created_at
    """), {"a": str(assignment_id), "cur": current_only}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_member(db: Session, assignment_id: UUID, member_id: UUID) -> dict:
    row = db.execute(text(f"""{_MEM_SQL}
        WHERE m.member_id = CAST(:m AS uuid) AND m.assignment_id = CAST(:a AS uuid)
    """), {"m": str(member_id), "a": str(assignment_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Team member not found")
    return dict(row._mapping)


def _validate_auditor(db: Session, auditor_id: UUID, a: dict, user_id: UUID):
    aud = db.execute(text("""
        SELECT user_id, status, is_active FROM aidaa_core.auditor
        WHERE auditor_id = CAST(:a AS uuid) AND root_org_id = CAST(:r AS uuid)
    """), {"a": str(auditor_id), "r": str(root_of_org(db, a["owner_org_id"]))}).fetchone()
    if not aud:
        raise HTTPException(status_code=404, detail="Auditor not found")
    if not aud.is_active or aud.status != "active":
        raise HTTPException(status_code=409, detail="Auditor is not active")
    holds = db.execute(text("""
        SELECT 1 FROM iam.active_user_roles m JOIN iam.roles r ON r.role_id = m.role_id
        WHERE m.user_id = CAST(:u AS uuid) AND r.role_code = 'AIDAA.AUDITOR' AND r.is_active = TRUE
        LIMIT 1
    """), {"u": str(aud.user_id)}).fetchone()
    if not holds:
        raise HTTPException(status_code=409, detail="Person does not hold the AIDAA.AUDITOR role")
    # conflict of interest against EVERY unit of the assignment (usually just one)
    for org_id in a["unit_org_ids"] or [None]:
        check_conflict(db, auditor_id, org_id, user_id, assignment_id=a["assignment_id"])

def _insert(db: Session, a: dict, auditor_id: UUID, role: str, start: date, user_id: UUID) -> UUID:
    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.assignment_member
                (assignment_id, auditor_id, role, start_date, created_by)
            VALUES (CAST(:a AS uuid), CAST(:au AS uuid), :r, :s, CAST(:uid AS uuid))
            RETURNING member_id
        """), {"a": str(a["assignment_id"]), "au": str(auditor_id), "r": role,
               "s": start, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Auditor already has an active role in this assignment")
    return row.member_id


def _end(db: Session, m: dict, end_date: Optional[date], reason: str) -> date:
    end = max(end_date or date.today(), m["start_date"])
    db.execute(text("""
        UPDATE aidaa_core.assignment_member SET end_date = :e, end_reason = :r
        WHERE member_id = CAST(:id AS uuid) AND end_date IS NULL
    """), {"e": end, "r": reason, "id": str(m["member_id"])})
    return end


def _active_member(db: Session, assignment_id: UUID, member_id: UUID) -> dict:
    m = get_member(db, assignment_id, member_id)
    if m["end_date"] is not None:
        raise HTTPException(status_code=409, detail="Member already ended")
    return m


def add_member(db: Session, assignment_id: UUID, payload: MemberAdd, user_id: UUID) -> dict:
    a = _open_assignment(db, assignment_id)
    _validate_auditor(db, payload.auditor_id, a, user_id)
    member_id = _insert(db, a, payload.auditor_id, payload.role,
                        payload.start_date or _default_start(a), user_id)
    log_team(db, "add", user_id, assignment_id=assignment_id, auditor_id=payload.auditor_id,
             role=payload.role)
    return get_member(db, assignment_id, member_id)


def add_from_plan(db: Session, assignment_id: UUID, user_id: UUID) -> list[dict]:
    a = _open_assignment(db, assignment_id)
    if not a["plan_id"]:
        raise HTTPException(status_code=400, detail="Unplanned assignment has no plan team to copy")
    active = {str(r.auditor_id) for r in db.execute(text("""
        SELECT auditor_id FROM aidaa_core.assignment_member
        WHERE assignment_id = CAST(:a AS uuid) AND end_date IS NULL
    """), {"a": str(assignment_id)}).fetchall()}
    todo = [m for m in list_plan_members(db, a["plan_id"]) if str(m["auditor_id"]) not in active]
    if not todo:
        raise HTTPException(status_code=409, detail="Nothing to copy, all plan members are already in the team")
    for m in todo:  # validate everyone first, a conflict block commits its own log row
        _validate_auditor(db, m["auditor_id"], a, user_id)
    for m in todo:
        _insert(db, a, m["auditor_id"], m["assignment_role"], _default_start(a), user_id)
        log_team(db, "add", user_id, assignment_id=assignment_id, auditor_id=m["auditor_id"],
                 role=m["assignment_role"], reason="copied from plan")
    return list_team(db, assignment_id)


def remove_member(db: Session, assignment_id: UUID, member_id: UUID, payload: MemberEnd, user_id: UUID) -> dict:
    _open_assignment(db, assignment_id)
    m = _active_member(db, assignment_id, member_id)
    _end(db, m, payload.end_date, payload.reason)
    log_team(db, "remove", user_id, assignment_id=assignment_id, auditor_id=m["auditor_id"],
             role=m["role"], reason=payload.reason)
    return get_member(db, assignment_id, member_id)


def replace_member(db: Session, assignment_id: UUID, member_id: UUID, payload: MemberReplace, user_id: UUID) -> dict:
    a = _open_assignment(db, assignment_id)
    old = _active_member(db, assignment_id, member_id)
    if str(payload.new_auditor_id) == str(old["auditor_id"]):
        raise HTTPException(status_code=400, detail="New auditor is the same person")
    _validate_auditor(db, payload.new_auditor_id, a, user_id)
    eff = payload.effective_date or _default_start(a)
    role = payload.role or old["role"]
    _end(db, old, eff, payload.reason)
    new_id = _insert(db, a, payload.new_auditor_id, role, eff, user_id)
    log_team(db, "replace", user_id, assignment_id=assignment_id, auditor_id=payload.new_auditor_id,
             role=role, reason=f"{payload.reason} (replaces {old['auditor_id']})")
    return get_member(db, assignment_id, new_id)


def change_role(db: Session, assignment_id: UUID, member_id: UUID, payload: MemberRoleChange, user_id: UUID) -> dict:
    a = _open_assignment(db, assignment_id)
    old = _active_member(db, assignment_id, member_id)
    if payload.role == old["role"]:
        raise HTTPException(status_code=400, detail="Member already has this role")
    eff = payload.effective_date or _default_start(a)
    _end(db, old, eff, f"role change to {payload.role}")
    new_id = _insert(db, a, old["auditor_id"], payload.role, eff, user_id)
    log_team(db, "role_change", user_id, assignment_id=assignment_id, auditor_id=old["auditor_id"],
             role=payload.role, reason=f"{payload.reason} (from {old['role']})")
    return get_member(db, assignment_id, new_id)