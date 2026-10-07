from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    plan_read, plan_create, plan_update, team_manage,
    check_org_permission, assert_org_access, get_user_accessible_org_ids, log_audit,
)
from app.schemas.aidaa import (
    PlanCreate, PlanUpdate, PlanOut,
    PlanMemberCreate, PlanMemberUpdate, PlanMemberOut,
)
from app.services import plans as svc

router = APIRouter()


@router.get("", response_model=List[PlanOut])
def list_plans(active_only: bool = True, fiscal_year: Optional[int] = None,
               status: Optional[str] = Query(None), search: Optional[str] = Query(None),
               db: Session = Depends(get_db), user=Depends(plan_read)):
    org_ids = get_user_accessible_org_ids(db, user.user_id, "audit.plan.read")
    return svc.list_plans(db, org_ids, active_only, fiscal_year, status, search)


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), user=Depends(plan_create)):
    assert_org_access(db, user, "audit.plan.create", payload.owner_org_id)
    row = svc.create_plan(db, payload, user.user_id)
    log_audit(db, user.user_id, "plan.create", "audit_plan", row["plan_id"], {"plan_no": row["plan_no"]})
    db.commit()
    return row


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: UUID, db: Session = Depends(get_db), user=Depends(plan_read)):
    check_org_permission(db, user, "audit.plan.read", "plan", plan_id)
    return svc.get_plan(db, plan_id)


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: UUID, payload: PlanUpdate,
                db: Session = Depends(get_db), user=Depends(plan_update)):
    check_org_permission(db, user, "audit.plan.update", "plan", plan_id)
    row = svc.update_plan(db, plan_id, payload, user.user_id)
    log_audit(db, user.user_id, "plan.update", "audit_plan", plan_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/{plan_id}", response_model=PlanOut)
def deactivate_plan(plan_id: UUID, db: Session = Depends(get_db), user=Depends(plan_update)):
    check_org_permission(db, user, "audit.plan.update", "plan", plan_id)
    row = svc.deactivate_plan(db, plan_id, user.user_id)
    log_audit(db, user.user_id, "plan.deactivate", "audit_plan", plan_id)
    db.commit()
    return row


# --- Plan members ---

@router.get("/{plan_id}/members", response_model=List[PlanMemberOut])
def list_members(plan_id: UUID, db: Session = Depends(get_db), user=Depends(plan_read)):
    check_org_permission(db, user, "audit.plan.read", "plan", plan_id)
    return svc.list_members(db, plan_id)


@router.post("/{plan_id}/members", response_model=PlanMemberOut, status_code=201)
def add_member(plan_id: UUID, payload: PlanMemberCreate,
               db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "plan", plan_id)
    row = svc.add_member(db, plan_id, payload, user.user_id)
    log_audit(db, user.user_id, "plan.member_add", "audit_plan", plan_id,
              {"auditor_id": str(payload.auditor_id), "role": payload.assignment_role})
    db.commit()
    return row


@router.patch("/{plan_id}/members/{plan_member_id}", response_model=PlanMemberOut)
def update_member(plan_id: UUID, plan_member_id: UUID, payload: PlanMemberUpdate,
                  db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "plan", plan_id)
    row = svc.update_member(db, plan_id, plan_member_id, payload, user.user_id)
    log_audit(db, user.user_id, "plan.member_update", "audit_plan", plan_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/{plan_id}/members/{plan_member_id}", status_code=204)
def remove_member(plan_id: UUID, plan_member_id: UUID,
                  db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "plan", plan_id)
    svc.remove_member(db, plan_id, plan_member_id, user.user_id)
    log_audit(db, user.user_id, "plan.member_remove", "audit_plan", plan_id,
              {"plan_member_id": str(plan_member_id)})
    db.commit()