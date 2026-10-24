"""Kuesioner (batch 07): questionnaire lifecycle and reads.

ONE questionnaire per PKA procedure (a UNIQUE column enforces it), issued by the LEADER in a
single batch that refuses (422) while any flagged procedure still misses a questionnaire with at
least one question. Issuing mints a fresh public token whose link expires after 40 hours;
regenerating kills the old token instantly. Question CRUD lives in questionnaire_questions.py,
answering and results in questionnaire_answers.py (the public router talks to that one).
"""
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.execution import QuestionnaireCreate, QuestionnaireUpdate
from app.services.execution.helpers import _WORKABLE, _assignment_open, _now, _patch, _row
from app.services.execution.correspondence import _assert_unit
from app.services.execution import procedures as proc_svc
from app.services.logs import log_status

_LINK_TTL = timedelta(hours=40)  # how long a public answer link stays valid

_QUEST_SQL = """
    SELECT q.questionnaire_id, q.procedure_id, q.assignment_id, q.unit_id,
           u.unit_code, u.org_id AS unit_org_id, q.title, q.intro, q.status,
           q.respondents_needed, q.public_token, q.link_expires_at, q.issued_at,
           (SELECT count(*) FROM aidaa_core.questionnaire_question qq
             WHERE qq.questionnaire_id = q.questionnaire_id) AS question_count,
           (SELECT count(*) FROM aidaa_core.questionnaire_response qr
             WHERE qr.questionnaire_id = q.questionnaire_id) AS responses_count,
           q.created_at, q.updated_at
    FROM aidaa_core.assignment_questionnaire q
    JOIN aidaa_core.ref_auditable_unit u ON u.unit_id = q.unit_id
"""


def get_questionnaire(db: Session, questionnaire_id: UUID) -> dict:
    return _row(db, f"{_QUEST_SQL} WHERE q.questionnaire_id = CAST(:d AS uuid)",
                {"d": str(questionnaire_id)}, "Questionnaire not found")


def procedure_assignment(db: Session, procedure_id: UUID) -> UUID:
    return proc_svc.get_procedure(db, procedure_id)["assignment_id"]


def get_question_assignment(db: Session, question_id: UUID) -> dict:
    return _row(db, """
        SELECT qq.questionnaire_id, q.assignment_id, q.status
        FROM aidaa_core.questionnaire_question qq
        JOIN aidaa_core.assignment_questionnaire q ON q.questionnaire_id = qq.questionnaire_id
        WHERE qq.question_id = CAST(:d AS uuid)
    """, {"d": str(question_id)}, "Question not found")


def list_questionnaires(db: Session, assignment_id: UUID, pic_orgs=None) -> list[dict]:
    sql = f"{_QUEST_SQL} WHERE q.assignment_id = CAST(:a AS uuid)"
    params: dict = {"a": str(assignment_id)}
    if pic_orgs is not None:
        sql += " AND u.org_id = ANY(CAST(:orgs AS uuid[]))"
        params["orgs"] = [str(o) for o in pic_orgs]
    sql += " ORDER BY q.created_at"
    return [dict(r._mapping) for r in db.execute(text(sql), params).fetchall()]


# --- needs_questionnaire toggle (the flag lives on the per-assignment procedure copy) ---

def set_needs_questionnaire(db: Session, procedure_id: UUID, value: bool, user_id: UUID) -> dict:
    """Same gating family as _proc_open: skipped procedures and procedures already under review
    stay frozen; the assignment itself may live in any active state while the team plans."""
    pr = proc_svc.get_procedure(db, procedure_id)
    if pr["pka_is_skipped"] or pr["is_skipped"]:
        raise HTTPException(status_code=409, detail="Procedure or its PKA is skipped")
    if pr["status"] not in ("planned", "in_progress"):
        raise HTTPException(status_code=409, detail="Procedure is under review or reviewed and cannot be edited")
    _patch(db, "aidaa_core.exe_procedure", "procedure_id", procedure_id,
           {"needs_questionnaire": value}, user_id)
    return proc_svc.get_procedure(db, procedure_id)


# --- team planning view: every non-skipped procedure with its (optional) questionnaire ---

def list_questionnaire_procedures(db: Session, assignment_id: UUID) -> list[dict]:
    from app.services.assignments import get_assignment
    get_assignment(db, assignment_id)
    rows = db.execute(text("""
        SELECT p.procedure_id, p.pka_id, k.title AS pka_title, p.step_no, p.procedure_text,
               p.needs_questionnaire, q.questionnaire_id,
               q.title AS questionnaire_title, q.intro AS questionnaire_intro,
               q.status AS questionnaire_status,
               q.respondents_needed, q.public_token, q.link_expires_at,
               (SELECT count(*) FROM aidaa_core.questionnaire_question qq
                 WHERE qq.questionnaire_id = q.questionnaire_id) AS question_count,
               (SELECT count(*) FROM aidaa_core.questionnaire_response qr
                 WHERE qr.questionnaire_id = q.questionnaire_id) AS responses_count
        FROM aidaa_core.exe_procedure p
        JOIN aidaa_core.pka k ON k.pka_id = p.pka_id
        LEFT JOIN aidaa_core.assignment_questionnaire q ON q.procedure_id = p.procedure_id
        WHERE k.assignment_id = CAST(:a AS uuid)
          AND p.is_skipped = FALSE AND k.is_skipped = FALSE
        ORDER BY k.title, p.step_no
    """), {"a": str(assignment_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


# --- questionnaire lifecycle ---

def create_questionnaire(db: Session, assignment_id: UUID, payload: QuestionnaireCreate,
                         user_id: UUID) -> dict:
    _assignment_open(db, assignment_id, _WORKABLE)
    pr = proc_svc.get_procedure(db, payload.procedure_id)
    if str(pr["assignment_id"]) != str(assignment_id):
        raise HTTPException(status_code=400, detail="Procedure does not belong to this assignment")
    if pr["is_skipped"] or pr["pka_is_skipped"]:
        raise HTTPException(status_code=409, detail="Questionnaires cannot be attached to a skipped procedure")
    _assert_unit(db, assignment_id, payload.unit_id)
    if db.execute(text("SELECT 1 FROM aidaa_core.assignment_questionnaire WHERE procedure_id = CAST(:p AS uuid)"),
                  {"p": str(payload.procedure_id)}).fetchone():
        raise HTTPException(status_code=409, detail="This procedure already has a questionnaire")
    qid = db.execute(text("""
        INSERT INTO aidaa_core.assignment_questionnaire
            (procedure_id, assignment_id, unit_id, title, intro, respondents_needed, created_by, updated_by)
        VALUES (CAST(:p AS uuid), CAST(:a AS uuid), CAST(:u AS uuid), :t, :i, :n, CAST(:c AS uuid), CAST(:c AS uuid))
        RETURNING questionnaire_id
    """), {"p": str(payload.procedure_id), "a": str(assignment_id), "u": str(payload.unit_id),
           "t": payload.title, "i": payload.intro, "n": payload.respondents_needed,
           "c": str(user_id)}).scalar_one()
    log_status(db, "questionnaire", qid, None, "draft", user_id)
    return get_questionnaire(db, qid)


def update_questionnaire(db: Session, questionnaire_id: UUID, payload, user_id: UUID) -> dict:
    q = get_questionnaire(db, questionnaire_id)
    _assignment_open(db, q["assignment_id"], _WORKABLE)
    cols = payload.model_dump(exclude_unset=True)
    if not cols:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if ("title" in cols or "intro" in cols) and q["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only a draft questionnaire can still be retitled")
    _patch(db, "aidaa_core.assignment_questionnaire", "questionnaire_id", questionnaire_id, cols, user_id)
    return get_questionnaire(db, questionnaire_id)


def delete_questionnaire(db: Session, questionnaire_id: UUID, user_id: UUID) -> None:
    q = get_questionnaire(db, questionnaire_id)
    _assignment_open(db, q["assignment_id"], _WORKABLE)
    if q["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only a draft questionnaire without responses can be deleted")
    db.execute(text("DELETE FROM aidaa_core.assignment_questionnaire WHERE questionnaire_id = CAST(:d AS uuid)"),
               {"d": str(questionnaire_id)})


def issue_batch(db: Session, assignment_id: UUID, user_id: UUID) -> list[dict]:
    """Issue every flagged procedure's draft questionnaire in one go; the leader is accountable."""
    _assignment_open(db, assignment_id, _WORKABLE)
    flagged = [p for p in list_questionnaire_procedures(db, assignment_id) if p["needs_questionnaire"]]
    if not flagged:
        raise HTTPException(status_code=409, detail="No procedure is marked as needing a questionnaire")
    missing, ready = [], []
    for p in flagged:
        label = f"step {p['step_no']}: {p['procedure_text']}"
        if not p["questionnaire_id"] or not p["question_count"]:
            missing.append(label)
        elif p["questionnaire_status"] == "draft":
            ready.append(p)
        # already issued or closed questionnaires stay untouched
    if missing:
        raise HTTPException(status_code=422,
                            detail="Cannot issue yet, questionnaire missing or empty for: " + "; ".join(missing))
    if not ready:
        raise HTTPException(status_code=409, detail="Nothing new to issue, every flagged procedure is already issued or closed")
    expires = _now() + _LINK_TTL
    out = []
    for p in ready:
        db.execute(text("""
            UPDATE aidaa_core.assignment_questionnaire
               SET status = 'issued', issued_at = :t, issued_by = CAST(:u AS uuid),
                   public_token = gen_random_uuid(), link_expires_at = :exp,
                   updated_at = now(), updated_by = CAST(:u AS uuid)
             WHERE questionnaire_id = CAST(:d AS uuid)
        """), {"t": _now(), "u": str(user_id), "exp": expires, "d": str(p["questionnaire_id"])})
        log_status(db, "questionnaire", p["questionnaire_id"], "draft", "issued", user_id)
        out.append(get_questionnaire(db, p["questionnaire_id"]))
    return out


def close_questionnaire(db: Session, questionnaire_id: UUID, user_id: UUID) -> dict:
    q = get_questionnaire(db, questionnaire_id)
    _assignment_open(db, q["assignment_id"], _WORKABLE)
    if q["status"] != "issued":
        raise HTTPException(status_code=409, detail="Only an issued questionnaire can be closed")
    _patch(db, "aidaa_core.assignment_questionnaire", "questionnaire_id", questionnaire_id,
           {"status": "closed"}, user_id)
    log_status(db, "questionnaire", questionnaire_id, "issued", "closed", user_id)
    return get_questionnaire(db, questionnaire_id)


def regenerate_link(db: Session, questionnaire_id: UUID, user_id: UUID) -> dict:
    """Fresh token + fresh expiry in ONE update, so the previous link dies instantly.
    Open to the team and to the auditee PIC of the questionnaire's own unit (router decides)."""
    q = get_questionnaire(db, questionnaire_id)
    _assignment_open(db, q["assignment_id"], _WORKABLE)
    if q["status"] != "issued":
        raise HTTPException(status_code=409, detail="Only an issued questionnaire has a link to renew")
    db.execute(text("""
        UPDATE aidaa_core.assignment_questionnaire
           SET public_token = gen_random_uuid(), link_expires_at = :exp,
               updated_at = now(), updated_by = CAST(:u AS uuid)
         WHERE questionnaire_id = CAST(:d AS uuid)
    """), {"exp": _now() + _LINK_TTL, "u": str(user_id), "d": str(questionnaire_id)})
    return get_questionnaire(db, questionnaire_id)
