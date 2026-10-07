from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.trip import VisitCreate, VisitUpdate
from app.services.masters import _exists, _update_row
from app.services.assignments import get_assignment
from app.services.logs import log_status, log_comment
from app.services.trip_common import (
    OVERLAP, SCHED_INSERT, open_assignment, check_range, check_members, release_schedule,
)

_VIS_COLS = ("visit_id, assignment_id, location_id, visit_start, visit_end, purpose, status, "
             "cancel_reason, created_at, updated_at")


def _attendee_ids(db: Session, visit_id: UUID) -> list:
    rows = db.execute(text("SELECT auditor_id FROM aidaa_core.visit_attendee WHERE visit_id = CAST(:v AS uuid)"),
                      {"v": str(visit_id)}).fetchall()
    return [r.auditor_id for r in rows]


def _set_attendees(db: Session, visit_id: UUID, ids):
    db.execute(text("DELETE FROM aidaa_core.visit_attendee WHERE visit_id = CAST(:v AS uuid)"),
               {"v": str(visit_id)})
    for auditor_id in {str(i) for i in ids}:
        db.execute(text("""
            INSERT INTO aidaa_core.visit_attendee (visit_id, auditor_id)
            VALUES (CAST(:v AS uuid), CAST(:a AS uuid))
        """), {"v": str(visit_id), "a": auditor_id})


def get_visit(db: Session, visit_id: UUID) -> dict:
    row = db.execute(text(f"SELECT {_VIS_COLS} FROM aidaa_core.assignment_visit WHERE visit_id = CAST(:id AS uuid)"),
                     {"id": str(visit_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Visit not found")
    out = dict(row._mapping)
    out["attendee_ids"] = _attendee_ids(db, visit_id)
    return out


def list_visits(db: Session, assignment_id: UUID, status: Optional[str] = None) -> list[dict]:
    get_assignment(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {_VIS_COLS} FROM aidaa_core.assignment_visit
        WHERE assignment_id = CAST(:a AS uuid) AND (CAST(:st AS text) IS NULL OR status = CAST(:st AS text))
        ORDER BY visit_start
    """), {"a": str(assignment_id), "st": status}).fetchall()
    out = []
    for r in rows:
        d = dict(r._mapping)
        d["attendee_ids"] = _attendee_ids(db, d["visit_id"])
        out.append(d)
    return out


def create_visit(db: Session, assignment_id: UUID, payload: VisitCreate, user_id: UUID) -> dict:
    open_assignment(db, assignment_id)
    _exists(db, "aidaa_core.ref_location", "location_id", payload.location_id, "Location")
    check_range(payload.visit_start, payload.visit_end, "visit_end")
    check_members(db, assignment_id, payload.attendee_ids)
    row = db.execute(text("""
        INSERT INTO aidaa_core.assignment_visit
            (assignment_id, location_id, visit_start, visit_end, purpose, created_by, updated_by)
        VALUES (CAST(:a AS uuid), CAST(:l AS uuid), :s, :e, :p, CAST(:uid AS uuid), CAST(:uid AS uuid))
        RETURNING visit_id
    """), {"a": str(assignment_id), "l": str(payload.location_id), "s": payload.visit_start,
           "e": payload.visit_end, "p": payload.purpose, "uid": str(user_id)}).fetchone()
    _set_attendees(db, row.visit_id, payload.attendee_ids)
    log_status(db, "visit", row.visit_id, None, "planned", user_id)
    return get_visit(db, row.visit_id)


def update_visit(db: Session, visit_id: UUID, payload: VisitUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    attendees = data.pop("attendee_ids", None)
    if not data and attendees is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    v = get_visit(db, visit_id)
    open_assignment(db, v["assignment_id"])
    if v["status"] != "planned":
        raise HTTPException(status_code=409, detail="Only planned visits can be edited, cancel a confirmed one first")
    if data.get("location_id"):
        _exists(db, "aidaa_core.ref_location", "location_id", data["location_id"], "Location")
    check_range(data.get("visit_start", v["visit_start"]), data.get("visit_end", v["visit_end"]), "visit_end")
    if attendees is not None:
        check_members(db, v["assignment_id"], attendees)
    _update_row(db, "aidaa_core.assignment_visit", "visit_id", visit_id, data,
                {"location_id"}, user_id, "visit_id")
    if attendees is not None:
        _set_attendees(db, visit_id, attendees)
    return get_visit(db, visit_id)


def confirm_visit(db: Session, visit_id: UUID, user_id: UUID) -> dict:
    v = get_visit(db, visit_id)
    open_assignment(db, v["assignment_id"])
    if v["status"] != "planned":
        raise HTTPException(status_code=409, detail="Only planned visits can be confirmed")
    if not v["attendee_ids"]:
        raise HTTPException(status_code=400, detail="Visit needs at least one attendee before it is confirmed")
    try:
        for auditor_id in v["attendee_ids"]:
            db.execute(text(SCHED_INSERT), {
                "au": str(auditor_id), "asg": str(v["assignment_id"]), "kind": "visit",
                "vid": str(visit_id), "lid": None, "loc": str(v["location_id"]),
                "s": v["visit_start"], "e": v["visit_end"], "uid": str(user_id)})
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=OVERLAP)
    db.execute(text("""
        UPDATE aidaa_core.assignment_visit
        SET status = 'confirmed', updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE visit_id = CAST(:id AS uuid)
    """), {"u": str(user_id), "id": str(visit_id)})
    log_status(db, "visit", visit_id, "planned", "confirmed", user_id)
    return get_visit(db, visit_id)


def cancel_visit(db: Session, visit_id: UUID, reason: str, user_id: UUID) -> dict:
    v = get_visit(db, visit_id)
    if v["status"] not in ("planned", "confirmed"):
        raise HTTPException(status_code=409, detail="Visit is already cancelled")
    db.execute(text("""
        UPDATE aidaa_core.assignment_visit
        SET status = 'cancelled', cancel_reason = :r, updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE visit_id = CAST(:id AS uuid)
    """), {"r": reason, "u": str(user_id), "id": str(visit_id)})
    release_schedule(db, "visit_id", visit_id)
    log_status(db, "visit", visit_id, v["status"], "cancelled", user_id)
    log_comment(db, "visit", visit_id, f"Cancelled: {reason}", user_id)
    return get_visit(db, visit_id)