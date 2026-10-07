from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    report_read, report_create, report_update, report_approve, check_org_permission,
    authorize_assignment, authorize_view, log_audit, ROLES_LEAD,
)
from app.schemas.execution import ReportCreate, ReportUpdate, ReportOut, ReportDetail
from app.services import execution_flow as svc

router = APIRouter()


@router.get("/assignment/{assignment_id}/reports", response_model=List[ReportOut])
def list_reports(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(report_read)):
    mode = authorize_view(db, user, "audit.report.read", assignment_id)
    return svc.list_reports(db, assignment_id, mode == "pic")


@router.post("/assignment/{assignment_id}/reports", response_model=ReportOut, status_code=201)
def create_report(assignment_id: UUID, payload: ReportCreate,
                  db: Session = Depends(get_db), user=Depends(report_create)):
    authorize_assignment(db, user, "audit.report.create", assignment_id, ROLES_LEAD)
    row = svc.create_report(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "report.create", "audit_report", row["report_id"], {"assignment_id": str(assignment_id)})
    db.commit()
    return row


@router.get("/reports/{report_id}", response_model=ReportDetail)
def get_report(report_id: UUID, db: Session = Depends(get_db), user=Depends(report_read)):
    mode = authorize_view(db, user, "audit.report.read", svc.get_report(db, report_id)["assignment_id"])
    return svc.get_report_detail(db, report_id, mode == "pic")


@router.patch("/reports/{report_id}", response_model=ReportOut)
def update_report(report_id: UUID, payload: ReportUpdate,
                  db: Session = Depends(get_db), user=Depends(report_update)):
    authorize_assignment(db, user, "audit.report.update", svc.get_report(db, report_id)["assignment_id"], ROLES_LEAD)
    row = svc.update_report(db, report_id, payload, user.user_id)
    log_audit(db, user.user_id, "report.update", "audit_report", report_id, payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/reports/{report_id}/submit", response_model=ReportOut)
def submit_report(report_id: UUID, db: Session = Depends(get_db), user=Depends(report_update)):
    authorize_assignment(db, user, "audit.report.update", svc.get_report(db, report_id)["assignment_id"], ROLES_LEAD)
    row = svc.submit_report(db, report_id, user.user_id)
    log_audit(db, user.user_id, "report.submit", "audit_report", report_id)
    db.commit()
    return row


@router.post("/reports/{report_id}/finalize", response_model=ReportOut)
def finalize_report(report_id: UUID, db: Session = Depends(get_db), user=Depends(report_approve)):
    check_org_permission(db, user, "audit.report.approve", "assignment", svc.get_report(db, report_id)["assignment_id"])
    row = svc.finalize_report(db, report_id, user.user_id)
    log_audit(db, user.user_id, "report.finalize", "audit_report", report_id)
    db.commit()
    return row