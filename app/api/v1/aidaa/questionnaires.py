"""Kuesioner routes (batch 07): procedure-linked questionnaires.

Permission reuse only (IAM cannot be seeded from here). Team planning/manage = the assignment
update code over ROLES_WORK; the batch ISSUE is the leader's (ROLES_LEAD, accountable); the
auditee PIC submits an in-app response through audit.finding.respond + authorize_pic scoped to
the questionnaire's own unit; reads go through authorize_view with audit.finding.read and PIC
lists are org-filtered. Results are team-only (the PIC never sees stored answers). The public
token link lives in app/api/v1/aidaa/public.py (mounted without the root dependency).
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    assignment_update, finding_read, finding_respond, ROLES_LEAD, ROLES_WORK,
    authorize_assignment, authorize_view, authorize_pic, log_audit,
)
from app.services.roles import is_auditee_pic, assignment_scope, pic_unit_orgs
from app.schemas.execution import (
    ExeProcOut, NeedsQuestionnaireIn, ProgressOut, QuestionnaireCreate, QuestionnaireOut,
    QuestionnaireProcedureOut, QuestionnaireQuestionIn, QuestionnaireResponseIn,
    QuestionnaireUpdate, QuestionOut, ResultsOut,
)
from app.services.execution import questionnaires as svc

router = APIRouter()


def _manage(db: Session, user, assignment_id: UUID):
    authorize_assignment(db, user, "audit.assignment.update", assignment_id, ROLES_WORK)


def _pic_orgs(db: Session, user, assignment_id: UUID):
    return pic_unit_orgs(db, user.user_id, assignment_scope(db, assignment_id)["unit_org_ids"])


# --- reads ---

@router.get("/assignment/{assignment_id}/questionnaires", response_model=List[QuestionnaireOut])
def list_questionnaires(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    mode = authorize_view(db, user, "audit.finding.read", assignment_id)
    pic_orgs = _pic_orgs(db, user, assignment_id) if mode == "pic" else None
    return svc.list_questionnaires(db, assignment_id, pic_orgs)


@router.get("/assignment/{assignment_id}/questionnaire-procedures",
            response_model=List[QuestionnaireProcedureOut])
def list_questionnaire_procedures(assignment_id: UUID, db: Session = Depends(get_db),
                                  user=Depends(finding_read)):
    mode = authorize_view(db, user, "audit.finding.read", assignment_id)
    if mode == "pic":
        raise HTTPException(status_code=403, detail="Questionnaire planning is team-only")
    return svc.list_questionnaire_procedures(db, assignment_id)


@router.get("/questionnaire/{questionnaire_id}/questions", response_model=List[QuestionOut])
def list_questions(questionnaire_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    q = svc.get_questionnaire(db, questionnaire_id)
    authorize_view(db, user, "audit.finding.read", q["assignment_id"])
    return svc.list_questions(db, questionnaire_id)


@router.get("/questionnaire/{questionnaire_id}/results", response_model=ResultsOut)
def get_results(questionnaire_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    q = svc.get_questionnaire(db, questionnaire_id)
    mode = authorize_view(db, user, "audit.finding.read", q["assignment_id"])
    if mode == "pic":
        raise HTTPException(status_code=403, detail="Questionnaire results are team-only")
    return svc.get_results(db, questionnaire_id)


# --- team planning & build ---

@router.post("/assignment/{assignment_id}/questionnaires", response_model=QuestionnaireOut, status_code=201)
def create_questionnaire(assignment_id: UUID, payload: QuestionnaireCreate,
                         db: Session = Depends(get_db), user=Depends(assignment_update)):
    _manage(db, user, assignment_id)
    row = svc.create_questionnaire(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "questionnaire.create", "assignment_questionnaire",
              row["questionnaire_id"], {"assignment_id": str(assignment_id),
                                        "procedure_id": str(payload.procedure_id)})
    db.commit()
    return row


@router.patch("/questionnaire/{questionnaire_id}", response_model=QuestionnaireOut)
def update_questionnaire(questionnaire_id: UUID, payload: QuestionnaireUpdate,
                         db: Session = Depends(get_db), user=Depends(assignment_update)):
    _manage(db, user, svc.get_questionnaire(db, questionnaire_id)["assignment_id"])
    row = svc.update_questionnaire(db, questionnaire_id, payload, user.user_id)
    log_audit(db, user.user_id, "questionnaire.update", "assignment_questionnaire", questionnaire_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/questionnaire/{questionnaire_id}", status_code=204)
def delete_questionnaire(questionnaire_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_update)):
    _manage(db, user, svc.get_questionnaire(db, questionnaire_id)["assignment_id"])
    svc.delete_questionnaire(db, questionnaire_id, user.user_id)
    log_audit(db, user.user_id, "questionnaire.delete", "assignment_questionnaire", questionnaire_id)
    db.commit()


@router.post("/questionnaire/{questionnaire_id}/questions", response_model=List[QuestionOut], status_code=201)
def add_question(questionnaire_id: UUID, payload: QuestionnaireQuestionIn,
                 db: Session = Depends(get_db), user=Depends(assignment_update)):
    _manage(db, user, svc.get_questionnaire(db, questionnaire_id)["assignment_id"])
    rows = svc.add_question(db, questionnaire_id, payload, user.user_id)
    log_audit(db, user.user_id, "questionnaire.question.add", "assignment_questionnaire",
              questionnaire_id, {"kind": payload.kind, "question_text": payload.question_text})
    db.commit()
    return rows


@router.delete("/question/{question_id}", response_model=List[QuestionOut])
def delete_question(question_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_update)):
    _manage(db, user, svc.get_question_assignment(db, question_id)["assignment_id"])
    rows = svc.delete_question(db, question_id, user.user_id)
    log_audit(db, user.user_id, "questionnaire.question.delete", "questionnaire_question", question_id)
    db.commit()
    return rows


@router.post("/assignment/{assignment_id}/questionnaires/issue", response_model=List[QuestionnaireOut])
def issue_batch(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_update)):
    # ISSUE is the leader's: ROLES_LEAD, the accountable role.
    authorize_assignment(db, user, "audit.assignment.update", assignment_id, ROLES_LEAD)
    rows = svc.issue_batch(db, assignment_id, user.user_id)
    log_audit(db, user.user_id, "questionnaire.issue", "assignment", assignment_id,
              {"issued": [str(r["questionnaire_id"]) for r in rows]})
    db.commit()
    return rows


@router.post("/questionnaire/{questionnaire_id}/close", response_model=QuestionnaireOut)
def close_questionnaire(questionnaire_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_update)):
    _manage(db, user, svc.get_questionnaire(db, questionnaire_id)["assignment_id"])
    row = svc.close_questionnaire(db, questionnaire_id, user.user_id)
    log_audit(db, user.user_id, "questionnaire.close", "assignment_questionnaire", questionnaire_id)
    db.commit()
    return row


@router.post("/questionnaire/{questionnaire_id}/regenerate", response_model=QuestionnaireOut)
def regenerate_link(questionnaire_id: UUID, db: Session = Depends(get_db), user=Depends(finding_respond)):
    """Team (assignment update over ROLES_WORK) or the auditee PIC of this questionnaire's unit."""
    q = svc.get_questionnaire(db, questionnaire_id)
    if is_auditee_pic(db, user.user_id, q["unit_org_id"]):
        authorize_pic(db, user, "audit.finding.respond", q["assignment_id"])
    else:
        _manage(db, user, q["assignment_id"])
    row = svc.regenerate_link(db, questionnaire_id, user.user_id)
    log_audit(db, user.user_id, "questionnaire.regenerate", "assignment_questionnaire", questionnaire_id)
    db.commit()
    return row


@router.post("/questionnaire/{questionnaire_id}/responses", response_model=ProgressOut, status_code=201)
def submit_pic_response(questionnaire_id: UUID, payload: QuestionnaireResponseIn,
                        db: Session = Depends(get_db), user=Depends(finding_respond)):
    q = svc.get_questionnaire(db, questionnaire_id)
    authorize_pic(db, user, "audit.finding.respond", q["assignment_id"])
    if not is_auditee_pic(db, user.user_id, q["unit_org_id"]):
        raise HTTPException(status_code=403, detail="The questionnaire belongs to another audited unit")
    out = svc.submit_response(db, questionnaire_id, payload, "pic", user.user_id)
    log_audit(db, user.user_id, "questionnaire.respond", "assignment_questionnaire", questionnaire_id)
    db.commit()
    return out


@router.patch("/procedures/{procedure_id}/needs-questionnaire", response_model=ExeProcOut)
def set_needs_questionnaire(procedure_id: UUID, payload: NeedsQuestionnaireIn,
                            db: Session = Depends(get_db), user=Depends(assignment_update)):
    _manage(db, user, svc.procedure_assignment(db, procedure_id))
    row = svc.set_needs_questionnaire(db, procedure_id, payload.needs_questionnaire, user.user_id)
    log_audit(db, user.user_id, "procedure.needs_questionnaire", "exe_procedure", procedure_id,
              {"needs_questionnaire": payload.needs_questionnaire})
    db.commit()
    return row
