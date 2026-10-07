from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    finding_read, finding_create, finding_update, finding_approve, finding_communicate,
    finding_respond, rekomend_read, rekomend_create, rekomend_update, rekomend_close,
    rekomend_followup, authorize_assignment, authorize_view, authorize_pic, log_audit,
    ROLES_WORK, ROLES_SUP, ROLES_LEAD_SUP,
)
from app.schemas.execution import (
    FindingCreate, FindingUpdate, FindingOut, CommunicateIn, ExtendDueIn, ResponseCreate,
    ResponseOut, NoteIn, RekCreate, RekUpdate, RekFollowupIn, RekOut,
)
from app.services import execution_flow as svc

router = APIRouter()
_PIC_OK = ("communicated", "responded", "open", "closed")


def _visible(mode: str, finding: dict):
    if mode == "pic" and finding["status"] not in _PIC_OK:
        raise HTTPException(status_code=404, detail="Finding not found")


# --- Findings ---

@router.get("/assignment/{assignment_id}/findings", response_model=List[FindingOut])
def list_findings(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    mode = authorize_view(db, user, "audit.finding.read", assignment_id)
    return svc.list_findings(db, assignment_id, mode == "pic")


@router.post("/assignment/{assignment_id}/findings", response_model=FindingOut, status_code=201)
def create_finding(assignment_id: UUID, payload: FindingCreate,
                   db: Session = Depends(get_db), user=Depends(finding_create)):
    authorize_assignment(db, user, "audit.finding.create", assignment_id, ROLES_WORK)
    row = svc.create_finding(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "finding.create", "finding", row["finding_id"], {"finding_no": row["finding_no"]})
    db.commit()
    return row


@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    row = svc.get_finding(db, finding_id)
    _visible(authorize_view(db, user, "audit.finding.read", row["assignment_id"]), row)
    return row


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def update_finding(finding_id: UUID, payload: FindingUpdate,
                   db: Session = Depends(get_db), user=Depends(finding_update)):
    authorize_assignment(db, user, "audit.finding.update", svc.get_finding(db, finding_id)["assignment_id"], ROLES_WORK)
    row = svc.update_finding(db, finding_id, payload, user.user_id)
    log_audit(db, user.user_id, "finding.update", "finding", finding_id, payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/findings/{finding_id}/submit", response_model=FindingOut)
def submit_finding(finding_id: UUID, db: Session = Depends(get_db), user=Depends(finding_update)):
    authorize_assignment(db, user, "audit.finding.update", svc.get_finding(db, finding_id)["assignment_id"], ROLES_WORK)
    row = svc.submit_finding(db, finding_id, user.user_id)
    log_audit(db, user.user_id, "finding.submit", "finding", finding_id)
    db.commit()
    return row


@router.post("/findings/{finding_id}/communicate", response_model=FindingOut)
def communicate_finding(finding_id: UUID, payload: CommunicateIn,
                        db: Session = Depends(get_db), user=Depends(finding_communicate)):
    authorize_assignment(db, user, "audit.finding.communicate", svc.get_finding(db, finding_id)["assignment_id"], ROLES_LEAD_SUP)
    row = svc.communicate_finding(db, finding_id, payload, user.user_id)
    log_audit(db, user.user_id, "finding.communicate", "finding", finding_id,
              {"response_due_date": str(payload.response_due_date)})
    db.commit()
    return row


@router.post("/findings/{finding_id}/extend-due", response_model=FindingOut)
def extend_due(finding_id: UUID, payload: ExtendDueIn,
               db: Session = Depends(get_db), user=Depends(finding_communicate)):
    authorize_assignment(db, user, "audit.finding.communicate", svc.get_finding(db, finding_id)["assignment_id"], ROLES_LEAD_SUP)
    row = svc.extend_due(db, finding_id, payload.new_due_date, payload.reason, user.user_id)
    log_audit(db, user.user_id, "finding.extend_due", "finding", finding_id,
              {"new_due_date": str(payload.new_due_date), "reason": payload.reason})
    db.commit()
    return row


@router.post("/findings/{finding_id}/respond", response_model=ResponseOut, status_code=201)
def respond_finding(finding_id: UUID, payload: ResponseCreate,
                    db: Session = Depends(get_db), user=Depends(finding_respond)):
    authorize_pic(db, user, "audit.finding.respond", svc.get_finding(db, finding_id)["assignment_id"])
    row = svc.respond_finding(db, finding_id, payload, user.user_id)
    log_audit(db, user.user_id, "finding.respond", "finding", finding_id, {"stance": payload.stance})
    db.commit()
    return row


@router.post("/findings/{finding_id}/resolve", response_model=FindingOut)
def resolve_finding(finding_id: UUID, payload: NoteIn,
                    db: Session = Depends(get_db), user=Depends(finding_approve)):
    authorize_assignment(db, user, "audit.finding.approve", svc.get_finding(db, finding_id)["assignment_id"], ROLES_SUP)
    row = svc.resolve_finding(db, finding_id, payload.note, user.user_id)
    log_audit(db, user.user_id, "finding.resolve", "finding", finding_id, {"note": payload.note})
    db.commit()
    return row


@router.get("/findings/{finding_id}/responses", response_model=List[ResponseOut])
def list_responses(finding_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    row = svc.get_finding(db, finding_id)
    _visible(authorize_view(db, user, "audit.finding.read", row["assignment_id"]), row)
    return svc.list_responses(db, finding_id)


# --- Recommendations ---

@router.get("/findings/{finding_id}/rekomend", response_model=List[RekOut])
def list_rekomend(finding_id: UUID, db: Session = Depends(get_db), user=Depends(rekomend_read)):
    row = svc.get_finding(db, finding_id)
    _visible(authorize_view(db, user, "audit.rekomend.read", row["assignment_id"]), row)
    return svc.list_rekomend(db, finding_id)


@router.post("/findings/{finding_id}/rekomend", response_model=RekOut, status_code=201)
def create_rekomend(finding_id: UUID, payload: RekCreate,
                    db: Session = Depends(get_db), user=Depends(rekomend_create)):
    authorize_assignment(db, user, "audit.rekomend.create", svc.get_finding(db, finding_id)["assignment_id"], ROLES_WORK)
    row = svc.create_rekomend(db, finding_id, payload, user.user_id)
    log_audit(db, user.user_id, "rekomend.create", "rekomend", row["rekomend_id"], {"finding_id": str(finding_id)})
    db.commit()
    return row


@router.patch("/rekomend/{rekomend_id}", response_model=RekOut)
def update_rekomend(rekomend_id: UUID, payload: RekUpdate,
                    db: Session = Depends(get_db), user=Depends(rekomend_update)):
    authorize_assignment(db, user, "audit.rekomend.update", svc.get_rekomend(db, rekomend_id)["assignment_id"], ROLES_WORK)
    row = svc.update_rekomend(db, rekomend_id, payload, user.user_id)
    log_audit(db, user.user_id, "rekomend.update", "rekomend", rekomend_id, payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/rekomend/{rekomend_id}/followup", response_model=RekOut)
def followup_rekomend(rekomend_id: UUID, payload: RekFollowupIn,
                      db: Session = Depends(get_db), user=Depends(rekomend_followup)):
    authorize_pic(db, user, "audit.rekomend.followup", svc.get_rekomend(db, rekomend_id)["assignment_id"])
    row = svc.followup_rekomend(db, rekomend_id, payload, user.user_id)
    log_audit(db, user.user_id, "rekomend.followup", "rekomend", rekomend_id)
    db.commit()
    return row


@router.post("/rekomend/{rekomend_id}/close", response_model=RekOut)
def close_rekomend(rekomend_id: UUID, db: Session = Depends(get_db), user=Depends(rekomend_close)):
    authorize_assignment(db, user, "audit.rekomend.close", svc.get_rekomend(db, rekomend_id)["assignment_id"], ROLES_SUP)
    row = svc.close_rekomend(db, rekomend_id, user.user_id)
    log_audit(db, user.user_id, "rekomend.close", "rekomend", rekomend_id)
    db.commit()
    return row


@router.post("/rekomend/{rekomend_id}/monitor", response_model=RekOut)
def monitor_rekomend(rekomend_id: UUID, db: Session = Depends(get_db), user=Depends(rekomend_update)):
    authorize_assignment(db, user, "audit.rekomend.update", svc.get_rekomend(db, rekomend_id)["assignment_id"], ROLES_LEAD_SUP)
    row = svc.monitor_rekomend(db, rekomend_id, user.user_id)
    log_audit(db, user.user_id, "rekomend.monitor", "rekomend", rekomend_id)
    db.commit()
    return row