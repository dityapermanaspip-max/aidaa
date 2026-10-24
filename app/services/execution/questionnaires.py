"""Kuesioner (batch 07): procedure-linked questionnaires.

ONE questionnaire per PKA procedure (a UNIQUE column enforces it), at most 5 questions; kinds
are single_choice / multi_select (2..5 options), free_text and scale (max 4/5/6). The team flags
procedures with needs_questionnaire and the LEADER issues the flagged batch at once - issuing
refuses (422) while any flagged procedure still misses a questionnaire with at least one
question. Issuing mints a fresh public token whose link expires after 40 hours; regenerating
kills the old token instantly. Answering happens while the questionnaire is issued and the
assignment is workable, either through the unauthenticated public router
(app/api/v1/aidaa/public.py) or in-app by the auditee PIC. Results stay team-side and stay
evidence only: bare aggregates, no automatic findings and no working papers are derived.
"""
import json
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.execution import (
    QuestionnaireCreate, QuestionnaireQuestionIn, QuestionnaireResponseIn, QuestionnaireUpdate,
)
from app.services.execution.helpers import _WORKABLE, _assignment_open, _now, _patch, _row
from app.services.execution.correspondence import _assert_unit
from app.services.execution import procedures as proc_svc
from app.services.logs import log_status

_QUESTION_CAP = 5               # hard cap of questions per questionnaire
_CHOICE_CAP = 5                 # options per choice question
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


# --- questions (draft only; per-kind validation happens in python) ---

def list_questions(db: Session, questionnaire_id: UUID) -> list[dict]:
    rows = db.execute(text("""
        SELECT question_id, questionnaire_id, question_no, kind, question_text, choices, scale_max
        FROM aidaa_core.questionnaire_question
        WHERE questionnaire_id = CAST(:d AS uuid)
        ORDER BY question_no
    """), {"d": str(questionnaire_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def _validated_question(payload: QuestionnaireQuestionIn):
    kind = payload.kind
    if kind in ("single_choice", "multi_select"):
        choices = [c.strip() for c in (payload.choices or []) if c and c.strip()]
        if len(choices) < 2 or len(choices) > _CHOICE_CAP:
            raise HTTPException(status_code=422, detail=f"A {kind} question needs 2 to {_CHOICE_CAP} options")
        if len(set(choices)) != len(choices):
            raise HTTPException(status_code=422, detail="Options must not repeat")
        return kind, choices, None
    if kind == "scale":
        if payload.scale_max not in (4, 5, 6):
            raise HTTPException(status_code=422, detail="Scale max must be 4, 5 or 6")
        return kind, None, payload.scale_max
    return "free_text", None, None


def add_question(db: Session, questionnaire_id: UUID, payload: QuestionnaireQuestionIn,
                 user_id: UUID) -> list[dict]:
    q = get_questionnaire(db, questionnaire_id)
    _assignment_open(db, q["assignment_id"], _WORKABLE)
    if q["status"] != "draft":
        raise HTTPException(status_code=409, detail="Questions are locked once the questionnaire is issued")
    held = db.execute(text("SELECT count(*) FROM aidaa_core.questionnaire_question WHERE questionnaire_id = CAST(:d AS uuid)"),
                      {"d": str(questionnaire_id)}).scalar_one()
    if held >= _QUESTION_CAP:
        raise HTTPException(status_code=409, detail=f"A questionnaire holds at most {_QUESTION_CAP} questions")
    kind, choices, scale_max = _validated_question(payload)
    db.execute(text("""
        INSERT INTO aidaa_core.questionnaire_question
            (questionnaire_id, question_no, kind, question_text, choices, scale_max, created_by, updated_by)
        VALUES (CAST(:q AS uuid), COALESCE((SELECT MAX(question_no) + 1
                                            FROM aidaa_core.questionnaire_question
                                            WHERE questionnaire_id = CAST(:q AS uuid)), 1),
                :k, :t, CAST(:c AS jsonb), :mx, CAST(:u AS uuid), CAST(:u AS uuid))
    """), {"q": str(questionnaire_id), "k": kind, "t": payload.question_text,
           "c": json.dumps(choices) if choices else None, "mx": scale_max, "u": str(user_id)})
    return list_questions(db, questionnaire_id)


def delete_question(db: Session, question_id: UUID, user_id: UUID) -> list[dict]:
    qq = _row(db, """
        SELECT qq.question_id, qq.questionnaire_id, q.status, q.assignment_id
        FROM aidaa_core.questionnaire_question qq
        JOIN aidaa_core.assignment_questionnaire q ON q.questionnaire_id = qq.questionnaire_id
        WHERE qq.question_id = CAST(:d AS uuid)
    """, {"d": str(question_id)}, "Question not found")
    _assignment_open(db, qq["assignment_id"], _WORKABLE)
    if qq["status"] != "draft":
        raise HTTPException(status_code=409, detail="Questions are locked once the questionnaire is issued")
    db.execute(text("DELETE FROM aidaa_core.questionnaire_question WHERE question_id = CAST(:d AS uuid)"),
               {"d": str(question_id)})
    db.execute(text("""
        WITH r AS (SELECT question_id, ROW_NUMBER() OVER (ORDER BY question_no) AS rn
                   FROM aidaa_core.questionnaire_question
                   WHERE questionnaire_id = CAST(:q AS uuid))
        UPDATE aidaa_core.questionnaire_question qq
           SET question_no = r.rn
          FROM r
         WHERE qq.question_id = r.question_id
    """), {"q": str(qq["questionnaire_id"])})
    return list_questions(db, qq["questionnaire_id"])


# --- answering (public token link and auditee PIC in-app) ---

def public_questionnaire_id(db: Session, token: UUID) -> UUID:
    r = db.execute(text("""
        SELECT questionnaire_id FROM aidaa_core.assignment_questionnaire
        WHERE public_token = CAST(:t AS uuid)
    """), {"t": str(token)}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Questionnaire link is not valid")
    return r.questionnaire_id


def get_public(db: Session, token: UUID) -> dict:
    r = db.execute(text("""
        SELECT q.questionnaire_id, q.title, q.intro, q.status, q.respondents_needed,
               q.link_expires_at, a.status AS assignment_status,
               (SELECT count(*) FROM aidaa_core.questionnaire_response qr
                 WHERE qr.questionnaire_id = q.questionnaire_id) AS responses_count
        FROM aidaa_core.assignment_questionnaire q
        JOIN aidaa_core.assignment a ON a.assignment_id = q.assignment_id
        WHERE q.public_token = CAST(:t AS uuid)
    """), {"t": str(token)}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Questionnaire link is not valid")
    row = dict(r._mapping)
    if row["status"] != "issued":
        raise HTTPException(status_code=409, detail="The questionnaire is not accepting answers")
    if row["assignment_status"] not in _WORKABLE:
        raise HTTPException(status_code=409, detail="The questionnaire is inactive because its audit assignment is no longer workable")
    if row["link_expires_at"] is None or row["link_expires_at"] <= _now():
        raise HTTPException(status_code=410, detail="The questionnaire link has expired")
    row["questions"] = list_questions(db, row["questionnaire_id"])
    return row


def _validated_answers(db: Session, questionnaire_id: UUID, payload: QuestionnaireResponseIn) -> list[dict]:
    """Per-question validation: every question answered exactly once, payload column matches kind."""
    questions = {q["question_id"]: q for q in list_questions(db, questionnaire_id)}
    if not questions:
        raise HTTPException(status_code=409, detail="This questionnaire has no questions")
    seen: set = set()
    rows = []
    for ans in payload.answers:
        qq = questions.get(ans.question_id)
        if not qq:
            raise HTTPException(status_code=422, detail="Answers reference an unknown question")
        if ans.question_id in seen:
            raise HTTPException(status_code=422, detail="Duplicate answer for the same question")
        seen.add(ans.question_id)
        kind = qq["kind"]
        choices = list(qq["choices"]) if qq["choices"] else None
        if kind == "single_choice":
            v = ans.single_index
            if v is None or v < 1 or v > len(choices):
                raise HTTPException(status_code=422, detail=f"Answer for question {qq['question_no']} must pick one option")
        elif kind == "multi_select":
            m = ans.multi_indexes or []
            if not m or len(set(m)) != len(m):
                raise HTTPException(status_code=422, detail=f"Answer for question {qq['question_no']} must pick at least one distinct option")
            if any(i < 1 or i > len(choices) for i in m):
                raise HTTPException(status_code=422, detail=f"Answer for question {qq['question_no']} picks an option that does not exist")
        elif kind == "scale":
            v = ans.scale_value
            if v is None or v < 1 or v > qq["scale_max"]:
                raise HTTPException(status_code=422, detail=f"Answer for question {qq['question_no']} must be a value from 1 to {qq['scale_max']}")
        else:  # free_text
            v = ans.text_value
            if v is None:
                raise HTTPException(status_code=422, detail=f"Answer for question {qq['question_no']} must not be empty")
        rows.append({"question_id": qq["question_id"], "kind": kind,
                     "single_index": ans.single_index if kind == "single_choice" else None,
                     "multi_indexes": ans.multi_indexes if kind == "multi_select" else None,
                     "scale_value": ans.scale_value if kind == "scale" else None,
                     "text_value": ans.text_value if kind == "free_text" else None})
    if seen != set(questions):
        raise HTTPException(status_code=422, detail="Every question must be answered exactly once")
    return rows


def submit_response(db: Session, questionnaire_id: UUID, payload: QuestionnaireResponseIn,
                    via: str, user_id: UUID | None = None) -> dict:
    """Valid answers for an issued questionnaire while its assignment is workable. Public calls
    pass user_id=None; the auditee PIC passes its own user (submitted_via = 'pic')."""
    q = get_questionnaire(db, questionnaire_id)
    _assignment_open(db, q["assignment_id"], _WORKABLE)
    if q["status"] != "issued":
        raise HTTPException(status_code=409, detail="The questionnaire is not accepting answers")
    if q["link_expires_at"] is not None and q["link_expires_at"] <= _now():
        raise HTTPException(status_code=410, detail="The questionnaire link has expired")
    rows = _validated_answers(db, questionnaire_id, payload)
    rid = db.execute(text("""
        INSERT INTO aidaa_core.questionnaire_response
            (questionnaire_id, name, position, age, last_degree, gender, submitted_via, submitted_by)
        VALUES (CAST(:q AS uuid), :name, :pos, :age, :deg, :g, :via,
                CAST(:u AS uuid))
        RETURNING response_id
    """), {"q": str(questionnaire_id), "name": payload.name, "pos": payload.position,
           "age": payload.age, "deg": payload.last_degree, "g": payload.gender, "via": via,
           "u": str(user_id) if user_id else None}).scalar_one()
    for a in rows:
        db.execute(text("""
            INSERT INTO aidaa_core.questionnaire_answer
                (response_id, question_id, single_index, multi_indexes, scale_value, text_value)
            VALUES (CAST(:r AS uuid), CAST(:qq AS uuid), :si, CAST(:mi AS jsonb), :sv, :tv)
        """), {"r": str(rid), "qq": str(a["question_id"]), "si": a["single_index"],
               "mi": json.dumps(a["multi_indexes"]) if a["multi_indexes"] else None,
               "sv": a["scale_value"], "tv": a["text_value"]})
    fresh = get_questionnaire(db, questionnaire_id)
    return {"responses_count": fresh["responses_count"], "respondents_needed": fresh["respondents_needed"]}


# --- results (team-side, aggregation in python, evidence only) ---

def get_results(db: Session, questionnaire_id: UUID) -> dict:
    q = get_questionnaire(db, questionnaire_id)
    rows = db.execute(text("""
        SELECT qq.question_id, qq.question_no, qq.kind, qq.question_text, qq.choices, qq.scale_max,
               a.single_index, a.multi_indexes, a.scale_value, a.text_value
        FROM aidaa_core.questionnaire_question qq
        LEFT JOIN aidaa_core.questionnaire_answer a ON a.question_id = qq.question_id
        WHERE qq.questionnaire_id = CAST(:d AS uuid)
        ORDER BY qq.question_no
    """), {"d": str(questionnaire_id)}).fetchall()
    questions: dict = {}
    order: list = []
    for r in rows:
        row = dict(r._mapping)
        qid = row["question_id"]
        if qid not in questions:
            questions[qid] = {"question_id": qid, "question_no": row["question_no"], "kind": row["kind"],
                              "question_text": row["question_text"], "choices": row["choices"],
                              "scale_max": row["scale_max"], "option_counts": None, "scale_counts": None,
                              "average": None, "texts": None}
            order.append(qid)
        agg = questions[qid]
        if agg["kind"] in ("single_choice", "multi_select"):
            counts = agg.get("_counts") or [0] * len(agg["choices"])
            idxs = [row["single_index"]] if row["single_index"] is not None else (row["multi_indexes"] or [])
            for i in idxs:
                counts[i - 1] += 1
            agg["_counts"] = counts
        elif agg["kind"] == "scale":
            counts = agg.get("_counts") or [0] * (agg["scale_max"] or 0)
            total, n = agg.get("_avg") or (0, 0)
            if row["scale_value"] is not None:
                counts[row["scale_value"] - 1] += 1
                total += row["scale_value"]
                n += 1
            agg["_counts"] = counts
            agg["_avg"] = (total, n)
        else:
            texts = agg["texts"] or []
            if row["text_value"]:
                texts.append(row["text_value"])
            agg["texts"] = texts
    out = []
    for qid in order:
        agg = questions[qid]
        if agg["kind"] in ("single_choice", "multi_select"):
            agg["option_counts"] = [{"label": opt, "count": c} for opt, c in zip(agg["choices"], agg.get("_counts") or [])]
        elif agg["kind"] == "scale":
            counts = agg.get("_counts") or []
            agg["scale_counts"] = [{"label": str(i + 1), "count": c} for i, c in enumerate(counts)]
            total, n = agg.get("_avg") or (0, 0)
            agg["average"] = round(total / n, 2) if n else None
        out.append({k: v for k, v in agg.items() if not k.startswith("_")})
    respondents = [dict(r._mapping) for r in db.execute(text("""
        SELECT name, position, age, last_degree, gender, submitted_via
        FROM aidaa_core.questionnaire_response
        WHERE questionnaire_id = CAST(:d AS uuid)
        ORDER BY submitted_at
    """), {"d": str(questionnaire_id)}).fetchall()]
    return {"questionnaire_id": q["questionnaire_id"], "title": q["title"], "status": q["status"],
            "respondents_needed": q["respondents_needed"], "responses_count": q["responses_count"],
            "respondents": respondents, "questions": out}
