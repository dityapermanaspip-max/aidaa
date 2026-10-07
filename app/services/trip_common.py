"""Rules shared by visits and trip legs."""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.assignments import get_assignment

OPEN = ("draft", "issued", "ongoing")
OVERLAP = "Overlaps another confirmed visit or trip of the same auditor"

SCHED_INSERT = """
    INSERT INTO aidaa_core.auditor_schedule
        (auditor_id, assignment_id, kind, visit_id, leg_id, location_id, period, status, created_by)
    VALUES (CAST(:au AS uuid), CAST(:asg AS uuid), :kind, CAST(:vid AS uuid), CAST(:lid AS uuid),
            CAST(:loc AS uuid), daterange(CAST(:s AS date), CAST(:e AS date), '[]'),
            'confirmed', CAST(:uid AS uuid))
"""


def open_assignment(db: Session, assignment_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in OPEN:
        raise HTTPException(status_code=409, detail="Assignment is finished or cancelled")
    return a


def check_range(start, end, label: str):
    if start and end and end < start:
        raise HTTPException(status_code=400, detail=f"{label} cannot be before the start")


def check_members(db: Session, assignment_id: UUID, ids):
    """Every auditor must be an ACTIVE member of this assignment's team."""
    wanted = {str(i) for i in ids}
    if not wanted:
        return
    rows = db.execute(text("""
        SELECT auditor_id FROM aidaa_core.assignment_member
        WHERE assignment_id = CAST(:a AS uuid) AND end_date IS NULL
          AND auditor_id = ANY(CAST(:ids AS uuid[]))
    """), {"a": str(assignment_id), "ids": list(wanted)}).fetchall()
    if {str(r.auditor_id) for r in rows} != wanted:
        raise HTTPException(status_code=400, detail="Auditors must be active team members of this assignment")


def release_schedule(db: Session, column: str, record_id: UUID):
    # column is an internal constant ('visit_id' or 'leg_id')
    db.execute(text(f"UPDATE aidaa_core.auditor_schedule SET status = 'cancelled' "
                    f"WHERE {column} = CAST(:id AS uuid) AND status = 'confirmed'"),
               {"id": str(record_id)})