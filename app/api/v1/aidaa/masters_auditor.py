from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    auditor_read, auditor_create, auditor_update, auditor_delete,
    expertise_read, expertise_create, expertise_verify, log_audit,
)
from app.schemas.aidaa import (
    AuditorCreate, AuditorUpdate, AuditorOut,
    ExpertiseCreate, ExpertiseUpdate, ExpertiseVerify, ExpertiseOut,
    DocumentCreate, DocumentOut,
)
from app.schemas.ai import SuggestionDecision, SuggestionOut
from app.schemas.expertise_ai import ExpertiseExtractRequest
from app.schemas.jobs import JobAccepted
from app.services import jobs as jobsvc
from app.services import masters_auditor as svc
from app.services import expertise_ai as esvc

router = APIRouter()


# --- Auditors ---

@router.get("/auditors", response_model=List[AuditorOut])
def list_auditors(active_only: bool = True, search: Optional[str] = Query(None),
                  limit: Optional[int] = Query(None, ge=1, le=200), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), user=Depends(auditor_read)):
    return svc.list_auditors(db, user.user_id, active_only, search, limit, offset)


@router.get("/auditors/{auditor_id}", response_model=AuditorOut)
def get_auditor(auditor_id: UUID, db: Session = Depends(get_db), user=Depends(auditor_read)):
    return svc.get_auditor(db, auditor_id, user.user_id)


@router.post("/auditors", response_model=AuditorOut, status_code=201)
def create_auditor(payload: AuditorCreate, db: Session = Depends(get_db), user=Depends(auditor_create)):
    row = svc.create_auditor(db, payload, user.user_id)
    log_audit(db, user.user_id, "auditor.create", "auditor", row["auditor_id"],
              {"user_id": str(row["user_id"])})
    db.commit()
    return row


@router.patch("/auditors/{auditor_id}", response_model=AuditorOut)
def update_auditor(auditor_id: UUID, payload: AuditorUpdate,
                   db: Session = Depends(get_db), user=Depends(auditor_update)):
    row = svc.update_auditor(db, auditor_id, payload, user.user_id)
    log_audit(db, user.user_id, "auditor.update", "auditor", auditor_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/auditors/{auditor_id}", response_model=AuditorOut)
def deactivate_auditor(auditor_id: UUID, db: Session = Depends(get_db), user=Depends(auditor_delete)):
    row = svc.deactivate_auditor(db, auditor_id, user.user_id)
    log_audit(db, user.user_id, "auditor.deactivate", "auditor", auditor_id)
    db.commit()
    return row


# --- Expertise ---

@router.get("/auditors/{auditor_id}/expertise", response_model=List[ExpertiseOut])
def list_expertise(auditor_id: UUID, db: Session = Depends(get_db), user=Depends(expertise_read)):
    return svc.list_expertise(db, auditor_id, user.user_id)


@router.post("/auditors/{auditor_id}/expertise", response_model=ExpertiseOut, status_code=201)
def create_expertise(auditor_id: UUID, payload: ExpertiseCreate,
                     db: Session = Depends(get_db), user=Depends(expertise_create)):
    row = svc.create_expertise(db, auditor_id, payload, user.user_id)
    log_audit(db, user.user_id, "expertise.create", "expertise", row["expertise_id"],
              {"title": row["title"]})
    db.commit()
    return row


@router.patch("/expertise/{expertise_id}", response_model=ExpertiseOut)
def update_expertise(expertise_id: UUID, payload: ExpertiseUpdate,
                     db: Session = Depends(get_db), user=Depends(expertise_create)):
    row = svc.update_expertise(db, expertise_id, payload, user.user_id)
    log_audit(db, user.user_id, "expertise.update", "expertise", expertise_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/expertise/{expertise_id}/verify", response_model=ExpertiseOut)
def verify_expertise(expertise_id: UUID, payload: ExpertiseVerify,
                     db: Session = Depends(get_db), user=Depends(expertise_verify)):
    row = svc.verify_expertise(db, expertise_id, payload, user.user_id)
    log_audit(db, user.user_id, f"expertise.{payload.decision}", "expertise", expertise_id,
              payload.model_dump(mode="json"))
    db.commit()
    return row


@router.get("/expertise/{expertise_id}", response_model=ExpertiseOut)
def get_expertise(expertise_id: UUID, db: Session = Depends(get_db), user=Depends(expertise_read)):
    return svc.get_expertise(db, expertise_id, user.user_id)


# --- Expertise AI extraction (feature 'expertise_extract', seeded step record_type 'expertise') ---

@router.post("/auditors/{auditor_id}/expertise/ai-suggestions", response_model=JobAccepted, status_code=202)
def extract_expertise(auditor_id: UUID, payload: ExpertiseExtractRequest,
                      db: Session = Depends(get_db), user=Depends(expertise_create)):
    return jobsvc.enqueue(db, user.user_id, "ai.expertise_extract",
                          {"auditor_id": str(auditor_id),
                           "request": payload.model_dump(mode="json")},
                          audit={"action": "expertise.ai_extract", "target_type": "ai_suggestion",
                                 "metadata": {"auditor_id": str(auditor_id)}})


@router.get("/auditors/{auditor_id}/expertise/ai-suggestions", response_model=List[SuggestionOut])
def list_expertise_ai(auditor_id: UUID, status: Optional[str] = Query(None),
                      limit: Optional[int] = Query(None, ge=1, le=200), offset: int = Query(0, ge=0),
                      db: Session = Depends(get_db), user=Depends(expertise_read)):
    return esvc.list_extracts(db, user.user_id, auditor_id, status, limit, offset)


@router.post("/expertise-ai-suggestions/{suggestion_id}/decide", response_model=SuggestionOut)
def decide_expertise_ai(suggestion_id: UUID, payload: SuggestionDecision,
                        db: Session = Depends(get_db), user=Depends(expertise_create)):
    row = esvc.decide_extract(db, suggestion_id, payload, user.user_id)
    log_audit(db, user.user_id, f"expertise.ai_suggestion_{payload.decision}", "ai_suggestion", suggestion_id,
              {"feature": "expertise_extract"})
    db.commit()
    return row


@router.get("/expertise/{expertise_id}/documents", response_model=List[DocumentOut])
def list_documents(expertise_id: UUID, db: Session = Depends(get_db), user=Depends(expertise_read)):
    return svc.list_documents(db, expertise_id, user.user_id)


@router.post("/expertise/{expertise_id}/documents", response_model=DocumentOut, status_code=201)
def add_document(expertise_id: UUID, payload: DocumentCreate,
                 db: Session = Depends(get_db), user=Depends(expertise_create)):
    row = svc.add_document(db, expertise_id, payload, user.user_id)
    log_audit(db, user.user_id, "expertise.document_add", "expertise_document", row["doc_id"],
              {"file_name": row["file_name"]})
    db.commit()
    return row