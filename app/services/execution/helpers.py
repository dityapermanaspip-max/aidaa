from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.assignments import get_assignment
from app.services.approval import create_task

_PREP = ("draft", "issued", "ongoing")
_WORKABLE = ("issued", "ongoing")
_REK_EDIT = ("draft", "approved", "responded", "open")


def _now():
    return datetime.now(timezone.utc)


def _row(db: Session, sql: str, params: dict, msg: str) -> dict:
    r = db.execute(text(sql), params).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail=msg)
    return dict(r._mapping)


def _patch(db: Session, table: str, pk: str, rid, cols: dict, user_id: UUID):
    # table, pk and column names are internal constants or Pydantic field names
    sets = [f"{k} = :{k}" for k in cols] + ["updated_at = now()", "updated_by = CAST(:_u AS uuid)"]
    db.execute(text(f"UPDATE {table} SET {', '.join(sets)} WHERE {pk} = CAST(:_id AS uuid)"),
               {**cols, "_u": str(user_id), "_id": str(rid)})


def _assignment_open(db: Session, assignment_id: UUID, allowed) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in allowed:
        raise HTTPException(status_code=409, detail=f"Assignment must be {' or '.join(allowed)} for this action")
    return a


def _my_auditor_id(db: Session, user_id: UUID):
    r = db.execute(text("SELECT auditor_id FROM aidaa_core.auditor WHERE user_id = CAST(:u AS uuid)"),
                   {"u": str(user_id)}).fetchone()
    return r.auditor_id if r else None


def _user_of_auditor(db: Session, auditor_id):
    if not auditor_id:
        return None
    r = db.execute(text("SELECT user_id FROM aidaa_core.auditor WHERE auditor_id = CAST(:a AS uuid)"),
                   {"a": str(auditor_id)}).fetchone()
    return r.user_id if r else None


def _assert_member(db: Session, assignment_id: UUID, auditor_id: UUID):
    ok = db.execute(text("""
        SELECT 1 FROM aidaa_core.assignment_member
        WHERE assignment_id = CAST(:a AS uuid) AND auditor_id = CAST(:u AS uuid) AND end_date IS NULL
    """), {"a": str(assignment_id), "u": str(auditor_id)}).fetchone()
    if not ok:
        raise HTTPException(status_code=400, detail="Auditor is not an active team member")


def _has_pending(db: Session, record_type: str, rid) -> bool:
    return db.execute(text("""
        SELECT 1 FROM aidaa_core.approval_task
        WHERE record_type = :rt AND record_id = CAST(:id AS uuid) AND status = 'pending' LIMIT 1
    """), {"rt": record_type, "id": str(rid)}).fetchone() is not None


def _reviewer(db: Session, assignment_id: UUID, role: str, exclude: list) -> UUID:
    """Active team member with this role who is not the preparer or the requester."""
    rows = db.execute(text("""
        SELECT a.user_id FROM aidaa_core.assignment_member m
        JOIN aidaa_core.auditor a ON a.auditor_id = m.auditor_id
        WHERE m.assignment_id = CAST(:a AS uuid) AND m.role = :r AND m.end_date IS NULL
        ORDER BY m.start_date, m.created_at
    """), {"a": str(assignment_id), "r": role}).fetchall()
    if not rows:
        raise HTTPException(status_code=409, detail=f"Assignment has no active {role} to review this")
    skip = {str(x) for x in exclude if x}
    for r in rows:
        if str(r.user_id) not in skip:
            return r.user_id
    raise HTTPException(status_code=409, detail=f"The {role} is also the preparer, a different reviewer is needed")


def _open_review(db: Session, record_type: str, record_id, assignment_id, step_no: int,
                 role: str, requester, preparers: list) -> dict:
    reviewer = _reviewer(db, assignment_id, role, [requester, *preparers])
    return create_task(db, record_type, record_id, step_no, requester, assigned_user_id=reviewer)