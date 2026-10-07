from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import library_read, library_manage, log_audit
from app.schemas.aidaa import (
    PkaCreate, PkaUpdate, PkaOut,
    ProcedureCreate, ProcedureUpdate, ProcedureOut,
)
from app.services import masters_library as svc

router = APIRouter()


# --- PKA ---

@router.get("/library/pka", response_model=List[PkaOut])
def list_pka(active_only: bool = True, type_id: Optional[UUID] = None,
             search: Optional[str] = Query(None),
             db: Session = Depends(get_db), user=Depends(library_read)):
    return svc.list_pka(db, user.user_id, active_only, type_id, search)


@router.get("/library/pka/{library_pka_id}", response_model=PkaOut)
def get_pka(library_pka_id: UUID, db: Session = Depends(get_db), user=Depends(library_read)):
    return svc.get_pka(db, user.user_id, library_pka_id)


@router.post("/library/pka", response_model=PkaOut, status_code=201)
def create_pka(payload: PkaCreate, db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.create_pka(db, payload, user.user_id)
    log_audit(db, user.user_id, "library_pka.create", "library_pka", row["library_pka_id"],
              {"pka_code": row["pka_code"]})
    db.commit()
    return row


@router.patch("/library/pka/{library_pka_id}", response_model=PkaOut)
def update_pka(library_pka_id: UUID, payload: PkaUpdate,
               db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.update_pka(db, library_pka_id, payload, user.user_id)
    log_audit(db, user.user_id, "library_pka.update", "library_pka", library_pka_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/library/pka/{library_pka_id}", response_model=PkaOut)
def deactivate_pka(library_pka_id: UUID, db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.deactivate_pka(db, library_pka_id, user.user_id)
    log_audit(db, user.user_id, "library_pka.deactivate", "library_pka", library_pka_id)
    db.commit()
    return row


# --- Procedures ---

@router.get("/library/pka/{library_pka_id}/procedures", response_model=List[ProcedureOut])
def list_procedures(library_pka_id: UUID, active_only: bool = True,
                    db: Session = Depends(get_db), user=Depends(library_read)):
    return svc.list_procedures(db, user.user_id, library_pka_id, active_only)


@router.post("/library/pka/{library_pka_id}/procedures", response_model=ProcedureOut, status_code=201)
def create_procedure(library_pka_id: UUID, payload: ProcedureCreate,
                     db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.create_procedure(db, library_pka_id, payload, user.user_id)
    log_audit(db, user.user_id, "library_procedure.create", "library_procedure", row["procedure_id"],
              {"library_pka_id": str(library_pka_id), "step_no": row["step_no"]})
    db.commit()
    return row


@router.patch("/library/procedures/{procedure_id}", response_model=ProcedureOut)
def update_procedure(procedure_id: UUID, payload: ProcedureUpdate,
                     db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.update_procedure(db, procedure_id, payload, user.user_id)
    log_audit(db, user.user_id, "library_procedure.update", "library_procedure", procedure_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/library/procedures/{procedure_id}", response_model=ProcedureOut)
def deactivate_procedure(procedure_id: UUID, db: Session = Depends(get_db), user=Depends(library_manage)):
    row = svc.deactivate_procedure(db, procedure_id, user.user_id)
    log_audit(db, user.user_id, "library_procedure.deactivate", "library_procedure", procedure_id)
    db.commit()
    return row