from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    assignment_read, logistics_write, check_org_permission, check_org_any_permission, log_audit,
)
from app.schemas.ai import ModelsOut, SuggestionDecision, SuggestionOut
from app.schemas.trip_ai import TripDraftRequest
from app.services import trip_ai as svc
from app.services.ai_engine import list_ollama_models
from app.services.roles import assert_assignment_visible

router = APIRouter()
_WRITE = ("audit.assignment.update", "audit.assignment.logistics")


def _can_write(db: Session, user, assignment_id: UUID):
    check_org_any_permission(db, user, _WRITE, "assignment", assignment_id)


def _resolved(db: Session, user, assignment_id: UUID) -> None:
    check_org_permission(db, user, "audit.assignment.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)


@router.get("/ai/models", response_model=ModelsOut)
def list_models(db: Session = Depends(get_db), user=Depends(assignment_read)):
    return {"data": list_ollama_models()}


@router.get("/{assignment_id}/ai/trip/drafts", response_model=list[SuggestionOut])
def list_drafts(assignment_id: UUID, status: Optional[str] = Query(None),
                db: Session = Depends(get_db), user=Depends(assignment_read)):
    _resolved(db, user, assignment_id)
    return svc.list_drafts(db, user.user_id, assignment_id, status)


@router.post("/{assignment_id}/ai/trip/drafts", response_model=SuggestionOut, status_code=201)
def create_draft(assignment_id: UUID, payload: TripDraftRequest,
                 db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.generate_draft(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "ai.trip_draft", "ai_suggestion", row["suggestion_id"],
              {"engine": row["engine"], "model": row["model_name"], "assignment_id": str(assignment_id)})
    db.commit()
    return row


@router.get("/{assignment_id}/ai/trip/drafts/{suggestion_id}", response_model=SuggestionOut)
def get_draft(assignment_id: UUID, suggestion_id: UUID,
              db: Session = Depends(get_db), user=Depends(assignment_read)):
    _resolved(db, user, assignment_id)
    return svc.get_draft(db, user.user_id, assignment_id, suggestion_id)


@router.post("/{assignment_id}/ai/trip/drafts/{suggestion_id}/decide", response_model=SuggestionOut)
def decide_draft(assignment_id: UUID, suggestion_id: UUID, payload: SuggestionDecision,
                 db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.decide_draft(db, assignment_id, suggestion_id, payload, user.user_id)
    log_audit(db, user.user_id, f"ai.trip_draft_{payload.decision}", "ai_suggestion", suggestion_id,
              {"assignment_id": str(assignment_id)})
    db.commit()
    return row