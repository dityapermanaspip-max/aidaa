from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    coststd_read, coststd_create, coststd_update, coststd_delete, log_audit,
)
from app.schemas.funding import (
    FundingCreate, FundingUpdate, FundingOut, FundingDocCreate, FundingDocOut,
)
from app.services import funding as svc

router = APIRouter()


@router.get("/sources", response_model=List[FundingOut])
def list_funding(active_only: bool = True, fiscal_year: Optional[int] = None,
                 funding_type: Optional[str] = Query(None), search: Optional[str] = Query(None),
                 db: Session = Depends(get_db), user=Depends(coststd_read)):
    return svc.list_funding(db, user.user_id, active_only, fiscal_year, funding_type, search)


@router.get("/sources/{funding_id}", response_model=FundingOut)
def get_funding(funding_id: UUID, db: Session = Depends(get_db), user=Depends(coststd_read)):
    return svc.get_funding(db, user.user_id, funding_id)


@router.post("/sources", response_model=FundingOut, status_code=201)
def create_funding(payload: FundingCreate, db: Session = Depends(get_db), user=Depends(coststd_create)):
    row = svc.create_funding(db, payload, user.user_id)
    log_audit(db, user.user_id, "funding.create", "ref_funding_source", row["funding_id"],
              {"funding_code": row["funding_code"]})
    db.commit()
    return row


@router.patch("/sources/{funding_id}", response_model=FundingOut)
def update_funding(funding_id: UUID, payload: FundingUpdate,
                   db: Session = Depends(get_db), user=Depends(coststd_update)):
    row = svc.update_funding(db, funding_id, payload, user.user_id)
    log_audit(db, user.user_id, "funding.update", "ref_funding_source", funding_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/sources/{funding_id}", response_model=FundingOut)
def deactivate_funding(funding_id: UUID, db: Session = Depends(get_db), user=Depends(coststd_delete)):
    row = svc.deactivate_funding(db, funding_id, user.user_id)
    log_audit(db, user.user_id, "funding.deactivate", "ref_funding_source", funding_id)
    db.commit()
    return row


@router.get("/sources/{funding_id}/documents", response_model=List[FundingDocOut])
def list_docs(funding_id: UUID, db: Session = Depends(get_db), user=Depends(coststd_read)):
    return svc.list_docs(db, user.user_id, funding_id)


@router.post("/sources/{funding_id}/documents", response_model=FundingDocOut, status_code=201)
def add_doc(funding_id: UUID, payload: FundingDocCreate,
            db: Session = Depends(get_db), user=Depends(coststd_create)):
    row = svc.add_doc(db, funding_id, payload, user.user_id)
    log_audit(db, user.user_id, "funding.document_add", "funding_document", row["doc_id"],
              {"funding_id": str(funding_id), "doc_type": row["doc_type"]})
    db.commit()
    return row