"""Public questionnaire answers: the capacity cap, its lock, and the anonymous commit.

The questionnaire chain is created inside the rollback transaction (see ``quiz``), so these tests
never persist an organisation, assignment or answer.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.aidaa import public
from app.core.database import engine
from app.schemas.execution import QuestionnaireResponseIn
from app.services.execution import questionnaire_answers as qa


def answer(question_id, text_value="jawaban"):
    return QuestionnaireResponseIn(
        name="Responden", position="Staf", age=30, last_degree="S1", gender="L",
        answers=[{"question_id": question_id, "text_value": text_value}],
    )


def response_count(db, questionnaire_id):
    return db.execute(text("""
        SELECT count(*) FROM aidaa_core.questionnaire_response
        WHERE questionnaire_id = CAST(:q AS uuid)
    """), {"q": str(questionnaire_id)}).scalar_one()


def test_capacity_is_enforced_on_the_second_submission(db, quiz):
    first = qa.submit_response(db, quiz.questionnaire_id, answer(quiz.question_id), "public", None)

    assert first == {"responses_count": 1, "respondents_needed": 1}

    with pytest.raises(HTTPException) as exc:
        qa.submit_response(db, quiz.questionnaire_id, answer(quiz.question_id), "public", None)

    assert exc.value.status_code == 409
    assert response_count(db, quiz.questionnaire_id) == 1


def test_conditional_insert_blocks_even_with_a_stale_precheck(db, quiz, monkeypatch):
    """The old code trusted a count read before the insert; the SQL guard must not."""
    qa.submit_response(db, quiz.questionnaire_id, answer(quiz.question_id), "public", None)
    stale = qa.get_questionnaire(db, quiz.questionnaire_id)
    stale["responses_count"] = 0
    monkeypatch.setattr(qa, "get_questionnaire", lambda session, qid: stale)

    with pytest.raises(HTTPException) as exc:
        qa.submit_response(db, quiz.questionnaire_id, answer(quiz.question_id), "public", None)

    assert exc.value.status_code == 409
    assert response_count(db, quiz.questionnaire_id) == 1


def test_submission_holds_a_lock_on_that_questionnaire(db, quiz):
    qa.submit_response(db, quiz.questionnaire_id, answer(quiz.question_id), "public", None)

    with engine.connect() as other:
        held = other.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(CAST(:q AS text)))"),
            {"q": str(quiz.questionnaire_id)},
        ).scalar()
        free = other.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(CAST(:q AS text)))"),
            {"q": str(uuid4())},
        ).scalar()

    assert held is False, "the submitting transaction must hold the questionnaire lock"
    assert free is True, "a different questionnaire must not be blocked"


def test_public_router_commits_the_anonymous_response(monkeypatch):
    """The public router has no audit row to write, so it must commit the answer itself."""
    class FakeDB:
        committed = False

        def commit(self):
            self.committed = True

    calls = {}

    def fake_submit(db, questionnaire_id, payload, via, user_id):
        calls.update(qid=questionnaire_id, via=via, user_id=user_id)
        return {"responses_count": 1, "respondents_needed": 1}

    monkeypatch.setattr(public.svc, "public_questionnaire_id", lambda db, token: uuid4())
    monkeypatch.setattr(public.svc, "submit_response", fake_submit)
    db = FakeDB()

    out = public.submit_public_questionnaire(uuid4(), answer(uuid4()), db)

    assert out["responses_count"] == 1
    assert db.committed is True
    assert calls["via"] == "public" and calls["user_id"] is None
