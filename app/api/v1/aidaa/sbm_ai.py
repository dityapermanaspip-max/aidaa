from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import costrate_read, costrate_create, log_audit
from app.schemas.ai import SuggestionDecision, SuggestionOut, ModelsOut
from app.schemas.sbm_ai import SbmDraftRequest
from app.services import sbm_ai as svc
from app.services.ai_engine import list_ollama_models

router = APIRouter()


@router.get("/sbm/ai/drafts", response_model=List[SuggestionOut])
def list_drafts(status: Optional[str] = Query(None),
                db: Session = Depends(get_db), user=Depends(costrate_read)):
    return svc.list_drafts(db, user.user_id, status)


@router.post("/sbm/ai/drafts", response_model=SuggestionOut, status_code=201)
def create_draft(payload: SbmDraftRequest, db: Session = Depends(get_db), user=Depends(costrate_create)):
    row = svc.generate_draft(db, payload, user.user_id)
    log_audit(db, user.user_id, "ai.sbm_draft", "ai_suggestion", row["suggestion_id"],
              {"engine": row["engine"], "model": row["model_name"], "annex": payload.annex_label})
    db.commit()
    return row

@router.get("/sbm/ai/models", response_model=ModelsOut)
def ollama_models(user=Depends(costrate_read)):
    return {"data": list_ollama_models()}

@router.get("/sbm/ai/drafts/{suggestion_id}", response_model=SuggestionOut)
def get_draft(suggestion_id: UUID, db: Session = Depends(get_db), user=Depends(costrate_read)):
    return svc.get_draft(db, user.user_id, suggestion_id)


@router.post("/sbm/ai/drafts/{suggestion_id}/decide", response_model=SuggestionOut)
def decide_draft(suggestion_id: UUID, payload: SuggestionDecision,
                 db: Session = Depends(get_db), user=Depends(costrate_create)):
    row = svc.decide_draft(db, suggestion_id, payload, user.user_id)
    log_audit(db, user.user_id, f"ai.sbm_draft_{payload.decision}", "ai_suggestion", suggestion_id)
    db.commit()
    return row