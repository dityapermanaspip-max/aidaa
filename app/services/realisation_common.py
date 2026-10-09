from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scope import get_root, assert_in_root
from app.services.trip_common import check_members

REALISE_STATUSES = ("issued", "ongoing", "finished")


def assert_realisable(db: Session, assignment_id: UUID, label: str = "saved"):
    """Realisation only on an issued, ongoing or finished assignment (not draft/cancelled)."""
    row = db.execute(text("""
        SELECT status, owner_org_id FROM aidaa_core.assignment
        WHERE assignment_id = CAST(:a AS uuid)
    """), {"a": str(assignment_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if row.status not in REALISE_STATUSES:
        raise HTTPException(status_code=409,
                            detail=f"Realisation is only available on an issued, ongoing or finished assignment "
                                   f"({label} was not).")
    return row


def assert_member(db: Session, assignment_id: UUID, auditor_id: UUID):
    """Records belong to ACTIVE team members (same rule as visits and legs)."""
    check_members(db, assignment_id, [auditor_id])


def assert_cost_ref(db: Session, user_id: UUID, component_id: UUID, location_id=None):
    """Cost component and location must belong to the active root (read-only masters are root scoped)."""
    root = get_root(db, user_id)
    assert_in_root(db, "aidaa_core.ref_cost_component", component_id, root, "Cost component")
    if location_id:
        assert_in_root(db, "aidaa_core.ref_location", location_id, root, "Location")


def username_map(db: Session, assignment_id: UUID) -> dict:
    rows = db.execute(text("""
        SELECT a.auditor_id, u.username
        FROM aidaa_core.assignment_member m
        JOIN aidaa_core.auditor a ON a.auditor_id = m.auditor_id
        JOIN iam.users u ON u.user_id = a.user_id
        WHERE m.assignment_id = CAST(:a AS uuid)
    """), {"a": str(assignment_id)}).fetchall()
    return {r.auditor_id: r.username for r in rows}