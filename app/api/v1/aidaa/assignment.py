from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    assignment_read, assignment_create, assignment_update,
    check_org_permission, assert_org_access, get_resource_org_id,
    get_user_accessible_org_ids, log_audit,
)
from app.schemas.assignment import (
    AssignmentCreate, AssignmentUpdate, AssignmentCancel, AssignmentOut,
    AssignmentChangeIn, AssignmentChangeOut,
)
from app.api.dependencies import authorize_assignment, ROLES_LEAD
from app.services import assignments as svc
from app.services import assignment_changes as changes
from app.services.roles import my_assignment_role

router = APIRouter()


@router.get("", response_model=List[AssignmentOut])
def list_assignments(active_only: bool = True, status: Optional[str] = Query(None),
                     plan_id: Optional[UUID] = None, unplanned_only: bool = False,
                     search: Optional[str] = Query(None),
                     db: Session = Depends(get_db), user=Depends(assignment_read)):
    org_ids = get_user_accessible_org_ids(db, user.user_id, "audit.assignment.read")
    return svc.list_assignments(db, org_ids, active_only, status, plan_id, unplanned_only, search)


@router.post("", response_model=AssignmentOut, status_code=201)
def create_assignment(payload: AssignmentCreate, db: Session = Depends(get_db),
                      user=Depends(assignment_create)):
    org_id = get_resource_org_id(db, "plan", payload.plan_id) if payload.plan_id else payload.owner_org_id
    if org_id is None:
        raise HTTPException(status_code=400, detail="owner_org_id is required when plan_id is empty")
    assert_org_access(db, user, "audit.assignment.create", org_id)
    row = svc.create_assignment(db, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.create", "assignment", row["assignment_id"],
              {"assignment_no": row["assignment_no"], "unplanned": row["is_unplanned"]})
    db.commit()
    return row


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_read)):
    row = svc.get_assignment(db, assignment_id)
    svc.assert_read_access(get_user_accessible_org_ids(db, user.user_id, "audit.assignment.read"), row)
    row["my_role"] = my_assignment_role(db, user.user_id, assignment_id)
    return row


@router.patch("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(assignment_id: UUID, payload: AssignmentUpdate,
                      db: Session = Depends(get_db), user=Depends(assignment_update)):
    check_org_permission(db, user, "audit.assignment.update", "assignment", assignment_id)
    row = svc.update_assignment(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.update", "assignment", assignment_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/{assignment_id}/issue", response_model=AssignmentOut)
def issue_assignment(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_create)):
    check_org_permission(db, user, "audit.assignment.create", "assignment", assignment_id)
    row = svc.issue_assignment(db, assignment_id, user.user_id)
    log_audit(db, user.user_id, "assignment.issue", "assignment", assignment_id)
    db.commit()
    return row


@router.post("/{assignment_id}/cancel", response_model=AssignmentOut)
def cancel_assignment(assignment_id: UUID, payload: AssignmentCancel,
                      db: Session = Depends(get_db), user=Depends(assignment_update)):
    check_org_permission(db, user, "audit.assignment.update", "assignment", assignment_id)
    row = svc.cancel_assignment(db, assignment_id, payload.reason, user.user_id)
    log_audit(db, user.user_id, "assignment.cancel", "assignment", assignment_id, {"reason": payload.reason})
    db.commit()
    return row


# --- Post-issue change requests (seeded step record_type 'assignment_change') ---

@router.get("/change-requests/{change_id}", response_model=AssignmentChangeOut)
def get_change_request(change_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_read)):
    row = changes.get_change(db, change_id)
    asg = svc.get_assignment(db, row["assignment_id"])
    svc.assert_read_access(get_user_accessible_org_ids(db, user.user_id, "audit.assignment.read"), asg)
    from app.services.roles import assert_assignment_visible
    assert_assignment_visible(db, user.user_id, row["assignment_id"])
    return row


@router.get("/{assignment_id}/change-requests", response_model=List[AssignmentChangeOut])
def list_change_requests(assignment_id: UUID, db: Session = Depends(get_db),
                         user=Depends(assignment_read)):
    from app.services.roles import assert_assignment_visible
    row = svc.get_assignment(db, assignment_id)
    svc.assert_read_access(get_user_accessible_org_ids(db, user.user_id, "audit.assignment.read"), row)
    assert_assignment_visible(db, user.user_id, assignment_id)
    return changes.list_changes(db, assignment_id)


@router.post("/{assignment_id}/change-requests", response_model=AssignmentChangeOut, status_code=201)
def create_change_request(assignment_id: UUID, payload: AssignmentChangeIn,
                          db: Session = Depends(get_db), user=Depends(assignment_update)):
    authorize_assignment(db, user, "audit.assignment.update", assignment_id, ROLES_LEAD)
    row = changes.create_change(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.change_request", "assignment_change", row["change_id"],
              {"assignment_id": str(assignment_id), "reason": row["reason"],
               "fields": sorted(row["payload"].keys())})
    db.commit()
    return row


@router.post("/{assignment_id}/change-requests/{change_id}/cancel", response_model=AssignmentChangeOut)
def cancel_change_request(assignment_id: UUID, change_id: UUID, db: Session = Depends(get_db),
                          user=Depends(assignment_update)):
    check_org_permission(db, user, "audit.assignment.update", "assignment", assignment_id)
    row = changes.cancel_change(db, change_id, user.user_id)
    if row["assignment_id"] != assignment_id:
        raise HTTPException(status_code=404, detail="Change request not found on this assignment")
    log_audit(db, user.user_id, "assignment.change_cancel", "assignment_change", change_id)
    db.commit()
    return row