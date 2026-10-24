"""Kuesioner answering and results (batch 07).

Answering happens while the questionnaire is issued and its assignment is workable, either through
the unauthenticated public router (app/api/v1/aidaa/public.py, token-based, no actor) or in-app by
the auditee PIC. Results stay team-side and stay evidence only: bare aggregates in python, no
automatic findings and no working papers are derived from answers.
"""
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.execution import QuestionnaireResponseIn
from app.services.execution.helpers import _WORKABLE, _assignment_open, _now
from app.services.execution.questionnaires import get_questionnaire
from app.services.execution.questionnaire_questions import list_questions


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
