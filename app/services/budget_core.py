from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date

from app.schemas.budget import BudgetLineCreate
from app.services.masters import _exists
from app.services.scope import assert_in_root

LINE_COLS = ("line_id, plan_id, assignment_id, version_no, auditor_id, component_id, location_id, "
             "rate_id, trip_leg_id, copied_from_line_id, quantity, unit_rate, amount, basis, "
             "source, approval_status, notes, created_at, updated_at")

_INSERT = """
    INSERT INTO aidaa_core.budget_line
        (plan_id, assignment_id, version_no, auditor_id, component_id, location_id, rate_id,
         quantity, unit_rate, basis, source, notes, created_by, updated_by)
    VALUES (CAST(:p AS uuid), CAST(:a AS uuid), :v, CAST(:au AS uuid), CAST(:c AS uuid),
            CAST(:l AS uuid), CAST(:r AS uuid), :q, :ur, :b, 'manual', :n,
            CAST(:uid AS uuid), CAST(:uid AS uuid))
    RETURNING line_id
"""


def get_line(db: Session, line_id: UUID) -> dict:
    row = db.execute(text(f"SELECT {LINE_COLS} FROM aidaa_core.budget_line WHERE line_id = CAST(:id AS uuid)"),
                     {"id": str(line_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Budget line not found")
    return dict(row._mapping)


def get_assignment_row(db: Session, assignment_id: UUID):
    """Minimal assignment row (assignment_id, plan_id, status, owner_org_id, start_date, end_date)."""
    row = db.execute(text("""
        SELECT assignment_id, plan_id, status, owner_org_id, start_date, end_date
        FROM aidaa_core.assignment WHERE assignment_id = CAST(:a AS uuid)
    """), {"a": str(assignment_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return row

def location_fits(db: Session, rate_location_id: UUID, line_location_id: UUID) -> bool:
    """A rate on a location with no city covers every place in the same province (SBM is per province).
    A rate on a city location covers that city only. When either side has no province (route rates such as
    air tickets, written by city name only), the city names must match exactly."""
    if str(rate_location_id) == str(line_location_id):
        return True
    rows = db.execute(text("""
        SELECT location_id, country, province, city FROM aidaa_core.ref_location
        WHERE location_id IN (CAST(:a AS uuid), CAST(:b AS uuid))
    """), {"a": str(rate_location_id), "b": str(line_location_id)}).fetchall()
    by_id = {str(r.location_id): r for r in rows}
    rate, line = by_id.get(str(rate_location_id)), by_id.get(str(line_location_id))
    if not rate or not line:
        return False
    same = lambda x, y: (x or "").strip().lower() == (y or "").strip().lower()
    if not same(rate.country, line.country):
        return False
    if not rate.province or not line.province:
        return bool(rate.city and line.city and same(rate.city, line.city))
    if not same(rate.province, line.province):
        return False
    return rate.city is None or same(rate.city, line.city)

def resolve_price(db: Session, component_id: UUID, rate_id: Optional[UUID], unit_rate: Optional[float],
                  location_id: Optional[UUID], root_id: Optional[UUID] = None,
                  period_start: Optional[date] = None) -> dict:
    """at_cost components take a typed unit_rate. All others take an approved rate that covers the WHOLE
    period of the plan or assignment (period_start to period_end). Without a period it falls back to today."""
    comp = db.execute(text("""
        SELECT calc_basis, is_active FROM aidaa_core.ref_cost_component
        WHERE component_id = CAST(:c AS uuid)
    """), {"c": str(component_id)}).fetchone()
    if not comp:
        raise HTTPException(status_code=404, detail="Cost component not found")
    if root_id is not None:
        assert_in_root(db, "aidaa_core.ref_cost_component", component_id, root_id, "Cost component")
    if not comp.is_active:
        raise HTTPException(status_code=409, detail="Cost component is inactive")
    if location_id:
        if root_id is not None:
            assert_in_root(db, "aidaa_core.ref_location", location_id, root_id, "Location")
        else:
            _exists(db, "aidaa_core.ref_location", "location_id", location_id, "Location")

    if comp.calc_basis == "at_cost":
        if unit_rate is None:
            raise HTTPException(status_code=400, detail="unit_rate is required for an at_cost component")
        if rate_id:
            raise HTTPException(status_code=400, detail="at_cost lines do not use a rate")
        return {"rate_id": None, "unit_rate": unit_rate, "basis": "at_cost", "location_id": location_id}

    if unit_rate is not None:
        raise HTTPException(status_code=400, detail="unit_rate comes from the approved rate, do not send it")
    if rate_id is None:
        raise HTTPException(status_code=400, detail="rate_id is required for this component")
    start = period_start or date.today()
    rate = db.execute(text("""
        SELECT rate_id, component_id, location_id, amount FROM aidaa_core.ref_cost_rate
        WHERE rate_id = CAST(:r AS uuid) AND is_active = TRUE AND approval_status = 'approved'
          AND effective_from <= CAST(:s AS date)
          AND (effective_to IS NULL OR effective_to >= CAST(:s AS date))
    """), {"r": str(rate_id), "s": start}).fetchone()
    if not rate:
        raise HTTPException(status_code=409, detail=f"Rate not found, not approved, inactive or not effective on {start}")
    if str(rate.component_id) != str(component_id):
        raise HTTPException(status_code=400, detail="Rate belongs to another component")
    if rate.location_id and location_id and not location_fits(db, rate.location_id, location_id):
        raise HTTPException(status_code=400, detail="Rate belongs to another location")
    return {"rate_id": rate.rate_id, "unit_rate": float(rate.amount), "basis": "standard",
            "location_id": location_id or rate.location_id}


def insert_line(db: Session, plan_id, assignment_id, version: int, payload: BudgetLineCreate,
                price: dict, user_id: UUID) -> dict:
    row = db.execute(text(_INSERT), {
        "p": str(plan_id) if plan_id else None, "a": str(assignment_id) if assignment_id else None,
        "v": version, "au": str(payload.auditor_id) if payload.auditor_id else None,
        "c": str(payload.component_id),
        "l": str(price["location_id"]) if price["location_id"] else None,
        "r": str(price["rate_id"]) if price["rate_id"] else None,
        "q": payload.quantity, "ur": price["unit_rate"], "b": price["basis"],
        "n": payload.notes, "uid": str(user_id)}).fetchone()
    return get_line(db, row.line_id)