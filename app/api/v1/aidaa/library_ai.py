# app/routers/library_ai.py
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import library_manage, log_audit
from app.schemas.ai import ModelsOut, SuggestionDecision, SuggestionOut
from app.schemas.library_ai import LibraryDraftRequest
from app.services import library_ai as svc
from app.services.ai_engine import list_ollama_models

router = APIRouter()


@router.get("/library/ai/models", response_model=ModelsOut)
def list_models(user=Depends(library_manage)):
    return {"data": list_ollama_models()}


@router.get("/library/ai/drafts", response_model=List[SuggestionOut])
def list_drafts(type_id: Optional[UUID] = None, status: Optional[str] = Query(None),
                db: Session = Depends(get_db), user=Depends(library_manage)):
    return svc.list_drafts(db, user.user_id, type_id, status)


@router.post("/library/ai/drafts", response_model=SuggestionOut, status_code=201)
def create_draft(payload: LibraryDraftRequest, db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.generate_draft(db, payload, user.user_id)
    log_audit(db, user.user_id, "ai.library_draft", "ai_suggestion", row["suggestion_id"],
              {"engine": row["engine"], "model": row["model_name"], "type_id": str(payload.type_id)})
    db.commit()
    return row


@router.get("/library/ai/drafts/{suggestion_id}", response_model=SuggestionOut)
def get_draft(suggestion_id: UUID, db: Session = Depends(get_db), user=Depends(library_manage)):
    return svc.get_draft(db, user.user_id, suggestion_id)


@router.post("/library/ai/drafts/{suggestion_id}/decide", response_model=SuggestionOut)
def decide_draft(suggestion_id: UUID, payload: SuggestionDecision,
                 db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.decide_draft(db, suggestion_id, payload, user.user_id)
    log_audit(db, user.user_id, f"ai.library_draft_{payload.decision}", "ai_suggestion", suggestion_id)
    db.commit()
    return row