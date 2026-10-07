from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    coststd_read, coststd_create, coststd_update, coststd_delete,
    costrate_read, costrate_create, costrate_update, costrate_delete, costrate_approve,
    log_audit,
)
from app.schemas.aidaa import (
    CostComponentCreate, CostComponentUpdate, CostComponentOut,
    CostRateCreate, CostRateUpdate, CostRateDecision, CostRateOut,
)
from app.services import masters_costing as svc

router = APIRouter()


# --- Cost components ---

@router.get("/cost-components", response_model=List[CostComponentOut])
def list_components(active_only: bool = True, search: Optional[str] = Query(None),
                    db: Session = Depends(get_db), user=Depends(coststd_read)):
    return svc.list_components(db, user.user_id, active_only, search)


@router.get("/cost-components/{component_id}", response_model=CostComponentOut)
def get_component(component_id: UUID, db: Session = Depends(get_db), user=Depends(coststd_read)):
    return svc.get_component(db, user.user_id, component_id)


@router.post("/cost-components", response_model=CostComponentOut, status_code=201)
def create_component(payload: CostComponentCreate, db: Session = Depends(get_db),
                     user=Depends(coststd_create)):
    row = svc.create_component(db, payload, user.user_id)
    log_audit(db, user.user_id, "cost_component.create", "ref_cost_component", row["component_id"],
              {"component_code": row["component_code"]})
    db.commit()
    return row


@router.patch("/cost-components/{component_id}", response_model=CostComponentOut)
def update_component(component_id: UUID, payload: CostComponentUpdate,
                     db: Session = Depends(get_db), user=Depends(coststd_update)):
    row = svc.update_component(db, component_id, payload, user.user_id)
    log_audit(db, user.user_id, "cost_component.update", "ref_cost_component", component_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/cost-components/{component_id}", response_model=CostComponentOut)
def deactivate_component(component_id: UUID, db: Session = Depends(get_db),
                         user=Depends(coststd_delete)):
    row = svc.deactivate_component(db, component_id, user.user_id)
    log_audit(db, user.user_id, "cost_component.deactivate", "ref_cost_component", component_id)
    db.commit()
    return row


# --- Cost rates ---

@router.get("/cost-rates", response_model=List[CostRateOut])
def list_rates(active_only: bool = True, component_id: Optional[UUID] = None,
               location_id: Optional[UUID] = None, status: Optional[str] = Query(None),
               grade: Optional[str] = Query(None, max_length=30),
               limit: Optional[int] = Query(None, ge=1, le=200), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), user=Depends(costrate_read)):
    return svc.list_rates(db, user.user_id, active_only, component_id, location_id, status, grade, limit, offset)


@router.get("/cost-rates/{rate_id}", response_model=CostRateOut)
def get_rate(rate_id: UUID, db: Session = Depends(get_db), user=Depends(costrate_read)):
    return svc.get_rate(db, user.user_id, rate_id)


@router.post("/cost-rates", response_model=CostRateOut, status_code=201)
def create_rate(payload: CostRateCreate, db: Session = Depends(get_db), user=Depends(costrate_create)):
    row = svc.create_rate(db, payload, user.user_id)
    log_audit(db, user.user_id, "cost_rate.create", "ref_cost_rate", row["rate_id"],
              {"component_id": str(row["component_id"]), "amount": float(row["amount"])})
    db.commit()
    return row


@router.patch("/cost-rates/{rate_id}", response_model=CostRateOut)
def update_rate(rate_id: UUID, payload: CostRateUpdate,
                db: Session = Depends(get_db), user=Depends(costrate_update)):
    row = svc.update_rate(db, rate_id, payload, user.user_id)
    log_audit(db, user.user_id, "cost_rate.update", "ref_cost_rate", rate_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.post("/cost-rates/{rate_id}/submit", response_model=CostRateOut)
def submit_rate(rate_id: UUID, db: Session = Depends(get_db), user=Depends(costrate_update)):
    row = svc.submit_rate(db, rate_id, user.user_id)
    log_audit(db, user.user_id, "cost_rate.submit", "ref_cost_rate", rate_id)
    db.commit()
    return row


@router.post("/cost-rates/{rate_id}/decide", response_model=CostRateOut)
def decide_rate(rate_id: UUID, payload: CostRateDecision,
                db: Session = Depends(get_db), user=Depends(costrate_approve)):
    row = svc.decide_rate(db, rate_id, payload, user.user_id)
    log_audit(db, user.user_id, f"cost_rate.{payload.decision}", "ref_cost_rate", rate_id,
              payload.model_dump(mode="json"))
    db.commit()
    return row


@router.delete("/cost-rates/{rate_id}", response_model=CostRateOut)
def deactivate_rate(rate_id: UUID, db: Session = Depends(get_db), user=Depends(costrate_delete)):
    row = svc.deactivate_rate(db, rate_id, user.user_id)
    log_audit(db, user.user_id, "cost_rate.deactivate", "ref_cost_rate", rate_id)
    db.commit()
    return row