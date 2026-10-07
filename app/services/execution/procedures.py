from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.execution import ExeProcCreate, ExeProcUpdate, PaperCreate, PaperUpdate
from app.services.logs import log_status, log_comment, log_approval
from app.services.execution.helpers import (
    _PREP, _WORKABLE, _now, _row, _patch, _assignment_open, _my_auditor_id,
    _user_of_auditor, _open_review,
)
from app.services.execution.pka import get_pka

_PROC_SQL = """
    SELECT p.procedure_id, p.pka_id, p.library_procedure_id, p.step_no, p.procedure_text,
           p.is_skipped, p.skip_reason, p.executed_by, p.executed_at, p.conclusion, p.result,
           p.status, p.leader_reviewed_by, p.leader_reviewed_at, p.supervisor_reviewed_by,
           p.supervisor_reviewed_at, p.created_at, p.updated_at,
           k.assignment_id, k.status AS pka_status, k.is_skipped AS pka_is_skipped,
           k.assigned_auditor_id AS pka_assigned_auditor_id,
           COALESCE(p.status = 'leader_reviewed' AND (
               SELECT t.status FROM aidaa_core.approval_task t
               JOIN aidaa_core.approval_step s ON s.step_id = t.step_id
               WHERE t.record_type = 'procedure' AND t.record_id = p.procedure_id AND s.step_no = 2
               ORDER BY t.created_at DESC LIMIT 1) = 'skipped', FALSE) AS supervisor_review_skipped
    FROM aidaa_core.exe_procedure p JOIN aidaa_core.pka k ON k.pka_id = p.pka_id
"""


def get_procedure(db: Session, procedure_id: UUID) -> dict:
    return _row(db, f"{_PROC_SQL} WHERE p.procedure_id = CAST(:id AS uuid)",
                {"id": str(procedure_id)}, "Procedure not found")


def list_procedures(db: Session, pka_id: UUID) -> list[dict]:
    get_pka(db, pka_id)
    rows = db.execute(text(f"{_PROC_SQL} WHERE p.pka_id = CAST(:k AS uuid) ORDER BY p.step_no"),
                      {"k": str(pka_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def _proc_open(pr: dict):
    if pr["pka_is_skipped"] or pr["is_skipped"]:
        raise HTTPException(status_code=409, detail="Procedure or its PKA is skipped")
    if pr["status"] not in ("planned", "in_progress"):
        raise HTTPException(status_code=409, detail="Procedure is under review or reviewed and cannot be edited")


def create_procedure(db: Session, pka_id: UUID, payload: ExeProcCreate, user_id: UUID) -> dict:
    p = get_pka(db, pka_id)
    if p["is_skipped"] or p["status"] not in ("draft", "approved", "in_progress"):
        raise HTTPException(status_code=409, detail="Procedures cannot be added to this PKA now")
    _assignment_open(db, p["assignment_id"], _PREP)
    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.exe_procedure (pka_id, step_no, procedure_text, created_by, updated_by)
            VALUES (CAST(:k AS uuid),
                    COALESCE(CAST(:s AS int), (SELECT COALESCE(MAX(step_no), 0) + 1
                                               FROM aidaa_core.exe_procedure WHERE pka_id = CAST(:k AS uuid))),
                    :t, CAST(:u AS uuid), CAST(:u AS uuid))
            RETURNING procedure_id
        """), {"k": str(pka_id), "s": payload.step_no, "t": payload.procedure_text,
               "u": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="step_no already used in this PKA")
    return get_procedure(db, row.procedure_id)


def update_procedure(db: Session, procedure_id: UUID, payload: ExeProcUpdate, user_id: UUID, role: str) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    pr = get_procedure(db, procedure_id)
    _proc_open(pr)
    cols = dict(data)
    if "conclusion" in data or "result" in data:
        a = _assignment_open(db, pr["assignment_id"], _WORKABLE)
        if pr["pka_status"] not in ("approved", "in_progress"):
            raise HTTPException(status_code=409, detail="PKA must be approved before procedures are executed")
        me = _my_auditor_id(db, user_id)
        if pr["executed_by"]:
            if str(pr["executed_by"]) != str(me):
                raise HTTPException(status_code=403, detail="Only the auditor who started this procedure can continue it")
        else:
            assigned = pr["pka_assigned_auditor_id"]
            if assigned and str(assigned) != str(me) and role != "leader":
                raise HTTPException(status_code=403, detail="This PKA is assigned to another auditor")
            cols["executed_by"] = me
            cols["executed_at"] = _now()
        if pr["status"] == "planned":
            cols["status"] = "in_progress"
            if a["status"] == "issued":
                _patch(db, "aidaa_core.assignment", "assignment_id", a["assignment_id"], {"status": "ongoing"}, user_id)
                log_status(db, "assignment", a["assignment_id"], "issued", "ongoing", user_id)
            if pr["pka_status"] == "approved":
                _patch(db, "aidaa_core.pka", "pka_id", pr["pka_id"], {"status": "in_progress"}, user_id)
                log_status(db, "pka", pr["pka_id"], "approved", "in_progress", user_id)
    elif pr["pka_status"] not in ("draft", "approved", "in_progress"):
        raise HTTPException(status_code=409, detail="PKA is under review or done")
    _patch(db, "aidaa_core.exe_procedure", "procedure_id", procedure_id, cols, user_id)
    return get_procedure(db, procedure_id)


def set_procedure_skip(db: Session, procedure_id: UUID, skip: bool, reason: Optional[str], user_id: UUID) -> dict:
    pr = get_procedure(db, procedure_id)
    if pr["status"] not in ("planned", "in_progress") or pr["pka_is_skipped"]:
        raise HTTPException(status_code=409, detail="Procedure cannot be skipped or unskipped now")
    if skip:
        if pr["is_skipped"]:
            raise HTTPException(status_code=409, detail="Procedure is already skipped")
        if not (reason or "").strip():
            raise HTTPException(status_code=400, detail="reason is required to skip")
        _patch(db, "aidaa_core.exe_procedure", "procedure_id", procedure_id,
               {"is_skipped": True, "skip_reason": reason}, user_id)
        log_comment(db, "procedure", procedure_id, f"Skipped: {reason}", user_id)
    else:
        if not pr["is_skipped"]:
            raise HTTPException(status_code=409, detail="Procedure is not skipped")
        _patch(db, "aidaa_core.exe_procedure", "procedure_id", procedure_id,
               {"is_skipped": False, "skip_reason": None}, user_id)
        log_comment(db, "procedure", procedure_id, "Skip removed", user_id)
    return get_procedure(db, procedure_id)


def submit_procedure(db: Session, procedure_id: UUID, user_id: UUID) -> dict:
    pr = get_procedure(db, procedure_id)
    _proc_open(pr)
    if pr["status"] != "in_progress" or not pr["conclusion"] or not pr["result"]:
        raise HTTPException(status_code=400, detail="Execute the procedure (conclusion and result) before submitting")
    _assignment_open(db, pr["assignment_id"], _WORKABLE)
    if str(pr["executed_by"]) != str(_my_auditor_id(db, user_id)):
        raise HTTPException(status_code=403, detail="Only the executing auditor can submit this procedure")
    _open_review(db, "procedure", procedure_id, pr["assignment_id"], 1, "leader", user_id, [user_id])
    _patch(db, "aidaa_core.exe_procedure", "procedure_id", procedure_id, {"status": "done"}, user_id)
    log_status(db, "procedure", procedure_id, "in_progress", "done", user_id)
    return get_procedure(db, procedure_id)


def skip_review(db: Session, procedure_id: UUID, reason: str, user_id: UUID) -> dict:
    if not reason.strip():
        raise HTTPException(status_code=400, detail="reason is required to skip a review")
    pr = get_procedure(db, procedure_id)
    if pr["status"] != "leader_reviewed":
        raise HTTPException(status_code=409, detail="Only a leader-reviewed procedure can skip the supervisor review")
    t = db.execute(text("""
        SELECT t.task_id, t.assigned_user_id, t.requested_by, s.can_skip
        FROM aidaa_core.approval_task t JOIN aidaa_core.approval_step s ON s.step_id = t.step_id
        WHERE t.record_type = 'procedure' AND t.record_id = CAST(:id AS uuid)
          AND s.step_no = 2 AND t.status = 'pending'
    """), {"id": str(procedure_id)}).fetchone()
    if not t:
        raise HTTPException(status_code=409, detail="No pending supervisor review to skip")
    if not t.can_skip:
        raise HTTPException(status_code=409, detail="This review step cannot be skipped")
    if str(t.assigned_user_id) != str(user_id) or str(t.requested_by) == str(user_id):
        raise HTTPException(status_code=403, detail="Only the assigned supervisor can skip this review")
    db.execute(text("""
        UPDATE aidaa_core.approval_task
        SET status = 'skipped', decided_by = CAST(:u AS uuid), decided_at = now(), decision_note = :n
        WHERE task_id = CAST(:t AS uuid)
    """), {"u": str(user_id), "n": reason, "t": str(t.task_id)})
    log_approval(db, "procedure", procedure_id, "supervisor_review", "skipped", user_id, reason)
    log_comment(db, "procedure", procedure_id, f"Supervisor review skipped: {reason}", user_id)
    return get_procedure(db, procedure_id)


def reopen_review(db: Session, procedure_id: UUID, user_id: UUID) -> dict:
    pr = get_procedure(db, procedure_id)
    if pr["status"] != "leader_reviewed" or not pr["supervisor_review_skipped"]:
        raise HTTPException(status_code=409, detail="Only a procedure with a skipped supervisor review can be reopened")
    last = db.execute(text("""
        SELECT t.requested_by FROM aidaa_core.approval_task t
        JOIN aidaa_core.approval_step s ON s.step_id = t.step_id
        WHERE t.record_type = 'procedure' AND t.record_id = CAST(:id AS uuid)
          AND s.step_no = 2 AND t.status = 'skipped'
        ORDER BY t.created_at DESC LIMIT 1
    """), {"id": str(procedure_id)}).fetchone()
    _open_review(db, "procedure", procedure_id, pr["assignment_id"], 2, "supervisor",
                 last.requested_by, [_user_of_auditor(db, pr["executed_by"])])
    log_comment(db, "procedure", procedure_id, "Skipped supervisor review reopened", user_id)
    return get_procedure(db, procedure_id)


def _on_procedure_task(db: Session, task: dict, user_id: UUID):
    pr = get_procedure(db, task["record_id"])
    pid = pr["procedure_id"]
    if task.get("decision_note"):
        log_comment(db, "procedure", pid, task["decision_note"], user_id)
    expected = "done" if task["step_no"] == 1 else "leader_reviewed"
    if pr["status"] != expected:
        return
    if task["status"] != "approved":  # back to the preparer
        _patch(db, "aidaa_core.exe_procedure", "procedure_id", pid, {"status": "in_progress"}, user_id)
        log_status(db, "procedure", pid, expected, "in_progress", user_id)
        return
    if task["step_no"] == 1:
        _patch(db, "aidaa_core.exe_procedure", "procedure_id", pid,
               {"status": "leader_reviewed", "leader_reviewed_by": user_id, "leader_reviewed_at": _now()}, user_id)
        log_status(db, "procedure", pid, "done", "leader_reviewed", user_id)
        _open_review(db, "procedure", pid, pr["assignment_id"], 2, "supervisor",
                     task["requested_by"], [_user_of_auditor(db, pr["executed_by"])])
    else:
        _patch(db, "aidaa_core.exe_procedure", "procedure_id", pid,
               {"status": "supervisor_reviewed", "supervisor_reviewed_by": user_id,
                "supervisor_reviewed_at": _now()}, user_id)
        log_status(db, "procedure", pid, "leader_reviewed", "supervisor_reviewed", user_id)


# --- working papers (reviewed through their procedure) ---

_WP_SQL = """
    SELECT w.paper_id, w.procedure_id, w.title, w.file_url, w.file_name, w.notes, w.uploaded_by,
           w.uploaded_at, w.updated_at, k.assignment_id
    FROM aidaa_core.working_paper w
    JOIN aidaa_core.exe_procedure p ON p.procedure_id = w.procedure_id
    JOIN aidaa_core.pka k ON k.pka_id = p.pka_id
"""


def get_paper(db: Session, paper_id: UUID) -> dict:
    return _row(db, f"{_WP_SQL} WHERE w.paper_id = CAST(:id AS uuid)", {"id": str(paper_id)}, "Working paper not found")


def list_papers(db: Session, procedure_id: UUID) -> list[dict]:
    get_procedure(db, procedure_id)
    rows = db.execute(text(f"{_WP_SQL} WHERE w.procedure_id = CAST(:p AS uuid) ORDER BY w.uploaded_at"),
                      {"p": str(procedure_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_paper(db: Session, procedure_id: UUID, payload: PaperCreate, user_id: UUID) -> dict:
    pr = get_procedure(db, procedure_id)
    _proc_open(pr)
    _assignment_open(db, pr["assignment_id"], _WORKABLE)
    row = db.execute(text("""
        INSERT INTO aidaa_core.working_paper
            (procedure_id, title, file_url, file_name, notes, uploaded_by, updated_by)
        VALUES (CAST(:p AS uuid), :t, :url, :fn, :n, CAST(:u AS uuid), CAST(:u AS uuid))
        RETURNING paper_id
    """), {"p": str(procedure_id), "t": payload.title, "url": payload.file_url,
           "fn": payload.file_name, "n": payload.notes, "u": str(user_id)}).fetchone()
    return get_paper(db, row.paper_id)


def update_paper(db: Session, paper_id: UUID, payload: PaperUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    w = get_paper(db, paper_id)
    _proc_open(get_procedure(db, w["procedure_id"]))
    _patch(db, "aidaa_core.working_paper", "paper_id", paper_id, data, user_id)
    return get_paper(db, paper_id)