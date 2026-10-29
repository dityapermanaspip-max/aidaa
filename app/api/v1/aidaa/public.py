"""Unauthenticated public surface for kuesioner answering (batch 07).

Mounted WITHOUT the root-scoped dependency (see app/main.py): a respondent is anonymous and the
only data that leaves the backend through here is the questionnaire text, its questions and bare
counters - never stored responses, results or team information. The token link is single-use in
the sense that regeneration instantly invalidates it; expiry and assignment-state gates live in
app/services/execution/questionnaires.py. Anonymous submissions write no audit log (there is no
actor), so submitted_by stays NULL.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.execution import ProgressOut, PublicQuestionnaireOut, QuestionnaireResponseIn
from app.services.execution import questionnaire_answers as svc

router = APIRouter()


@router.get("/public/questionnaires/{token}", response_model=PublicQuestionnaireOut)
def get_public_questionnaire(token: UUID, db: Session = Depends(get_db)):
    data = svc.get_public(db, token)
    return {"title": data["title"], "intro": data["intro"],
            "respondents_needed": data["respondents_needed"],
            "responses_count": data["responses_count"],
            "link_expires_at": data["link_expires_at"], "questions": data["questions"]}


@router.post("/public/questionnaires/{token}", response_model=ProgressOut, status_code=201)
def submit_public_questionnaire(token: UUID, payload: QuestionnaireResponseIn,
                                db: Session = Depends(get_db)):
    qid = svc.public_questionnaire_id(db, token)
    out = svc.submit_response(db, qid, payload, "public", None)
    # There is no audit row to write (no actor), but the response itself must be committed: this
    # router does not go through the authenticated endpoints' commit path. The capacity advisory
    # lock is transaction-scoped, so it is released here too.
    db.commit()
    return out
