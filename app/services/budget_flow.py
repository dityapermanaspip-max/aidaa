"""Budget verification wiring for the seeded approval step record_type 'budget' ('finance_verify',
global_role AIDAA.FINANCE). Budget lines keep editing while issued; submitting creates a task whose
decision is only recorded (approved = a comment, rejected = a comment with the note, the team can
resubmit). The latest task doubles as the verification state - nothing is stored separately.
"""
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.approval import create_task, register_handler
from app.services.assignments import get_assignment
from app.services.execution.helpers import _has_pending
from app.services.logs import log_comment

_OPEN = ("issued", "ongoing")


def submit_budget_verification(db: Session, assignment_id: UUID, user_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in _OPEN:
        raise HTTPException(
            status_code=409,
            detail=f"Budget verification is for issued or ongoing assignments, this one is {a['status']}")
    if _has_pending(db, "budget", assignment_id):
        raise HTTPException(status_code=409, detail="A budget verification is already pending")
    return create_task(db, "budget", assignment_id, 1, user_id)


def get_budget_verification(db: Session, assignment_id) -> Optional[dict]:
    row = db.execute(text("""
        SELECT t.task_id, t.record_type, t.record_id, t.step_id, s.step_no, s.step_code,
               s.approver_kind, s.approver_role, t.assigned_user_id, t.requested_by, t.status,
               t.due_date, t.decided_by, t.decided_at, t.decision_note, t.created_at
        FROM aidaa_core.approval_task t
        JOIN aidaa_core.approval_step s ON s.step_id = t.step_id
        WHERE t.record_type = 'budget' AND t.record_id = CAST(:a AS uuid)
        ORDER BY t.created_at DESC
        LIMIT 1
    """), {"a": str(assignment_id)}).fetchone()
    return dict(row._mapping) if row else None


def _on_budget_task(db: Session, task: dict, user_id):
    if task["status"] == "approved":
        log_comment(db, "assignment", task["record_id"], "Budget verified by Finance", user_id)
    else:
        log_comment(db, "assignment", task["record_id"],
                    f"Budget verification {task['status']}: {task['decision_note'] or '-'}", user_id)


register_handler("budget", _on_budget_task)
