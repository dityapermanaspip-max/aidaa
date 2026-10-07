from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.trip import LegCreate, LegUpdate
from app.services.masters import _exists, _update_row
from app.services.assignments import get_assignment
from app.services.logs import log_status, log_comment
from app.services.trip_common import (
    OVERLAP, SCHED_INSERT, open_assignment, check_range, check_members, release_schedule,
)

_LEG_COLS = ("leg_id, assignment_id, auditor_id, leg_no, origin_location_id, destination_location_id, "
             "mode, depart_at, arrive_at, estimated_cost, actual_cost, status, created_at, updated_at")

# The cost component lives on the leg's budget line, not on the leg row.
_LEG_SQL = f"""
    SELECT {_LEG_COLS},
           (SELECT b.component_id FROM aidaa_core.budget_line b
            WHERE b.trip_leg_id = assignment_trip_leg.leg_id LIMIT 1) AS component_id
    FROM aidaa_core.assignment_trip_leg
"""


def get_leg(db: Session, leg_id: UUID) -> dict:
    row = db.execute(text(f"{_LEG_SQL} WHERE leg_id = CAST(:id AS uuid)"), {"id": str(leg_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Trip leg not found")
    return dict(row._mapping)


def list_legs(db: Session, assignment_id: UUID, auditor_id: Optional[UUID] = None) -> list[dict]:
    get_assignment(db, assignment_id)
    rows = db.execute(text(f"""
        {_LEG_SQL}
        WHERE assignment_id = CAST(:a AS uuid)
          AND (CAST(:au AS uuid) IS NULL OR auditor_id = CAST(:au AS uuid))
        ORDER BY auditor_id, leg_no
    """), {"a": str(assignment_id), "au": str(auditor_id) if auditor_id else None}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_leg(db: Session, assignment_id: UUID, payload: LegCreate, user_id: UUID) -> dict:
    open_assignment(db, assignment_id)
    check_members(db, assignment_id, [payload.auditor_id])
    _exists(db, "aidaa_core.ref_location", "location_id", payload.origin_location_id, "Origin location")
    _exists(db, "aidaa_core.ref_location", "location_id", payload.destination_location_id, "Destination location")
    if payload.origin_location_id == payload.destination_location_id:
        raise HTTPException(status_code=400, detail="Origin and destination are the same")
    check_range(payload.depart_at, payload.arrive_at, "arrive_at")
    try:
        row = db.execute(text(f"""
            INSERT INTO aidaa_core.assignment_trip_leg
                (assignment_id, auditor_id, leg_no, origin_location_id, destination_location_id,
                 mode, depart_at, arrive_at, estimated_cost, created_by, updated_by)
            VALUES (CAST(:a AS uuid), CAST(:au AS uuid),
                    (SELECT COALESCE(MAX(leg_no), 0) + 1 FROM aidaa_core.assignment_trip_leg
                     WHERE assignment_id = CAST(:a AS uuid) AND auditor_id = CAST(:au AS uuid)),
                    CAST(:o AS uuid), CAST(:d AS uuid), :m, :dep, :arr, :cost,
                    CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING {_LEG_COLS}
        """), {"a": str(assignment_id), "au": str(payload.auditor_id),
               "o": str(payload.origin_location_id), "d": str(payload.destination_location_id),
               "m": payload.mode, "dep": payload.depart_at, "arr": payload.arrive_at,
               "cost": payload.estimated_cost, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Leg number clash, please retry")
    leg = dict(row._mapping)
    log_status(db, "trip_leg", leg["leg_id"], None, "planned", user_id)
    return leg  # the router then calls sync_leg_line (with payload.component_id) to create the budget line


def update_leg(db: Session, leg_id: UUID, payload: LegUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    component_id = data.pop("component_id", None)  # not a column of the leg, it belongs to the budget line
    if not data and component_id is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    leg = get_leg(db, leg_id)
    open_assignment(db, leg["assignment_id"])
    if leg["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Cancelled legs cannot be edited")
    if component_id is not None and leg["status"] != "planned":
        raise HTTPException(status_code=409, detail="The cost component can only change while the leg is planned")
    if leg["status"] == "planned" and "actual_cost" in data:
        raise HTTPException(status_code=400, detail="actual_cost can only be set after the leg is confirmed")
    if leg["status"] == "confirmed" and set(data) - {"actual_cost"}:
        raise HTTPException(status_code=409, detail="Confirmed legs only accept actual_cost, cancel and recreate to change the trip")
    for key in ("origin_location_id", "destination_location_id"):
        if data.get(key):
            _exists(db, "aidaa_core.ref_location", "location_id", data[key], "Location")
    if str(data.get("origin_location_id", leg["origin_location_id"])) == \
            str(data.get("destination_location_id", leg["destination_location_id"])):
        raise HTTPException(status_code=400, detail="Origin and destination are the same")
    check_range(data.get("depart_at", leg["depart_at"]), data.get("arrive_at", leg["arrive_at"]), "arrive_at")
    _update_row(db, "aidaa_core.assignment_trip_leg", "leg_id", leg_id, data,
                {"origin_location_id", "destination_location_id"}, user_id, "leg_id")
    return get_leg(db, leg_id)


def confirm_leg(db: Session, leg_id: UUID, user_id: UUID) -> dict:
    leg = get_leg(db, leg_id)
    open_assignment(db, leg["assignment_id"])
    if leg["status"] != "planned":
        raise HTTPException(status_code=409, detail="Only planned legs can be confirmed")
    if not leg["depart_at"] or not leg["arrive_at"]:
        raise HTTPException(status_code=400, detail="depart_at and arrive_at are required to confirm a leg")
    try:
        db.execute(text(SCHED_INSERT), {
            "au": str(leg["auditor_id"]), "asg": str(leg["assignment_id"]), "kind": "travel",
            "vid": None, "lid": str(leg_id), "loc": str(leg["destination_location_id"]),
            "s": leg["depart_at"].date(), "e": leg["arrive_at"].date(), "uid": str(user_id)})
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=OVERLAP)
    db.execute(text("""
        UPDATE aidaa_core.assignment_trip_leg
        SET status = 'confirmed', updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE leg_id = CAST(:id AS uuid)
    """), {"u": str(user_id), "id": str(leg_id)})
    log_status(db, "trip_leg", leg_id, "planned", "confirmed", user_id)
    return get_leg(db, leg_id)


def cancel_leg(db: Session, leg_id: UUID, reason: str, user_id: UUID) -> dict:
    leg = get_leg(db, leg_id)
    if leg["status"] not in ("planned", "confirmed"):
        raise HTTPException(status_code=409, detail="Leg is already cancelled")
    db.execute(text("""
        UPDATE aidaa_core.assignment_trip_leg
        SET status = 'cancelled', updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE leg_id = CAST(:id AS uuid)
    """), {"u": str(user_id), "id": str(leg_id)})
    release_schedule(db, "leg_id", leg_id)
    log_status(db, "trip_leg", leg_id, leg["status"], "cancelled", user_id)
    log_comment(db, "trip_leg", leg_id, f"Cancelled: {reason}", user_id)
    return get_leg(db, leg_id)