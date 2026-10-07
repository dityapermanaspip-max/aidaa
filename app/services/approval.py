from datetime import date
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.aidaa import TaskDecision
from app.services.logs import log_approval

_TASK_SQL = """
    SELECT t.task_id, t.record_type, t.record_id, t.step_id, s.step_no, s.step_code,
           s.approver_kind, s.approver_role, t.assigned_user_id, t.requested_by, t.status,
           t.due_date, t.decided_by, t.decided_at, t.decision_note, t.created_at
    FROM aidaa_core.approval_task t
    JOIN aidaa_core.approval_step s ON s.step_id = t.step_id
"""

_HOLDS_ROLE = """
    EXISTS (SELECT 1 FROM iam.active_user_roles m
            JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
            WHERE m.user_id = CAST(:u AS uuid) AND r.role_code = s.approver_role)
"""

_HANDLERS = {}


def register_handler(record_type: str, fn):
    """Domain services register a function(db, task, user_id) run after each decision."""
    _HANDLERS[record_type] = fn
    
    
def get_step(db: Session, record_type: str, step_no: int) -> dict:
    row = db.execute(text("""
        SELECT step_id, record_type, step_no, step_code, approver_kind, approver_role
        FROM aidaa_core.approval_step
        WHERE record_type = :rt AND step_no = :n AND is_active = TRUE
    """), {"rt": record_type, "n": step_no}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No approval step {step_no} for '{record_type}'")
    return dict(row._mapping)


def get_task(db: Session, task_id: UUID) -> dict:
    row = db.execute(text(f"{_TASK_SQL} WHERE t.task_id = CAST(:id AS uuid)"),
                     {"id": str(task_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row._mapping)


def create_task(db: Session, record_type: str, record_id: UUID, step_no: int, requested_by: UUID,
                due_date: Optional[date] = None, assigned_user_id: Optional[UUID] = None) -> dict:
    """Called by domain services (plan, budget, pka, report), not by a router."""
    step = get_step(db, record_type, step_no)
    dup = db.execute(text("""
        SELECT 1 FROM aidaa_core.approval_task
        WHERE record_type = :rt AND record_id = CAST(:rid AS uuid)
          AND step_id = CAST(:sid AS uuid) AND status = 'pending'
    """), {"rt": record_type, "rid": str(record_id), "sid": str(step["step_id"])}).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail="This step already has a pending task")
    row = db.execute(text("""
        INSERT INTO aidaa_core.approval_task
            (record_type, record_id, step_id, assigned_user_id, requested_by, due_date)
        VALUES (:rt, CAST(:rid AS uuid), CAST(:sid AS uuid), CAST(:au AS uuid),
                CAST(:rb AS uuid), :due)
        RETURNING task_id
    """), {"rt": record_type, "rid": str(record_id), "sid": str(step["step_id"]),
           "au": str(assigned_user_id) if assigned_user_id else None,
           "rb": str(requested_by), "due": due_date}).fetchone()
    log_approval(db, record_type, record_id, step["step_code"], "submitted", requested_by)
    return get_task(db, row.task_id)


def _assert_can_decide(db: Session, user_id: UUID, task: dict):
    if task["assigned_user_id"] is not None:
        if str(task["assigned_user_id"]) != str(user_id):
            raise HTTPException(status_code=403, detail="This task is assigned to someone else")
        return
    if task["approver_kind"] != "global_role":
        # assignment_role steps must be created with assigned_user_id resolved from assignment_member
        raise HTTPException(status_code=403, detail="Task has no assigned approver")
    held = db.execute(text("""
        SELECT 1 FROM iam.active_user_roles m
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        WHERE m.user_id = CAST(:u AS uuid) AND r.role_code = :rc LIMIT 1
    """), {"u": str(user_id), "rc": task["approver_role"]}).fetchone()
    if not held:
        raise HTTPException(status_code=403, detail=f"Role '{task['approver_role']}' required")


def decide_task(db: Session, task_id: UUID, user_id: UUID, payload: TaskDecision) -> dict:
    """Records the decision only. The domain service decides what happens next (next step, status)."""
    task = get_task(db, task_id)
    if task["status"] != "pending":
        raise HTTPException(status_code=409, detail="Task is already decided")
    if str(task["requested_by"]) == str(user_id):
        raise HTTPException(status_code=403, detail="You cannot decide your own request")
    if payload.decision != "approved" and not (payload.note or "").strip():
        raise HTTPException(status_code=400, detail="note is required when rejecting or returning")
    _assert_can_decide(db, user_id, task)

    db.execute(text("""
        UPDATE aidaa_core.approval_task
        SET status = :st, decided_by = CAST(:u AS uuid), decided_at = now(), decision_note = :note
        WHERE task_id = CAST(:id AS uuid) AND status = 'pending'
    """), {"st": payload.decision, "u": str(user_id), "note": payload.note, "id": str(task_id)})
    log_approval(db, task["record_type"], task["record_id"], task["step_code"],
                 payload.decision, user_id, payload.note)
    task = get_task(db, task_id)
    handler = _HANDLERS.get(task["record_type"])
    if handler:
        handler(db, task, user_id)
    return task


def list_my_tasks(db: Session, user_id: UUID, status: str = "pending") -> list[dict]:
    rows = db.execute(text(f"""
        {_TASK_SQL}
        WHERE t.status = :st
          AND t.requested_by <> CAST(:u AS uuid)
          AND (t.assigned_user_id = CAST(:u AS uuid)
               OR (t.assigned_user_id IS NULL AND s.approver_kind = 'global_role' AND {_HOLDS_ROLE}))
        ORDER BY t.created_at
    """), {"st": status, "u": str(user_id)}).fetchall()
    return [dict(r._mapping) for r in rows]