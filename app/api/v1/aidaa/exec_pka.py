from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    pka_read, pka_create, pka_update, paper_read, paper_create, paper_update, paper_review,
    assignment_update, check_org_permission, authorize_assignment, authorize_view, log_audit,
    ROLES_WORK, ROLES_LEAD, ROLES_SUP, ROLES_LEAD_SUP,
)
from app.schemas.execution import (
    CopyLibraryIn, ExePkaCreate, ExePkaUpdate, ExePkaOut, PkaComplete, SkipIn,
    ExeProcCreate, ExeProcUpdate, ExeProcOut, PaperCreate, PaperUpdate, PaperOut,
)
from app.services import execution_flow as svc

router = APIRouter()


# --- PKA ---

@router.get("/assignment/{assignment_id}/pka", response_model=List[ExePkaOut])
def list_pka(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(pka_read)):
    authorize_view(db, user, "audit.pka.read", assignment_id)
    return svc.list_pka(db, assignment_id)


@router.post("/assignment/{assignment_id}/pka/copy-library", response_model=List[ExePkaOut], status_code=201)
def copy_library(assignment_id: UUID, payload: Optional[CopyLibraryIn] = None,
                 db: Session = Depends(get_db), user=Depends(assignment_update)):
    check_org_permission(db, user, "audit.assignment.update", "assignment", assignment_id)
    ids = (payload or CopyLibraryIn()).library_pka_ids
    rows = svc.copy_library(db, assignment_id, ids, user.user_id)
    log_audit(db, user.user_id, "pka.copy_library", "assignment", assignment_id, {"pka_count": len(rows)})
    db.commit()
    return rows


@router.post("/assignment/{assignment_id}/pka", response_model=ExePkaOut, status_code=201)
def create_pka(assignment_id: UUID, payload: ExePkaCreate,
               db: Session = Depends(get_db), user=Depends(pka_create)):
    authorize_assignment(db, user, "audit.pka.create", assignment_id, ROLES_WORK)
    row = svc.create_pka(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "pka.create", "pka", row["pka_id"], {"assignment_id": str(assignment_id)})
    db.commit()
    return row


@router.get("/pka/{pka_id}", response_model=ExePkaOut)
def get_pka(pka_id: UUID, db: Session = Depends(get_db), user=Depends(pka_read)):
    row = svc.get_pka(db, pka_id)
    authorize_view(db, user, "audit.pka.read", row["assignment_id"])
    return row


@router.patch("/pka/{pka_id}", response_model=ExePkaOut)
def update_pka(pka_id: UUID, payload: ExePkaUpdate,
               db: Session = Depends(get_db), user=Depends(pka_update)):
    authorize_assignment(db, user, "audit.pka.update", svc.get_pka(db, pka_id)["assignment_id"], ROLES_WORK)
    row = svc.update_pka(db, pka_id, payload, user.user_id)
    log_audit(db, user.user_id, "pka.update", "pka", pka_id, payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/pka/{pka_id}/skip", response_model=ExePkaOut)
def skip_pka(pka_id: UUID, payload: SkipIn, db: Session = Depends(get_db), user=Depends(pka_update)):
    authorize_assignment(db, user, "audit.pka.update", svc.get_pka(db, pka_id)["assignment_id"], ROLES_WORK)
    row = svc.set_pka_skip(db, pka_id, True, payload.reason, user.user_id)
    log_audit(db, user.user_id, "pka.skip", "pka", pka_id, {"reason": payload.reason})
    db.commit()
    return row


@router.post("/pka/{pka_id}/unskip", response_model=ExePkaOut)
def unskip_pka(pka_id: UUID, db: Session = Depends(get_db), user=Depends(pka_update)):
    authorize_assignment(db, user, "audit.pka.update", svc.get_pka(db, pka_id)["assignment_id"], ROLES_WORK)
    row = svc.set_pka_skip(db, pka_id, False, None, user.user_id)
    log_audit(db, user.user_id, "pka.unskip", "pka", pka_id)
    db.commit()
    return row


@router.post("/pka/{pka_id}/submit", response_model=ExePkaOut)
def submit_pka(pka_id: UUID, db: Session = Depends(get_db), user=Depends(pka_update)):
    authorize_assignment(db, user, "audit.pka.update", svc.get_pka(db, pka_id)["assignment_id"], ROLES_LEAD)
    row = svc.submit_pka(db, pka_id, user.user_id)
    log_audit(db, user.user_id, "pka.submit", "pka", pka_id)
    db.commit()
    return row


@router.post("/pka/{pka_id}/complete", response_model=ExePkaOut)
def complete_pka(pka_id: UUID, payload: Optional[PkaComplete] = None,
                 db: Session = Depends(get_db), user=Depends(pka_update)):
    authorize_assignment(db, user, "audit.pka.update", svc.get_pka(db, pka_id)["assignment_id"], ROLES_LEAD)
    row = svc.complete_pka(db, pka_id, (payload or PkaComplete()).actual_hours, user.user_id)
    log_audit(db, user.user_id, "pka.complete", "pka", pka_id)
    db.commit()
    return row


# --- Procedures ---

@router.get("/pka/{pka_id}/procedures", response_model=List[ExeProcOut])
def list_procedures(pka_id: UUID, db: Session = Depends(get_db), user=Depends(pka_read)):
    authorize_view(db, user, "audit.pka.read", svc.get_pka(db, pka_id)["assignment_id"])
    return svc.list_procedures(db, pka_id)


@router.post("/pka/{pka_id}/procedures", response_model=ExeProcOut, status_code=201)
def create_procedure(pka_id: UUID, payload: ExeProcCreate,
                     db: Session = Depends(get_db), user=Depends(pka_create)):
    authorize_assignment(db, user, "audit.pka.create", svc.get_pka(db, pka_id)["assignment_id"], ROLES_WORK)
    row = svc.create_procedure(db, pka_id, payload, user.user_id)
    log_audit(db, user.user_id, "procedure.create", "exe_procedure", row["procedure_id"], {"pka_id": str(pka_id)})
    db.commit()
    return row


@router.patch("/procedures/{procedure_id}", response_model=ExeProcOut)
def update_procedure(procedure_id: UUID, payload: ExeProcUpdate,
                     db: Session = Depends(get_db), user=Depends(paper_update)):
    pr = svc.get_procedure(db, procedure_id)
    role = authorize_assignment(db, user, "audit.paper.update", pr["assignment_id"], ROLES_WORK)
    row = svc.update_procedure(db, procedure_id, payload, user.user_id, role)
    log_audit(db, user.user_id, "procedure.update", "exe_procedure", procedure_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/procedures/{procedure_id}/skip", response_model=ExeProcOut)
def skip_procedure(procedure_id: UUID, payload: SkipIn, db: Session = Depends(get_db), user=Depends(paper_update)):
    authorize_assignment(db, user, "audit.paper.update", svc.get_procedure(db, procedure_id)["assignment_id"], ROLES_WORK)
    row = svc.set_procedure_skip(db, procedure_id, True, payload.reason, user.user_id)
    log_audit(db, user.user_id, "procedure.skip", "exe_procedure", procedure_id, {"reason": payload.reason})
    db.commit()
    return row


@router.post("/procedures/{procedure_id}/unskip", response_model=ExeProcOut)
def unskip_procedure(procedure_id: UUID, db: Session = Depends(get_db), user=Depends(paper_update)):
    authorize_assignment(db, user, "audit.paper.update", svc.get_procedure(db, procedure_id)["assignment_id"], ROLES_WORK)
    row = svc.set_procedure_skip(db, procedure_id, False, None, user.user_id)
    log_audit(db, user.user_id, "procedure.unskip", "exe_procedure", procedure_id)
    db.commit()
    return row


@router.post("/procedures/{procedure_id}/submit", response_model=ExeProcOut)
def submit_procedure(procedure_id: UUID, db: Session = Depends(get_db), user=Depends(paper_update)):
    authorize_assignment(db, user, "audit.paper.update", svc.get_procedure(db, procedure_id)["assignment_id"], ROLES_WORK)
    row = svc.submit_procedure(db, procedure_id, user.user_id)
    log_audit(db, user.user_id, "procedure.submit", "exe_procedure", procedure_id)
    db.commit()
    return row


@router.post("/procedures/{procedure_id}/skip-review", response_model=ExeProcOut)
def skip_review(procedure_id: UUID, payload: SkipIn, db: Session = Depends(get_db), user=Depends(paper_review)):
    authorize_assignment(db, user, "audit.paper.review", svc.get_procedure(db, procedure_id)["assignment_id"], ROLES_SUP)
    row = svc.skip_review(db, procedure_id, payload.reason, user.user_id)
    log_audit(db, user.user_id, "procedure.skip_review", "exe_procedure", procedure_id, {"reason": payload.reason})
    db.commit()
    return row


@router.post("/procedures/{procedure_id}/reopen-review", response_model=ExeProcOut)
def reopen_review(procedure_id: UUID, db: Session = Depends(get_db), user=Depends(paper_review)):
    authorize_assignment(db, user, "audit.paper.review", svc.get_procedure(db, procedure_id)["assignment_id"], ROLES_LEAD_SUP)
    row = svc.reopen_review(db, procedure_id, user.user_id)
    log_audit(db, user.user_id, "procedure.reopen_review", "exe_procedure", procedure_id)
    db.commit()
    return row


# --- Working papers ---

@router.get("/procedures/{procedure_id}/papers", response_model=List[PaperOut])
def list_papers(procedure_id: UUID, db: Session = Depends(get_db), user=Depends(paper_read)):
    authorize_view(db, user, "audit.paper.read", svc.get_procedure(db, procedure_id)["assignment_id"])
    return svc.list_papers(db, procedure_id)


@router.post("/procedures/{procedure_id}/papers", response_model=PaperOut, status_code=201)
def create_paper(procedure_id: UUID, payload: PaperCreate,
                 db: Session = Depends(get_db), user=Depends(paper_create)):
    authorize_assignment(db, user, "audit.paper.create", svc.get_procedure(db, procedure_id)["assignment_id"], ROLES_WORK)
    row = svc.create_paper(db, procedure_id, payload, user.user_id)
    log_audit(db, user.user_id, "paper.create", "working_paper", row["paper_id"], {"procedure_id": str(procedure_id)})
    db.commit()
    return row


@router.patch("/papers/{paper_id}", response_model=PaperOut)
def update_paper(paper_id: UUID, payload: PaperUpdate,
                 db: Session = Depends(get_db), user=Depends(paper_update)):
    authorize_assignment(db, user, "audit.paper.update", svc.get_paper(db, paper_id)["assignment_id"], ROLES_WORK)
    row = svc.update_paper(db, paper_id, payload, user.user_id)
    log_audit(db, user.user_id, "paper.update", "working_paper", paper_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row