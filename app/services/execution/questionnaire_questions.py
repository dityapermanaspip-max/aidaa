"""Kuesioner questions (batch 07): the ≤5-question builder, draft-only.

Question CRUD is locked once the questionnaire is issued (answers depend on the exact question
list). Kinds: single_choice / multi_select (2..5 options), free_text, scale (max 4/5/6); the
per-kind shape is validated here in python before the row is written.
"""
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.execution import QuestionnaireQuestionIn
from app.services.execution.helpers import _WORKABLE, _assignment_open, _row
from app.services.execution.questionnaires import get_questionnaire

_QUESTION_CAP = 5   # hard cap of questions per questionnaire
_CHOICE_CAP = 5     # options per choice question


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
