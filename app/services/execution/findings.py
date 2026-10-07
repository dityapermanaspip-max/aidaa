from datetime import date
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.execution import FindingCreate, FindingUpdate, CommunicateIn, ResponseCreate
from app.services.assignments import get_assignment
from app.services.logs import log_status, log_edit, log_comment
from app.services.execution.helpers import (
    _WORKABLE, _now, _row, _patch, _assignment_open, _has_pending, _open_review,
)

_FIND_SQL = """
    SELECT f.finding_id, f.assignment_id, f.procedure_id, f.finding_no, f.title, f.description,
           f.criteria, f.materiality_amount, f.communicated_at, f.response_due_date, f.status,
           f.created_by, f.created_at, f.updated_at,
           COALESCE(f.status = 'communicated' AND f.response_due_date < CURRENT_DATE, FALSE) AS no_response
    FROM aidaa_core.finding f
"""


def get_finding(db: Session, finding_id: UUID) -> dict:
    return _row(db, f"{_FIND_SQL} WHERE f.finding_id = CAST(:id AS uuid)", {"id": str(finding_id)}, "Finding not found")


def list_findings(db: Session, assignment_id: UUID, pic: bool = False) -> list[dict]:
    get_assignment(db, assignment_id)
    rows = db.execute(text(f"""
        {_FIND_SQL}
        WHERE f.assignment_id = CAST(:a AS uuid)
          AND (:pic = FALSE OR f.status IN ('communicated', 'responded', 'open', 'closed'))
        ORDER BY f.finding_no
    """), {"a": str(assignment_id), "pic": pic}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_finding(db: Session, assignment_id: UUID, payload: FindingCreate, user_id: UUID) -> dict:
    _assignment_open(db, assignment_id, _WORKABLE)
    if payload.procedure_id:
        ok = db.execute(text("""
            SELECT 1 FROM aidaa_core.exe_procedure p JOIN aidaa_core.pka k ON k.pka_id = p.pka_id
            WHERE p.procedure_id = CAST(:p AS uuid) AND k.assignment_id = CAST(:a AS uuid)
        """), {"p": str(payload.procedure_id), "a": str(assignment_id)}).fetchone()
        if not ok:
            raise HTTPException(status_code=400, detail="Procedure does not belong to this assignment")
    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.finding
                (assignment_id, procedure_id, finding_no, title, description, criteria,
                 materiality_amount, created_by, updated_by)
            VALUES (CAST(:a AS uuid), CAST(:p AS uuid),
                    'F-' || lpad(CAST((SELECT COALESCE(MAX(CAST(NULLIF(regexp_replace(finding_no, '[^0-9]', '', 'g'), '') AS int)), 0) + 1
                                       FROM aidaa_core.finding WHERE assignment_id = CAST(:a AS uuid)) AS text), 3, '0'),
                    :t, :d, :c, :m, CAST(:u AS uuid), CAST(:u AS uuid))
            RETURNING finding_id
        """), {"a": str(assignment_id), "p": str(payload.procedure_id) if payload.procedure_id else None,
               "t": payload.title, "d": payload.description, "c": payload.criteria,
               "m": payload.materiality_amount, "u": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Finding number clash, please retry")
    log_status(db, "finding", row.finding_id, None, "draft", user_id)
    return get_finding(db, row.finding_id)


def update_finding(db: Session, finding_id: UUID, payload: FindingUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    f = get_finding(db, finding_id)
    if f["status"] != "draft" or _has_pending(db, "finding", finding_id):
        raise HTTPException(status_code=409, detail="Only a draft finding that is not under review can be edited")
    _patch(db, "aidaa_core.finding", "finding_id", finding_id, data, user_id)
    return get_finding(db, finding_id)


def submit_finding(db: Session, finding_id: UUID, user_id: UUID) -> dict:
    f = get_finding(db, finding_id)
    if f["status"] != "draft" or _has_pending(db, "finding", finding_id):
        raise HTTPException(status_code=409, detail="Only a draft finding that is not under review can be submitted")
    _assignment_open(db, f["assignment_id"], _WORKABLE)
    _open_review(db, "finding", finding_id, f["assignment_id"], 1, "leader", user_id, [f["created_by"]])
    return get_finding(db, finding_id)


def _on_finding_task(db: Session, task: dict, user_id: UUID):
    f = get_finding(db, task["record_id"])
    fid = f["finding_id"]
    if task.get("decision_note"):
        log_comment(db, "finding", fid, task["decision_note"], user_id)
    expected = "draft" if task["step_no"] == 1 else "leader_reviewed"
    if f["status"] != expected:
        return
    if task["status"] != "approved":
        if expected != "draft":
            _patch(db, "aidaa_core.finding", "finding_id", fid, {"status": "draft"}, user_id)
            log_status(db, "finding", fid, expected, "draft", user_id)
        return
    if task["step_no"] == 1:
        _patch(db, "aidaa_core.finding", "finding_id", fid, {"status": "leader_reviewed"}, user_id)
        log_status(db, "finding", fid, "draft", "leader_reviewed", user_id)
        _open_review(db, "finding", fid, f["assignment_id"], 2, "supervisor", task["requested_by"], [f["created_by"]])
    else:
        _patch(db, "aidaa_core.finding", "finding_id", fid, {"status": "approved"}, user_id)
        log_status(db, "finding", fid, "leader_reviewed", "approved", user_id)


def _next_round(db: Session, finding_id: UUID) -> int:
    return db.execute(text("""
        SELECT COALESCE(MAX(round_no), 0) + 1 AS n FROM aidaa_core.finding_response
        WHERE finding_id = CAST(:f AS uuid)
    """), {"f": str(finding_id)}).fetchone().n


def communicate_finding(db: Session, finding_id: UUID, payload: CommunicateIn, user_id: UUID) -> dict:
    f = get_finding(db, finding_id)
    if f["status"] != "approved":
        raise HTTPException(status_code=409, detail="Only an approved finding can be communicated")
    _assignment_open(db, f["assignment_id"], _WORKABLE)
    if payload.response_due_date <= date.today():
        raise HTTPException(status_code=400, detail="response_due_date must be in the future")
    _patch(db, "aidaa_core.finding", "finding_id", finding_id,
           {"status": "communicated", "communicated_at": _now(),
            "response_due_date": payload.response_due_date}, user_id)
    db.execute(text("""
        INSERT INTO aidaa_core.finding_response (finding_id, round_no, direction, message, responded_by)
        VALUES (CAST(:f AS uuid), :r, 'auditor_communication', :m, CAST(:u AS uuid))
    """), {"f": str(finding_id), "r": _next_round(db, finding_id), "m": payload.message, "u": str(user_id)})
    log_status(db, "finding", finding_id, "approved", "communicated", user_id)
    return get_finding(db, finding_id)


def extend_due(db: Session, finding_id: UUID, new_due: date, reason: str, user_id: UUID) -> dict:
    f = get_finding(db, finding_id)
    if f["status"] != "communicated":
        raise HTTPException(status_code=409, detail="Only a communicated finding without a response can be extended")
    if new_due <= f["response_due_date"]:
        raise HTTPException(status_code=400, detail="new_due_date must be later than the current due date")
    _patch(db, "aidaa_core.finding", "finding_id", finding_id, {"response_due_date": new_due}, user_id)
    log_edit(db, "finding", finding_id, "response_due_date", f["response_due_date"], new_due, user_id, reason)
    return get_finding(db, finding_id)


def respond_finding(db: Session, finding_id: UUID, payload: ResponseCreate, user_id: UUID) -> dict:
    f = get_finding(db, finding_id)
    if f["status"] != "communicated":
        raise HTTPException(status_code=409, detail="This finding is not waiting for a response")
    if payload.stance in ("agree", "partially_agree") and not (payload.action_plan and payload.target_date):
        raise HTTPException(status_code=400, detail="action_plan and target_date are required when you agree")
    if payload.stance in ("disagree", "partially_agree") and not (payload.message or "").strip():
        raise HTTPException(status_code=400, detail="message (your reasoning) is required when you disagree")
    if payload.target_date and payload.target_date < date.today():
        raise HTTPException(status_code=400, detail="target_date cannot be in the past")
    db.execute(text("""
        INSERT INTO aidaa_core.finding_response
            (finding_id, round_no, direction, stance, message, action_plan, target_date,
             evidence_url, responded_by)
        VALUES (CAST(:f AS uuid), :r, 'auditee_response', :s, :m, :a, :t, :e, CAST(:u AS uuid))
    """), {"f": str(finding_id), "r": _next_round(db, finding_id), "s": payload.stance,
           "m": payload.message, "a": payload.action_plan, "t": payload.target_date,
           "e": payload.evidence_url, "u": str(user_id)})
    _patch(db, "aidaa_core.finding", "finding_id", finding_id, {"status": "responded"}, user_id)
    log_status(db, "finding", finding_id, "communicated", "responded", user_id)
    return list_responses(db, finding_id)[-1]


def resolve_finding(db: Session, finding_id: UUID, note: str, user_id: UUID) -> dict:
    f = get_finding(db, finding_id)
    if f["status"] != "responded":
        raise HTTPException(status_code=409, detail="Only a responded finding can be resolved")
    _patch(db, "aidaa_core.finding", "finding_id", finding_id, {"status": "open"}, user_id)
    log_comment(db, "finding", finding_id, f"Supervisor decision: {note}", user_id)
    log_status(db, "finding", finding_id, "responded", "open", user_id)
    return get_finding(db, finding_id)


def list_responses(db: Session, finding_id: UUID) -> list[dict]:
    get_finding(db, finding_id)
    rows = db.execute(text("""
        SELECT response_id, finding_id, round_no, direction, stance, message, action_plan,
               target_date, evidence_url, responded_by, responded_at
        FROM aidaa_core.finding_response WHERE finding_id = CAST(:f AS uuid) ORDER BY round_no
    """), {"f": str(finding_id)}).fetchall()
    return [dict(r._mapping) for r in rows]