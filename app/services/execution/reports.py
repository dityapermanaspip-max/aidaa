from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.execution import ReportCreate, ReportUpdate
from app.services.assignments import get_assignment
from app.services.approval import create_task
from app.services.logs import log_status, log_comment
from app.services.execution.helpers import _WORKABLE, _row, _patch, _assignment_open, _open_review

_REP_COLS = ("report_id, assignment_id, version_no, opinion, summary, materiality_threshold_pct, "
             "total_open_materiality, report_url, source, status, created_by, created_at, updated_at")


def get_report(db: Session, report_id: UUID) -> dict:
    return _row(db, f"SELECT {_REP_COLS} FROM aidaa_core.audit_report WHERE report_id = CAST(:id AS uuid)",
                {"id": str(report_id)}, "Report not found")


def list_reports(db: Session, assignment_id: UUID, pic: bool = False) -> list[dict]:
    get_assignment(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {_REP_COLS} FROM aidaa_core.audit_report
        WHERE assignment_id = CAST(:a AS uuid) AND (:pic = FALSE OR status IN ('approved', 'final'))
        ORDER BY version_no DESC
    """), {"a": str(assignment_id), "pic": pic}).fetchall()
    return [dict(r._mapping) for r in rows]


def _open_materiality(db: Session, assignment_id):
    return db.execute(text("""
        SELECT COALESCE(SUM(f.materiality_amount), 0) AS t FROM aidaa_core.finding f
        WHERE f.assignment_id = CAST(:a AS uuid)
          AND EXISTS (SELECT 1 FROM aidaa_core.rekomend r WHERE r.finding_id = f.finding_id AND r.status <> 'closed')
    """), {"a": str(assignment_id)}).fetchone().t


def _assert_no_overdue(db: Session, assignment_id):
    n = db.execute(text("""
        SELECT count(*) AS n FROM aidaa_core.finding
        WHERE assignment_id = CAST(:a AS uuid) AND status = 'communicated' AND response_due_date < CURRENT_DATE
    """), {"a": str(assignment_id)}).fetchone().n
    if n:
        raise HTTPException(status_code=409,
                            detail=f"{n} communicated finding(s) are past due with no response, extend the due date or wait for the response")


def get_report_detail(db: Session, report_id: UUID, pic: bool = False) -> dict:
    r = get_report(db, report_id)
    if pic and r["status"] not in ("approved", "final"):
        raise HTTPException(status_code=404, detail="Report not found")
    aid = str(r["assignment_id"])
    counts = db.execute(text("""
        WITH pr AS (
            SELECT p.is_skipped, p.status,
                   (SELECT t.status FROM aidaa_core.approval_task t
                    JOIN aidaa_core.approval_step s ON s.step_id = t.step_id
                    WHERE t.record_type = 'procedure' AND t.record_id = p.procedure_id AND s.step_no = 2
                    ORDER BY t.created_at DESC LIMIT 1) AS last_step2
            FROM aidaa_core.exe_procedure p JOIN aidaa_core.pka k ON k.pka_id = p.pka_id
            WHERE k.assignment_id = CAST(:a AS uuid) AND NOT k.is_skipped
        )
        SELECT count(*) FILTER (WHERE NOT is_skipped) AS procedures_total,
               count(*) FILTER (WHERE status = 'supervisor_reviewed') AS fully_reviewed,
               count(*) FILTER (WHERE status = 'leader_reviewed' AND last_step2 = 'skipped') AS supervisor_review_skipped,
               count(*) FILTER (WHERE is_skipped) AS procedures_skipped
        FROM pr
    """), {"a": aid}).fetchone()
    findings = db.execute(text("""
        SELECT f.finding_no, f.title, f.status, f.materiality_amount, f.response_due_date,
               COALESCE(f.status = 'communicated' AND f.response_due_date < CURRENT_DATE, FALSE) AS no_response,
               (SELECT x.message FROM aidaa_core.finding_response x WHERE x.finding_id = f.finding_id
                AND x.direction = 'auditor_communication' ORDER BY x.round_no DESC LIMIT 1) AS auditor_position,
               (SELECT x.stance FROM aidaa_core.finding_response x WHERE x.finding_id = f.finding_id
                AND x.direction = 'auditee_response' ORDER BY x.round_no DESC LIMIT 1) AS auditee_stance,
               (SELECT x.message FROM aidaa_core.finding_response x WHERE x.finding_id = f.finding_id
                AND x.direction = 'auditee_response' ORDER BY x.round_no DESC LIMIT 1) AS auditee_position
        FROM aidaa_core.finding f
        WHERE f.assignment_id = CAST(:a AS uuid) AND f.status NOT IN ('draft', 'leader_reviewed')
        ORDER BY f.finding_no
    """), {"a": aid}).fetchall()
    r["review_counts"] = {k: int(v) for k, v in counts._mapping.items()}
    r["findings"] = [dict(x._mapping) for x in findings]
    r["open_materiality_now"] = _open_materiality(db, aid)
    return r


def create_report(db: Session, assignment_id: UUID, payload: ReportCreate, user_id: UUID) -> dict:
    _assignment_open(db, assignment_id, _WORKABLE)
    open_one = db.execute(text("""
        SELECT 1 FROM aidaa_core.audit_report WHERE assignment_id = CAST(:a AS uuid) AND status <> 'final' LIMIT 1
    """), {"a": str(assignment_id)}).fetchone()
    if open_one:
        raise HTTPException(status_code=409, detail="This assignment already has a report in progress")
    row = db.execute(text("""
        INSERT INTO aidaa_core.audit_report
            (assignment_id, version_no, opinion, summary, materiality_threshold_pct, report_url,
             created_by, updated_by)
        VALUES (CAST(:a AS uuid),
                (SELECT COALESCE(MAX(version_no), 0) + 1 FROM aidaa_core.audit_report
                 WHERE assignment_id = CAST(:a AS uuid)),
                :o, :s, :pct, :url, CAST(:u AS uuid), CAST(:u AS uuid))
        RETURNING report_id
    """), {"a": str(assignment_id), "o": payload.opinion, "s": payload.summary,
           "pct": payload.materiality_threshold_pct, "url": payload.report_url,
           "u": str(user_id)}).fetchone()
    log_status(db, "report", row.report_id, None, "draft", user_id)
    return get_report(db, row.report_id)


def update_report(db: Session, report_id: UUID, payload: ReportUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    r = get_report(db, report_id)
    if r["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only a draft report can be edited")
    _patch(db, "aidaa_core.audit_report", "report_id", report_id, data, user_id)
    return get_report(db, report_id)


def submit_report(db: Session, report_id: UUID, user_id: UUID) -> dict:
    r = get_report(db, report_id)
    if r["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only a draft report can be submitted")
    _assignment_open(db, r["assignment_id"], _WORKABLE)
    _assert_no_overdue(db, r["assignment_id"])
    _open_review(db, "report", report_id, r["assignment_id"], 1, "supervisor", user_id, [r["created_by"]])
    _patch(db, "aidaa_core.audit_report", "report_id", report_id,
           {"status": "review", "total_open_materiality": _open_materiality(db, r["assignment_id"])}, user_id)
    log_status(db, "report", report_id, "draft", "review", user_id)
    return get_report(db, report_id)


def finalize_report(db: Session, report_id: UUID, user_id: UUID) -> dict:
    r = get_report(db, report_id)
    if r["status"] != "approved":
        raise HTTPException(status_code=409, detail="Only a Head-approved report can be finalized")
    a = _assignment_open(db, r["assignment_id"], _WORKABLE)
    _assert_no_overdue(db, r["assignment_id"])
    _patch(db, "aidaa_core.audit_report", "report_id", report_id,
           {"status": "final", "total_open_materiality": _open_materiality(db, r["assignment_id"])}, user_id)
    log_status(db, "report", report_id, "approved", "final", user_id)
    _patch(db, "aidaa_core.assignment", "assignment_id", a["assignment_id"], {"status": "finished"}, user_id)
    log_status(db, "assignment", a["assignment_id"], a["status"], "finished", user_id)
    db.execute(text("""
        INSERT INTO aidaa_core.expertise
            (auditor_id, expertise_type, title, issued_date, type_id, points, source,
             verification_status, verified_at, created_by, updated_by)
        SELECT d.auditor_id, 'internal_experience', 'Audit ' || CAST(:no AS text), CURRENT_DATE,
               CAST(:t AS uuid), d.days, 'system_credit', 'verified', now(),
               CAST(:u AS uuid), CAST(:u AS uuid)
        FROM (SELECT m.auditor_id,
                     SUM(GREATEST(LEAST(COALESCE(m.end_date, CAST(:e AS date)), CAST(:e AS date)) - m.start_date + 1, 0)) AS days
              FROM aidaa_core.assignment_member m
              WHERE m.assignment_id = CAST(:a AS uuid) GROUP BY m.auditor_id) d
        WHERE d.days > 0
    """), {"no": a["assignment_no"], "t": str(a["type_id"]), "u": str(user_id),
           "e": a["end_date"], "a": str(a["assignment_id"])})
    return get_report(db, report_id)


def _on_report_task(db: Session, task: dict, user_id: UUID):
    r = get_report(db, task["record_id"])
    if task.get("decision_note"):
        log_comment(db, "report", r["report_id"], task["decision_note"], user_id)
    if r["status"] != "review":
        return
    if task["status"] != "approved":
        _patch(db, "aidaa_core.audit_report", "report_id", r["report_id"], {"status": "draft"}, user_id)
        log_status(db, "report", r["report_id"], "review", "draft", user_id)
    elif task["step_no"] == 1:  # supervisor reviewed, now Head (global role, no assigned user)
        create_task(db, "report", r["report_id"], 2, task["requested_by"])
    else:
        _patch(db, "aidaa_core.audit_report", "report_id", r["report_id"], {"status": "approved"}, user_id)
        log_status(db, "report", r["report_id"], "review", "approved", user_id)