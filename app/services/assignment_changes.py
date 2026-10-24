"""Assignment change requests: draft-only PATCH is joined by a staged, supervisor-approved edit.

The seeded approval step record_type 'assignment_change' step 1 'supervisor_approve'
(assignment_role supervisor) is the authority: the leader stages the change here, the supervisor
decides it in the generic approval inbox, and only an approved task applies the staged payload
to the assignment (dates, notes, document links, extra units with the same guards as drafts).
Rows rejected or returned mark the request rejected - the requester files a new one if needed.
"""
import json
from datetime import date
from typing import Optional
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.assignment import AssignmentChangeIn
from app.services.approval import create_task, register_handler
from app.services.assignments import get_assignment, _apply_assignment_edit
from app.services.logs import log_comment
from app.services.execution.helpers import _reviewer, _row

_OPEN = ("issued", "ongoing")  # a change request is a post-issue instrument

_CHANGE_SQL = """
    SELECT c.change_id, c.assignment_id, c.requested_by, c.reason, c.payload, c.status,
           c.task_id, c.created_at,
           s.step_code, t.due_date, t.decided_by, t.decided_at, t.decision_note
    FROM aidaa_core.assignment_change c
    LEFT JOIN aidaa_core.approval_task t ON t.task_id = c.task_id
    LEFT JOIN aidaa_core.approval_step s ON s.step_id = t.step_id
"""


def get_change(db: Session, change_id: UUID) -> dict:
    return _row(db, f"{_CHANGE_SQL} WHERE c.change_id = CAST(:id AS uuid)",
                {"id": str(change_id)}, "Change request not found")


def list_changes(db: Session, assignment_id: UUID) -> list[dict]:
    rows = db.execute(text(f"""
        {_CHANGE_SQL} WHERE c.assignment_id = CAST(:a AS uuid)
        ORDER BY c.created_at DESC
    """), {"a": str(assignment_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def _assert_open(a: dict):
    if a["status"] not in _OPEN:
        raise HTTPException(status_code=409,
                            detail=f"Change requests are for issued or ongoing assignments, this one is {a['status']}")


def create_change(db: Session, assignment_id: UUID, payload: AssignmentChangeIn,
                  user_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    _assert_open(a)
    pending = db.execute(text("""
        SELECT 1 FROM aidaa_core.assignment_change
        WHERE assignment_id = CAST(:a AS uuid) AND status = 'pending' LIMIT 1
    """), {"a": str(assignment_id)}).fetchone()
    if pending:
        raise HTTPException(status_code=409, detail="This assignment already has a pending change request")

    data = payload.model_dump(exclude_unset=True)
    reason = data.pop("reason")
    due: Optional[date] = data.pop("due_date", None)
    if not data:
        raise HTTPException(status_code=400, detail="The change request carries no actual change")

    # Fail fast on the reviewer before staging anything: the requester cannot decide their own
    # request, so an active supervisor other than the requester must exist.
    change_id = uuid4()
    reviewer = _reviewer(db, assignment_id, "supervisor", [user_id])
    db.execute(text("""
        INSERT INTO aidaa_core.assignment_change
            (change_id, assignment_id, requested_by, reason, payload, status)
        VALUES (CAST(:id AS uuid), CAST(:a AS uuid), CAST(:u AS uuid), :reason,
                CAST(:payload AS jsonb), 'pending')
    """), {"id": str(change_id), "a": str(assignment_id), "u": str(user_id),
           "reason": reason, "payload": json.dumps(data)}).fetchone()
    task = create_task(db, "assignment_change", change_id, 1, user_id, due_date=due,
                       assigned_user_id=reviewer)
    db.execute(text("""
        UPDATE aidaa_core.assignment_change SET task_id = CAST(:t AS uuid)
        WHERE change_id = CAST(:id AS uuid)
    """), {"t": task["task_id"], "id": str(change_id)})
    return get_change(db, change_id)


def cancel_change(db: Session, change_id: UUID, user_id: UUID) -> dict:
    change = get_change(db, change_id)
    if change["status"] != "pending":
        raise HTTPException(status_code=409, detail="Only a pending change request can be cancelled")
    if str(change["requested_by"]) != str(user_id):
        raise HTTPException(status_code=403, detail="Only the requester can cancel this change request")
    db.execute(text("""
        UPDATE aidaa_core.approval_task SET status = 'cancelled'
        WHERE task_id = CAST(:t AS uuid) AND status = 'pending'
    """), {"t": change["task_id"]})
    db.execute(text("""
        UPDATE aidaa_core.assignment_change SET status = 'cancelled'
        WHERE change_id = CAST(:id AS uuid)
    """), {"id": str(change_id)})
    log_comment(db, "assignment", change["assignment_id"],
                f"Change request cancelled by the requester ({change['reason']})", user_id)
    return get_change(db, change_id)


def _on_assignment_change_task(db: Session, task: dict, user_id: UUID):
    change = get_change(db, task["record_id"])
    if task["status"] != "approved":
        db.execute(text("""
            UPDATE aidaa_core.assignment_change SET status = 'rejected'
            WHERE change_id = CAST(:id AS uuid)
        """), {"id": str(change["change_id"])})
        log_comment(db, "assignment", change["assignment_id"],
                    f"Change request not approved ({task['status']}): {task['decision_note'] or '-'}",
                    user_id)
        return
    data = dict(change["payload"])
    extras = data.pop("extra_unit_ids", None)
    current = get_assignment(db, change["assignment_id"])
    _assert_open(current)
    _apply_assignment_edit(db, current, data, extras, user_id)
    db.execute(text("""
        UPDATE aidaa_core.assignment_change SET status = 'approved'
        WHERE change_id = CAST(:id AS uuid)
    """), {"id": str(change["change_id"])})
    log_comment(db, "assignment", change["assignment_id"],
                f"Change request applied ({change['reason']})", user_id)


register_handler("assignment_change", _on_assignment_change_task)
