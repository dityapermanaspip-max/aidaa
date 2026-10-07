from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    assignment_read, logistics_write, check_org_permission, check_org_any_permission, log_audit,
)
from app.schemas.trip import (
    ReasonIn, VisitCreate, VisitUpdate, VisitOut, LegCreate, LegUpdate, LegOut,
)
from app.services import trip as svc
from app.services import budgets
from app.services.roles import assert_assignment_visible

router = APIRouter()
_WRITE = ("audit.assignment.update", "audit.assignment.logistics")


def _can_write(db: Session, user, assignment_id: UUID):
    check_org_any_permission(db, user, _WRITE, "assignment", assignment_id)


# --- Visits ---

@router.get("/{assignment_id}/visits", response_model=List[VisitOut])
def list_visits(assignment_id: UUID, status: Optional[str] = Query(None),
                db: Session = Depends(get_db), user=Depends(assignment_read)):
    check_org_permission(db, user, "audit.assignment.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)
    return svc.list_visits(db, assignment_id, status)


@router.post("/{assignment_id}/visits", response_model=VisitOut, status_code=201)
def create_visit(assignment_id: UUID, payload: VisitCreate,
                 db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.create_visit(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "visit.create", "assignment_visit", row["visit_id"],
              {"assignment_id": str(assignment_id)})
    db.commit()
    return row


@router.patch("/visits/{visit_id}", response_model=VisitOut)
def update_visit(visit_id: UUID, payload: VisitUpdate,
                 db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_visit(db, visit_id)["assignment_id"])
    row = svc.update_visit(db, visit_id, payload, user.user_id)
    log_audit(db, user.user_id, "visit.update", "assignment_visit", visit_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/visits/{visit_id}/confirm", response_model=VisitOut)
def confirm_visit(visit_id: UUID, db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_visit(db, visit_id)["assignment_id"])
    row = svc.confirm_visit(db, visit_id, user.user_id)
    log_audit(db, user.user_id, "visit.confirm", "assignment_visit", visit_id)
    db.commit()
    return row


@router.post("/visits/{visit_id}/cancel", response_model=VisitOut)
def cancel_visit(visit_id: UUID, payload: ReasonIn,
                 db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_visit(db, visit_id)["assignment_id"])
    row = svc.cancel_visit(db, visit_id, payload.reason, user.user_id)
    log_audit(db, user.user_id, "visit.cancel", "assignment_visit", visit_id, {"reason": payload.reason})
    db.commit()
    return row


# --- Trip legs ---

@router.get("/{assignment_id}/legs", response_model=List[LegOut])
def list_legs(assignment_id: UUID, auditor_id: Optional[UUID] = None,
              db: Session = Depends(get_db), user=Depends(assignment_read)):
    check_org_permission(db, user, "audit.assignment.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)
    return svc.list_legs(db, assignment_id, auditor_id)


@router.post("/{assignment_id}/legs", response_model=LegOut, status_code=201)
def create_leg(assignment_id: UUID, payload: LegCreate,
               db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.create_leg(db, assignment_id, payload, user.user_id)
    budgets.sync_leg_line(db, row["leg_id"], user.user_id, payload.component_id)
    log_audit(db, user.user_id, "leg.create", "assignment_trip_leg", row["leg_id"],
              {"assignment_id": str(assignment_id), "auditor_id": str(payload.auditor_id)})
    db.commit()
    return svc.get_leg(db, row["leg_id"])


@router.patch("/legs/{leg_id}", response_model=LegOut)
def update_leg(leg_id: UUID, payload: LegUpdate,
               db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_leg(db, leg_id)["assignment_id"])
    svc.update_leg(db, leg_id, payload, user.user_id)
    budgets.sync_leg_line(db, leg_id, user.user_id, payload.component_id)
    log_audit(db, user.user_id, "leg.update", "assignment_trip_leg", leg_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return svc.get_leg(db, leg_id)


@router.post("/legs/{leg_id}/confirm", response_model=LegOut)
def confirm_leg(leg_id: UUID, db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_leg(db, leg_id)["assignment_id"])
    row = svc.confirm_leg(db, leg_id, user.user_id)
    budgets.sync_leg_line(db, leg_id, user.user_id)
    log_audit(db, user.user_id, "leg.confirm", "assignment_trip_leg", leg_id)
    db.commit()
    return row


@router.post("/legs/{leg_id}/cancel", response_model=LegOut)
def cancel_leg(leg_id: UUID, payload: ReasonIn,
               db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, svc.get_leg(db, leg_id)["assignment_id"])
    row = svc.cancel_leg(db, leg_id, payload.reason, user.user_id)
    budgets.sync_leg_line(db, leg_id, user.user_id)
    log_audit(db, user.user_id, "leg.cancel", "assignment_trip_leg", leg_id, {"reason": payload.reason})
    db.commit()
    return row