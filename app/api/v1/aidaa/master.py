from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session


from app.core.database import get_db
from app.api.dependencies import (
    location_read, location_create, location_update, location_delete, log_audit,
)

from app.api.dependencies import (
    location_read, location_create, location_update, location_delete,
    unit_read, unit_create, unit_update, unit_delete, log_audit,
)
from app.schemas.aidaa import (
    LocationCreate, LocationUpdate, LocationOut,
    AuditTypeCreate, AuditTypeUpdate, AuditTypeOut,
    UnitCreate, UnitUpdate, UnitOut,
)
from app.services import masters

router = APIRouter()


@router.get("/locations", response_model=List[LocationOut])
def list_locations(active_only: bool = True, search: Optional[str] = Query(None),
                   db: Session = Depends(get_db), user=Depends(location_read)):
    return masters.list_locations(db, user.user_id, active_only, search)


@router.get("/locations/{location_id}", response_model=LocationOut)
def get_location(location_id: UUID, db: Session = Depends(get_db), user=Depends(location_read)):
    return masters.get_location(db, user.user_id, location_id)


@router.post("/locations", response_model=LocationOut, status_code=201)
def create_location(payload: LocationCreate, db: Session = Depends(get_db), user=Depends(location_create)):
    row = masters.create_location(db, payload, user.user_id)
    log_audit(db, user.user_id, "location.create", "ref_location", row["location_id"],
              {"location_code": row["location_code"]})
    db.commit()
    return row


@router.patch("/locations/{location_id}", response_model=LocationOut)
def update_location(location_id: UUID, payload: LocationUpdate,
                    db: Session = Depends(get_db), user=Depends(location_update)):
    row = masters.update_location(db, location_id, payload, user.user_id)
    log_audit(db, user.user_id, "location.update", "ref_location", location_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/locations/{location_id}", response_model=LocationOut)
def deactivate_location(location_id: UUID, db: Session = Depends(get_db), user=Depends(location_delete)):
    row = masters.deactivate_location(db, location_id, user.user_id)
    log_audit(db, user.user_id, "location.deactivate", "ref_location", location_id)
    db.commit()
    return row
    
# --- Audit types ---

@router.get("/audit-types", response_model=List[AuditTypeOut])
def list_audit_types(active_only: bool = True, search: Optional[str] = Query(None),
                     db: Session = Depends(get_db), user=Depends(unit_read)):
    return masters.list_audit_types(db, user.user_id, active_only, search)


@router.get("/audit-types/{type_id}", response_model=AuditTypeOut)
def get_audit_type(type_id: UUID, db: Session = Depends(get_db), user=Depends(unit_read)):
    return masters.get_audit_type(db, user.user_id, type_id)

@router.post("/audit-types", response_model=AuditTypeOut, status_code=201)
def create_audit_type(payload: AuditTypeCreate, db: Session = Depends(get_db), user=Depends(unit_create)):
    row = masters.create_audit_type(db, payload, user.user_id)
    log_audit(db, user.user_id, "audit_type.create", "ref_audit_type", row["type_id"],
              {"type_code": row["type_code"]})
    db.commit()
    return row


@router.patch("/audit-types/{type_id}", response_model=AuditTypeOut)
def update_audit_type(type_id: UUID, payload: AuditTypeUpdate,
                      db: Session = Depends(get_db), user=Depends(unit_update)):
    row = masters.update_audit_type(db, type_id, payload, user.user_id)
    log_audit(db, user.user_id, "audit_type.update", "ref_audit_type", type_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/audit-types/{type_id}", response_model=AuditTypeOut)
def deactivate_audit_type(type_id: UUID, db: Session = Depends(get_db), user=Depends(unit_delete)):
    row = masters.deactivate_audit_type(db, type_id, user.user_id)
    log_audit(db, user.user_id, "audit_type.deactivate", "ref_audit_type", type_id)
    db.commit()
    return row


# --- Auditable units ---

@router.get("/units", response_model=List[UnitOut])
def list_units(active_only: bool = True, search: Optional[str] = Query(None),
               db: Session = Depends(get_db), user=Depends(unit_read)):
    return masters.list_units(db, user.user_id, active_only, search)


@router.get("/units/{unit_id}", response_model=UnitOut)
def get_unit(unit_id: UUID, db: Session = Depends(get_db), user=Depends(unit_read)):
    return masters.get_unit(db, user.user_id, unit_id)


@router.post("/units", response_model=UnitOut, status_code=201)
def create_unit(payload: UnitCreate, db: Session = Depends(get_db), user=Depends(unit_create)):
    row = masters.create_unit(db, payload, user.user_id)
    log_audit(db, user.user_id, "unit.create", "ref_auditable_unit", row["unit_id"],
              {"unit_code": row["unit_code"]})
    db.commit()
    return row


@router.patch("/units/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: UUID, payload: UnitUpdate,
                db: Session = Depends(get_db), user=Depends(unit_update)):
    row = masters.update_unit(db, unit_id, payload, user.user_id)
    log_audit(db, user.user_id, "unit.update", "ref_auditable_unit", unit_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/units/{unit_id}", response_model=UnitOut)
def deactivate_unit(unit_id: UUID, db: Session = Depends(get_db), user=Depends(unit_delete)):
    row = masters.deactivate_unit(db, unit_id, user.user_id)
    log_audit(db, user.user_id, "unit.deactivate", "ref_auditable_unit", unit_id)
    db.commit()
    return row