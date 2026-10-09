from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    assignment_read, logistics_write, check_org_permission, check_org_any_permission, log_audit,
)
from app.schemas.realisation import (
    AdvanceCreate, AdvanceUpdate, AdvanceOut,
    CostCreate, CostUpdate, CostOut,
    BalanceOut, VarianceOut,
    SettlementCreate, SettlementOut,
)
from app.services import realisation as svc
from app.services.roles import assert_assignment_visible

router = APIRouter()
_WRITE = ("audit.assignment.update", "audit.assignment.logistics")


def _can_write(db: Session, user, assignment_id: UUID):
    check_org_any_permission(db, user, _WRITE, "assignment", assignment_id)


def _resolved(db: Session, user, assignment_id: UUID) -> None:
    check_org_permission(db, user, "audit.assignment.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)


# --- Advances (uang muka) ---

@router.get("/{assignment_id}/realisation/advances", response_model=List[AdvanceOut])
def list_advances(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_read)):
    _resolved(db, user, assignment_id)
    return svc.list_advances(db, assignment_id)


@router.post("/{assignment_id}/realisation/advances", response_model=AdvanceOut, status_code=201)
def create_advance(assignment_id: UUID, payload: AdvanceCreate,
                   db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.create_advance(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "realisation.advance.create", "realisation_advance", row["advance_id"],
              {"assignment_id": str(assignment_id), "amount": payload.amount})
    db.commit()
    return row


@router.patch("/{assignment_id}/realisation/advances/{advance_id}", response_model=AdvanceOut)
def update_advance(assignment_id: UUID, advance_id: UUID, payload: AdvanceUpdate,
                   db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.update_advance(db, advance_id, payload, user.user_id)
    log_audit(db, user.user_id, "realisation.advance.update", "realisation_advance", advance_id,
              {"assignment_id": str(assignment_id)})
    db.commit()
    return row


@router.delete("/{assignment_id}/realisation/advances/{advance_id}")
def delete_advance(assignment_id: UUID, advance_id: UUID,
                   db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.delete_advance(db, advance_id, user.user_id)
    log_audit(db, user.user_id, "realisation.advance.delete", "realisation_advance", advance_id,
              {"assignment_id": str(assignment_id)})
    db.commit()
    return row


# --- Real costs (pertanggungjawaban) ---

@router.get("/{assignment_id}/realisation/costs", response_model=List[CostOut])
def list_costs(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_read)):
    _resolved(db, user, assignment_id)
    return svc.list_costs(db, assignment_id)


@router.post("/{assignment_id}/realisation/costs", response_model=CostOut, status_code=201)
def create_cost(assignment_id: UUID, payload: CostCreate,
                db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.create_cost(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "realisation.cost.create", "realisation_cost", row["rc_id"],
              {"assignment_id": str(assignment_id), "amount": round(payload.unit_rate * payload.quantity, 2)})
    db.commit()
    return row


@router.patch("/{assignment_id}/realisation/costs/{rc_id}", response_model=CostOut)
def update_cost(assignment_id: UUID, rc_id: UUID, payload: CostUpdate,
                db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.update_cost(db, rc_id, payload, user.user_id)
    log_audit(db, user.user_id, "realisation.cost.update", "realisation_cost", rc_id,
              {"assignment_id": str(assignment_id)})
    db.commit()
    return row


@router.delete("/{assignment_id}/realisation/costs/{rc_id}")
def delete_cost(assignment_id: UUID, rc_id: UUID,
                db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.delete_cost(db, rc_id, user.user_id)
    log_audit(db, user.user_id, "realisation.cost.delete", "realisation_cost", rc_id,
              {"assignment_id": str(assignment_id)})
    db.commit()
    return row


# --- Reports (read only, amounts computed in SQL) ---

@router.get("/{assignment_id}/realisation/balance", response_model=BalanceOut)
def balance(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_read)):
    _resolved(db, user, assignment_id)
    return svc.balance_out(db, assignment_id)


@router.get("/{assignment_id}/realisation/variance", response_model=VarianceOut)
def variance(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_read)):
    _resolved(db, user, assignment_id)
    return svc.variance_out(db, assignment_id)


# --- Settlements (per-auditor, approved by Finance via the generic approval engine) ---

@router.get("/{assignment_id}/realisation/settlements", response_model=List[SettlementOut])
def list_settlements(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(assignment_read)):
    _resolved(db, user, assignment_id)
    return svc.list_settlements(db, assignment_id)


@router.post("/{assignment_id}/realisation/settlements", response_model=SettlementOut, status_code=201)
def submit_settlement(assignment_id: UUID, payload: SettlementCreate,
                      db: Session = Depends(get_db), user=Depends(logistics_write)):
    _can_write(db, user, assignment_id)
    row = svc.submit_settlement(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "realisation.settlement.submit", "realisation_settlement",
              row["settlement_id"], {"assignment_id": str(assignment_id)})
    db.commit()
    return row