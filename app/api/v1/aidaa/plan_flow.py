from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import plan_read, plan_update, check_org_permission, log_audit
from app.schemas.plan_flow import PlanSubmit, PlanVersionOut, PlanVersionDetail
from app.services import plan_flow as svc

router = APIRouter()


@router.post("/{plan_id}/submit", response_model=PlanVersionOut, status_code=201)
def submit_plan(plan_id: UUID, payload: Optional[PlanSubmit] = None,
                db: Session = Depends(get_db), user=Depends(plan_update)):
    check_org_permission(db, user, "audit.plan.update", "plan", plan_id)
    row = svc.submit_plan(db, plan_id, payload or PlanSubmit(), user.user_id)
    log_audit(db, user.user_id, "plan.submit", "audit_plan", plan_id,
              {"version_no": row["version_no"], "total_amount": float(row["total_amount"])})
    db.commit()
    return row


@router.get("/{plan_id}/versions", response_model=List[PlanVersionOut])
def list_versions(plan_id: UUID, db: Session = Depends(get_db), user=Depends(plan_read)):
    check_org_permission(db, user, "audit.plan.read", "plan", plan_id)
    return svc.list_versions(db, plan_id)


@router.get("/versions/{version_id}", response_model=PlanVersionDetail)
def get_version(version_id: UUID, db: Session = Depends(get_db), user=Depends(plan_read)):
    row = svc.get_version(db, version_id)
    check_org_permission(db, user, "audit.plan.read", "plan", row["plan_id"])
    return row