from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    get_current_user, pka_read, pka_create, report_create, authorize_assignment, authorize_view,
    log_audit, ROLES_WORK, ROLES_LEAD,
)
from app.schemas.ai import AiRequest, ModelsOut, SuggestionDecision, SuggestionOut
from app.services import ai_suggestions as svc
from app.services.ai_engine import list_ollama_models

router = APIRouter()
_AUTH = {"pka": ("audit.pka.create", ROLES_WORK), "report": ("audit.report.create", ROLES_LEAD)}


def _team_only(db: Session, user, code: str, assignment_id: UUID):
    if authorize_view(db, user, code, assignment_id) != "team":
        raise HTTPException(status_code=403, detail="AI suggestions are for the audit team only")


@router.get("/ai/models", response_model=ModelsOut)
def ollama_models(user=Depends(pka_read)):
    return {"data": list_ollama_models()}


@router.post("/assignment/{assignment_id}/ai/pka-suggestions", response_model=SuggestionOut, status_code=201)
def suggest_pka(assignment_id: UUID, payload: Optional[AiRequest] = None,
                db: Session = Depends(get_db), user=Depends(pka_create)):
    authorize_assignment(db, user, "audit.pka.create", assignment_id, ROLES_WORK)
    p = payload or AiRequest()
    row = svc.generate_pka(db, assignment_id, user.user_id, p.engine, p.model)
    log_audit(db, user.user_id, "ai.suggest_pka", "ai_suggestion", row["suggestion_id"],
              {"engine": row["engine"], "model": row["model_name"]})
    db.commit()
    return row


@router.post("/assignment/{assignment_id}/ai/report-suggestions", response_model=SuggestionOut, status_code=201)
def suggest_report(assignment_id: UUID, payload: Optional[AiRequest] = None,
                   db: Session = Depends(get_db), user=Depends(report_create)):
    authorize_assignment(db, user, "audit.report.create", assignment_id, ROLES_LEAD)
    p = payload or AiRequest()
    row = svc.generate_report(db, assignment_id, user.user_id, p.engine, p.model)
    log_audit(db, user.user_id, "ai.suggest_report", "ai_suggestion", row["suggestion_id"],
              {"engine": row["engine"], "model": row["model_name"]})
    db.commit()
    return row


@router.get("/assignment/{assignment_id}/ai/suggestions", response_model=List[SuggestionOut])
def list_suggestions(assignment_id: UUID, feature: Optional[str] = Query(None),
                     status: Optional[str] = Query(None),
                     db: Session = Depends(get_db), user=Depends(pka_read)):
    _team_only(db, user, "audit.pka.read", assignment_id)
    return svc.list_suggestions(db, assignment_id, feature, status)


@router.get("/ai/suggestions/{suggestion_id}", response_model=SuggestionOut)
def get_suggestion(suggestion_id: UUID, db: Session = Depends(get_db), user=Depends(pka_read)):
    row = svc.get_suggestion(db, suggestion_id)
    _team_only(db, user, "audit.pka.read", row["record_id"])
    return row


@router.post("/ai/suggestions/{suggestion_id}/decide", response_model=SuggestionOut)
def decide(suggestion_id: UUID, payload: SuggestionDecision,
           db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = svc.get_suggestion(db, suggestion_id)
    code, roles = _AUTH[s["feature"]]
    authorize_assignment(db, user, code, s["record_id"], roles)
    row = svc.decide(db, suggestion_id, payload, user.user_id)
    log_audit(db, user.user_id, f"ai.{payload.decision}", "ai_suggestion", suggestion_id,
              {"feature": s["feature"]})
    db.commit()
    return row