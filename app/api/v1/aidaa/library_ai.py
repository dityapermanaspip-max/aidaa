# app/routers/library_ai.py
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import library_manage, library_read, log_audit
from app.schemas.ai import ModelsOut, SuggestionDecision, SuggestionOut
from app.schemas.jobs import JobAccepted
from app.schemas.library_ai import LibraryDraftRequest, LibraryImproveRequest
from app.services import jobs as jobsvc
from app.services import library_ai as svc
from app.services import library_ai_improvement as isvc
from app.services.ai_engine import list_ollama_models

router = APIRouter()


@router.get("/library/ai/models", response_model=ModelsOut)
def list_models(user=Depends(library_manage)):
    return {"data": list_ollama_models()}


@router.get("/library/ai/drafts", response_model=List[SuggestionOut])
def list_drafts(type_id: Optional[UUID] = None, status: Optional[str] = Query(None),
                limit: Optional[int] = Query(None, ge=1, le=200), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), user=Depends(library_manage)):
    return svc.list_drafts(db, user.user_id, type_id, status, limit, offset)


@router.post("/library/ai/drafts", response_model=JobAccepted, status_code=202)
def create_draft(payload: LibraryDraftRequest, db: Session = Depends(get_db), user=Depends(library_manage)):
    return jobsvc.enqueue(db, user.user_id, "ai.library_draft",
                          {"request": payload.model_dump(mode="json")},
                          audit={"action": "ai.library_draft", "target_type": "ai_suggestion",
                                 "metadata": {"type_id": str(payload.type_id)}})


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


# --- library_improvement: rewrite one library PKA (accept deactivates the old head) ---

@router.post("/library/pka/{library_pka_id}/ai-improvement", response_model=JobAccepted, status_code=202)
def create_improvement(library_pka_id: UUID, payload: LibraryImproveRequest,
                       db: Session = Depends(get_db), user=Depends(library_manage)):
    return jobsvc.enqueue(db, user.user_id, "ai.library_improvement",
                          {"library_pka_id": str(library_pka_id),
                           "request": payload.model_dump(mode="json")},
                          audit={"action": "ai.library_improvement", "target_type": "ai_suggestion",
                                 "metadata": {"library_pka_id": str(library_pka_id)}})


@router.get("/library/pka/{library_pka_id}/ai-improvements", response_model=List[SuggestionOut])
def list_improvements(library_pka_id: UUID, status: Optional[str] = Query(None),
                      limit: Optional[int] = Query(None, ge=1, le=200), offset: int = Query(0, ge=0),
                      db: Session = Depends(get_db), user=Depends(library_read)):
    return isvc.list_improvements(db, user.user_id, library_pka_id, status, limit, offset)


@router.post("/library/ai/improvements/{suggestion_id}/decide", response_model=SuggestionOut)
def decide_improvement(suggestion_id: UUID, payload: SuggestionDecision,
                       db: Session = Depends(get_db), user=Depends(library_manage)):
    row = isvc.decide_improvement(db, user.user_id, suggestion_id, payload)
    log_audit(db, user.user_id, f"ai.library_improvement_{payload.decision}", "ai_suggestion", suggestion_id)
    db.commit()
    return row