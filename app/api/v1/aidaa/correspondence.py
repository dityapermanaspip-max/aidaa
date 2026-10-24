"""Korespondensi routes (batch 06): document requests, interview schedules, berita acara notisi.

Reuses permission codes only (IAM cannot be seeded from here): doc-req manage = audit.assignment.update,
PIC submit = audit.finding.respond + authorize_pic, interviews = the logistics wrapper (update OR
logistics), BAP writes = audit.finding.communicate (lead/supervisor), all reads = authorize_view with
audit.finding.read through authorize_view, with PIC lists org-filtered by their unit orgs. BAP routes
skip assignment-status checks on purpose (post-audit correspondence).
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    finding_read, finding_respond, finding_communicate, assignment_update,
    logistics_write, authorize_assignment, authorize_view, authorize_pic,
    check_org_any_permission, log_audit, ROLES_WORK, ROLES_LEAD_SUP,
)
from app.services.roles import is_auditee_pic, my_assignment_role, assignment_scope, pic_unit_orgs
from app.schemas.execution import (
    BapCreate, BapItemOut, BapOut, BapResultIn, BapUpdate, CancelIn, DocReqCreate, DocReqOut,
    DocReqSubmitIn, DocReqUpdate, DocReqVerifyIn, InterviewCreate, InterviewOut,
    InterviewResultIn, InterviewUpdate,
)
from app.services.execution import correspondence as svc

router = APIRouter()
_LOG_WRITE = ("audit.assignment.update", "audit.assignment.logistics")


def _can_write(db: Session, user, assignment_id: UUID):
    """Interviews: the audit team with either org permission (same rule as visits and trip legs)."""
    check_org_any_permission(db, user, _LOG_WRITE, "assignment", assignment_id)
    role = my_assignment_role(db, user.user_id, assignment_id)
    if role not in ROLES_WORK:
        raise HTTPException(status_code=403,
                            detail=f"Assignment role {list(ROLES_WORK)} required, yours is {role or 'none (not on the team)'}")


def _pic_orgs(db: Session, user, assignment_id: UUID):
    """The audited unit orgs where this caller is the auditee PIC; used to filter their lists."""
    return pic_unit_orgs(db, user.user_id, assignment_scope(db, assignment_id)["unit_org_ids"])


# --- A: permintaan dokumen awal ---

@router.get("/assignment/{assignment_id}/doc-req", response_model=List[DocReqOut])
def list_doc_req(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    mode = authorize_view(db, user, "audit.finding.read", assignment_id)
    pic_orgs = _pic_orgs(db, user, assignment_id) if mode == "pic" else None
    return svc.list_doc_reqs(db, assignment_id, pic_orgs)


@router.post("/assignment/{assignment_id}/doc-req", response_model=DocReqOut, status_code=201)
def create_doc_req(assignment_id: UUID, payload: DocReqCreate,
                   db: Session = Depends(get_db), user=Depends(assignment_update)):
    authorize_assignment(db, user, "audit.assignment.update", assignment_id, ROLES_WORK)
    row = svc.create_doc_req(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "docreq.create", "doc_req", row["doc_req_id"],
              {"assignment_id": str(assignment_id), "unit_id": str(payload.unit_id)})
    db.commit()
    return row


@router.patch("/doc-req/{doc_req_id}", response_model=DocReqOut)
def update_doc_req(doc_req_id: UUID, payload: DocReqUpdate,
                   db: Session = Depends(get_db), user=Depends(assignment_update)):
    authorize_assignment(db, user, "audit.assignment.update",
                         svc.get_doc_req(db, doc_req_id)["assignment_id"], ROLES_WORK)
    row = svc.update_doc_req(db, doc_req_id, payload, user.user_id)
    log_audit(db, user.user_id, "docreq.update", "doc_req", doc_req_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/doc-req/{doc_req_id}/submit", response_model=DocReqOut)
def submit_doc_req(doc_req_id: UUID, payload: DocReqSubmitIn,
                   db: Session = Depends(get_db), user=Depends(finding_respond)):
    d = svc.get_doc_req(db, doc_req_id)
    authorize_pic(db, user, "audit.finding.respond", d["assignment_id"])
    if not is_auditee_pic(db, user.user_id, d["unit_org_id"]):
        raise HTTPException(status_code=403, detail="The document request belongs to another audited unit")
    row = svc.submit_doc_req(db, doc_req_id, payload, user.user_id)
    log_audit(db, user.user_id, "docreq.submit", "doc_req", doc_req_id)
    db.commit()
    return row


@router.post("/doc-req/{doc_req_id}/verify", response_model=DocReqOut)
def verify_doc_req(doc_req_id: UUID, payload: DocReqVerifyIn,
                   db: Session = Depends(get_db), user=Depends(assignment_update)):
    authorize_assignment(db, user, "audit.assignment.update",
                         svc.get_doc_req(db, doc_req_id)["assignment_id"], ROLES_WORK)
    row = svc.verify_doc_req(db, doc_req_id, payload.verify_note, user.user_id)
    log_audit(db, user.user_id, "docreq.verify", "doc_req", doc_req_id)
    db.commit()
    return row


# --- C: jadwal wawancara ---

@router.get("/assignment/{assignment_id}/interviews", response_model=List[InterviewOut])
def list_interviews(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    mode = authorize_view(db, user, "audit.finding.read", assignment_id)
    pic_orgs = _pic_orgs(db, user, assignment_id) if mode == "pic" else None
    return svc.list_interviews(db, assignment_id, pic_orgs)


@router.post("/assignment/{assignment_id}/interviews", response_model=InterviewOut, status_code=201)
def create_interview(assignment_id: UUID, payload: InterviewCreate,
                     db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.create_interview(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "interview.create", "interview", row["interview_id"],
              {"assignment_id": str(assignment_id), "unit_id": str(payload.unit_id)})
    db.commit()
    return row


@router.patch("/interview/{interview_id}", response_model=InterviewOut)
def update_interview(interview_id: UUID, payload: InterviewUpdate,
                     db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_interview(db, interview_id)["assignment_id"])
    row = svc.update_interview(db, interview_id, payload, user.user_id)
    log_audit(db, user.user_id, "interview.update", "interview", interview_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/interview/{interview_id}/hold", response_model=InterviewOut)
def hold_interview(interview_id: UUID, db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_interview(db, interview_id)["assignment_id"])
    row = svc.hold_interview(db, interview_id, user.user_id)
    log_audit(db, user.user_id, "interview.hold", "interview", interview_id)
    db.commit()
    return row


@router.post("/interview/{interview_id}/done", response_model=InterviewOut)
def done_interview(interview_id: UUID, payload: InterviewResultIn,
                   db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_interview(db, interview_id)["assignment_id"])
    row = svc.done_interview(db, interview_id, payload.result, user.user_id)
    log_audit(db, user.user_id, "interview.done", "interview", interview_id)
    db.commit()
    return row


@router.post("/interview/{interview_id}/cancel", response_model=InterviewOut)
def cancel_interview(interview_id: UUID, payload: CancelIn,
                     db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_interview(db, interview_id)["assignment_id"])
    row = svc.cancel_interview(db, interview_id, payload.reason, user.user_id)
    log_audit(db, user.user_id, "interview.cancel", "interview", interview_id, {"reason": payload.reason})
    db.commit()
    return row


# --- D: berita acara penyampaian notisi ---

@router.get("/assignment/{assignment_id}/baps", response_model=List[BapItemOut])
def list_baps(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(finding_read)):
    authorize_view(db, user, "audit.finding.read", assignment_id)
    return svc.list_baps(db, assignment_id)


@router.post("/findings/{finding_id}/bap", response_model=BapOut, status_code=201)
def create_bap(finding_id: UUID, payload: BapCreate,
               db: Session = Depends(get_db), user=Depends(finding_communicate)):
    authorize_assignment(db, user, "audit.finding.communicate",
                         svc.get_finding(db, finding_id)["assignment_id"], ROLES_LEAD_SUP)
    row = svc.create_bap(db, finding_id, payload, user.user_id)
    log_audit(db, user.user_id, "bap.create", "finding_bap", row["bap_id"],
              {"finding_id": str(finding_id), "bap_no": payload.bap_no})
    db.commit()
    return row


@router.patch("/bap/{bap_id}", response_model=BapOut)
def update_bap(bap_id: UUID, payload: BapUpdate,
               db: Session = Depends(get_db), user=Depends(finding_communicate)):
    authorize_assignment(db, user, "audit.finding.communicate",
                         svc.get_bap(db, bap_id)["assignment_id"], ROLES_LEAD_SUP)
    row = svc.update_bap(db, bap_id, payload, user.user_id)
    log_audit(db, user.user_id, "bap.update", "finding_bap", bap_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/bap/{bap_id}/result", response_model=BapOut)
def record_bap_result(bap_id: UUID, payload: BapResultIn,
                      db: Session = Depends(get_db), user=Depends(finding_communicate)):
    authorize_assignment(db, user, "audit.finding.communicate",
                         svc.get_bap(db, bap_id)["assignment_id"], ROLES_LEAD_SUP)
    row = svc.record_bap_result(db, bap_id, payload, user.user_id)
    log_audit(db, user.user_id, "bap.result", "finding_bap", bap_id,
              {"stance_result": payload.stance_result, "finding_id": str(row["finding_id"])})
    db.commit()
    return row
