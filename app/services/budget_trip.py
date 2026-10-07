from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scope import root_of_org, assert_in_root


def _at_cost_component(db: Session, component_id: UUID, root_id: UUID) -> UUID:
    """Trip legs are priced by hand, so the component must be an active at_cost one of the same organisation."""
    assert_in_root(db, "aidaa_core.ref_cost_component", component_id, root_id, "Cost component")
    comp = db.execute(text("""
        SELECT component_id, calc_basis, is_active FROM aidaa_core.ref_cost_component
        WHERE component_id = CAST(:c AS uuid)
    """), {"c": str(component_id)}).fetchone()
    if not comp.is_active:
        raise HTTPException(status_code=409, detail="Cost component is inactive")
    if comp.calc_basis != "at_cost":
        raise HTTPException(status_code=400, detail="A trip leg needs an at_cost cost component (actual cost)")
    return comp.component_id


def _fallback_component(db: Session, root_id: UUID) -> UUID:
    comp = db.execute(text("""
        SELECT component_id FROM aidaa_core.ref_cost_component
        WHERE component_code = 'TRANSPORT' AND calc_basis = 'at_cost' AND is_active = TRUE
          AND root_org_id = CAST(:r AS uuid)
    """), {"r": str(root_id)}).fetchone()
    if not comp:
        raise HTTPException(status_code=409,
                            detail="Choose an at_cost cost component for this trip leg (or create one with code TRANSPORT)")
    return comp.component_id


def sync_leg_line(db: Session, leg_id: UUID, user_id: UUID, component_id: Optional[UUID] = None):
    """Keeps one at_cost budget line per trip leg: create, follow the cost, or delete when cancelled.
    component_id is optional: empty keeps the line's component, or uses code TRANSPORT for a new line."""
    leg = db.execute(text("""
        SELECT leg_id, assignment_id, auditor_id, destination_location_id, estimated_cost,
               actual_cost, status
        FROM aidaa_core.assignment_trip_leg WHERE leg_id = CAST(:l AS uuid)
    """), {"l": str(leg_id)}).fetchone()
    if not leg:
        return
    line = db.execute(text("SELECT line_id FROM aidaa_core.budget_line WHERE trip_leg_id = CAST(:l AS uuid)"),
                      {"l": str(leg_id)}).fetchone()
    if leg.status == "cancelled":
        if line:
            db.execute(text("DELETE FROM aidaa_core.budget_line WHERE line_id = CAST(:id AS uuid)"),
                       {"id": str(line.line_id)})
        return

    owner = db.execute(text("SELECT owner_org_id FROM aidaa_core.assignment WHERE assignment_id = CAST(:a AS uuid)"),
                       {"a": str(leg.assignment_id)}).fetchone()
    root = root_of_org(db, owner.owner_org_id)
    chosen = _at_cost_component(db, component_id, root) if component_id else None
    cost = leg.actual_cost if leg.actual_cost is not None else leg.estimated_cost
    if line:
        db.execute(text("""
            UPDATE aidaa_core.budget_line
            SET unit_rate = :c, location_id = CAST(:loc AS uuid),
                component_id = COALESCE(CAST(:comp AS uuid), component_id),
                updated_at = now(), updated_by = CAST(:u AS uuid)
            WHERE line_id = CAST(:id AS uuid)
        """), {"c": cost, "loc": str(leg.destination_location_id),
               "comp": str(chosen) if chosen else None, "u": str(user_id), "id": str(line.line_id)})
        return

    comp_id = chosen or _fallback_component(db, root)
    db.execute(text("""
        INSERT INTO aidaa_core.budget_line
            (assignment_id, version_no, auditor_id, component_id, location_id, trip_leg_id,
             quantity, unit_rate, basis, source, created_by, updated_by)
        VALUES (CAST(:a AS uuid), 1, CAST(:au AS uuid), CAST(:c AS uuid), CAST(:loc AS uuid),
                CAST(:l AS uuid), 1, :cost, 'at_cost', 'manual', CAST(:u AS uuid), CAST(:u AS uuid))
    """), {"a": str(leg.assignment_id), "au": str(leg.auditor_id), "c": str(comp_id),
           "loc": str(leg.destination_location_id), "l": str(leg_id), "cost": cost, "u": str(user_id)})