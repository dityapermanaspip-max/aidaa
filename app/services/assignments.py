from typing import Optional, List
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.assignment import AssignmentCreate, AssignmentUpdate
from app.services.masters import _exists, _update_row
from app.services.plans import get_plan
from app.services.logs import log_edit, log_status, log_comment
from app.services.budgets import copy_plan_lines, assert_funding_matches
from app.services.conflict import check_conflict
from app.services.org_options import assert_owner_org
from app.services.scope import get_root, assert_in_root
from app.services.unit_links import clean_units, check_units, unit_org_ids, unit_ids_for, sync_units

_APPROVED_PLAN = ("approved", "ai_approved")

# unit_org_id is the org of the FIRST unit. get_assignment also adds unit_ids and unit_org_ids (all units).
_ASG_SQL = """
    SELECT a.assignment_id, a.assignment_no, a.plan_id, a.owner_org_id, a.unit_id, a.type_id,
           a.start_date, a.end_date, a.assignment_doc_url, a.assignment_doc_name, a.status,
           a.issued_by, a.issued_at, a.notes, a.is_active, a.created_at, a.updated_at,
           (a.plan_id IS NULL) AS is_unplanned, u.org_id AS unit_org_id
    FROM aidaa_core.assignment a
    JOIN aidaa_core.ref_auditable_unit u ON u.unit_id = a.unit_id
"""


def _check_dates(start, end):
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")


def get_assignment(db: Session, assignment_id: UUID) -> dict:
    row = db.execute(text(f"{_ASG_SQL} WHERE a.assignment_id = CAST(:id AS uuid)"),
                     {"id": str(assignment_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    a = dict(row._mapping)
    a["unit_ids"] = unit_ids_for(db, "assignment", [assignment_id]).get(str(assignment_id), [])
    a["unit_org_ids"] = unit_org_ids(db, a["unit_ids"])
    return a


def assert_read_access(org_ids: Optional[List[UUID]], a: dict):
    """Audit team side: owner org. Auditee PIC side: the org of ANY unit, and only after it is issued."""
    if org_ids is None or a["owner_org_id"] in org_ids:
        return
    if a["status"] != "draft" and any(o in org_ids for o in a["unit_org_ids"]):
        return
    raise HTTPException(status_code=403, detail="Access denied: assignment is outside your organizations")


def list_assignments(db: Session, org_ids: Optional[List[UUID]], active_only: bool = True,
                     status: Optional[str] = None, plan_id: Optional[UUID] = None,
                     unplanned_only: bool = False, search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        {_ASG_SQL}
        WHERE (:all_orgs
               OR a.owner_org_id = ANY(CAST(:orgs AS uuid[]))
               OR (a.status <> 'draft' AND EXISTS (
                     SELECT 1 FROM aidaa_core.assignment_unit au
                     JOIN aidaa_core.ref_auditable_unit au_u ON au_u.unit_id = au.unit_id
                     WHERE au.assignment_id = a.assignment_id
                       AND au_u.org_id = ANY(CAST(:orgs AS uuid[])))))
          AND (:active_only = FALSE OR a.is_active = TRUE)
          AND (CAST(:st AS text) IS NULL OR a.status = CAST(:st AS text))
          AND (CAST(:p AS uuid) IS NULL OR a.plan_id = CAST(:p AS uuid))
          AND (:unplanned = FALSE OR a.plan_id IS NULL)
          AND (CAST(:q AS text) IS NULL OR a.assignment_no ILIKE CAST(:q AS text))
        ORDER BY a.start_date DESC, a.assignment_no
    """), {"all_orgs": org_ids is None, "orgs": [str(o) for o in (org_ids or [])],
           "active_only": active_only, "st": status,
           "p": str(plan_id) if plan_id else None, "unplanned": unplanned_only,
           "q": f"%{search}%" if search else None}).fetchall()
    items = [dict(r._mapping) for r in rows]
    units = unit_ids_for(db, "assignment", [a["assignment_id"] for a in items])
    for a in items:
        a["unit_ids"] = units.get(str(a["assignment_id"]), [])
    return items


def _recheck_team(db: Session, assignment_id: UUID, org_ids: list, user_id: UUID):
    """New units must not create a conflict of interest for people already on the team."""
    members = db.execute(text("""
        SELECT auditor_id FROM aidaa_core.assignment_member
        WHERE assignment_id = CAST(:a AS uuid) AND end_date IS NULL
    """), {"a": str(assignment_id)}).fetchall()
    for m in members:
        for org_id in org_ids:
            check_conflict(db, m.auditor_id, org_id, user_id, assignment_id=assignment_id)


def create_assignment(db: Session, payload: AssignmentCreate, user_id: UUID) -> dict:
    if payload.plan_id:
        plan = get_plan(db, payload.plan_id)
        if not plan["is_active"] or plan["status"] not in _APPROVED_PLAN:
            raise HTTPException(status_code=409, detail="Plan must be approved before an assignment is created")
        for field in ("owner_org_id", "unit_id", "type_id"):
            given = getattr(payload, field)
            if given is not None and str(given) != str(plan[field]):
                raise HTTPException(status_code=400, detail=f"{field} does not match the plan")
        if payload.extra_unit_ids:
            raise HTTPException(status_code=400,
                                detail="A planned assignment follows the plan's units, extra_unit_ids is for unplanned audits only")
        owner, unit, atype = plan["owner_org_id"], plan["unit_id"], plan["type_id"]
        unit_ids = [str(u) for u in plan["unit_ids"]]
        start = payload.start_date or plan["period_start"]
        end = payload.end_date or plan["period_end"]
    else:
        missing = [f for f in ("owner_org_id", "unit_id", "type_id", "start_date", "end_date")
                   if getattr(payload, f) is None]
        if missing:
            raise HTTPException(status_code=400,
                                detail=f"Required when plan_id is empty: {', '.join(missing)}")
        assert_owner_org(db, user_id, payload.owner_org_id)
        unit_ids = clean_units(payload.unit_id, payload.extra_unit_ids)
        check_units(db, unit_ids)
        assert_in_root(db, "aidaa_core.ref_audit_type", payload.type_id, get_root(db, user_id), "Audit type")       
        owner, unit, atype = payload.owner_org_id, payload.unit_id, payload.type_id
        start, end = payload.start_date, payload.end_date
    _check_dates(start, end)

    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.assignment
                (assignment_no, plan_id, owner_org_id, unit_id, type_id, start_date, end_date,
                 notes, created_by, updated_by)
            VALUES (:no, CAST(:p AS uuid), CAST(:org AS uuid), CAST(:unit AS uuid),
                    CAST(:type AS uuid), :s, :e, :notes, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING assignment_id
        """), {"no": payload.assignment_no,
               "p": str(payload.plan_id) if payload.plan_id else None,
               "org": str(owner), "unit": str(unit), "type": str(atype),
               "s": start, "e": end, "notes": payload.notes, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="assignment_no already exists")
    sync_units(db, "assignment", row.assignment_id, unit_ids, user_id)
    log_status(db, "assignment", row.assignment_id, None, "draft", user_id)
    return get_assignment(db, row.assignment_id)


def update_assignment(db: Session, assignment_id: UUID, payload: AssignmentUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    extras = data.pop("extra_unit_ids", None)
    if not data and extras is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    current = get_assignment(db, assignment_id)
    if current["status"] != "draft":
        raise HTTPException(status_code=409,
                            detail="Only draft assignments can be edited, issued ones need a change request")
    _check_dates(data.get("start_date", current["start_date"]), data.get("end_date", current["end_date"]))

    old_units = [str(u) for u in current["unit_ids"]]
    new_units = old_units
    if extras is not None:
        if current["plan_id"]:
            raise HTTPException(status_code=400, detail="A planned assignment follows the plan's units")
        new_units = clean_units(current["unit_id"], extras)
        added = [u for u in new_units if u not in old_units]
        if added:
            check_units(db, added)
            _recheck_team(db, assignment_id, unit_org_ids(db, added), user_id)

    _update_row(db, "aidaa_core.assignment", "assignment_id", assignment_id, data,
                set(), user_id, "assignment_id")
    if extras is not None:
        sync_units(db, "assignment", assignment_id, new_units, user_id)
        if set(new_units) != set(old_units):
            log_edit(db, "assignment", assignment_id, "unit_ids", old_units, new_units, user_id)
    for key, new in data.items():
        if str(current[key]) != str(new):
            log_edit(db, "assignment", assignment_id, key, current[key], new, user_id)
    return get_assignment(db, assignment_id)


def issue_assignment(db: Session, assignment_id: UUID, user_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    if not a["is_active"] or a["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only active draft assignments can be issued")
    if a["plan_id"]:
        plan = get_plan(db, a["plan_id"])
        if plan["status"] not in _APPROVED_PLAN:
            raise HTTPException(status_code=409, detail="Plan is no longer approved")
    has_team = db.execute(text("""
        SELECT 1 FROM aidaa_core.assignment_member
        WHERE assignment_id = CAST(:id AS uuid) AND end_date IS NULL LIMIT 1
    """), {"id": str(assignment_id)}).fetchone()
    if not has_team:
        raise HTTPException(status_code=409, detail="Assignment needs at least one team member before it is issued")

    copied = copy_plan_lines(db, a, user_id) if a["plan_id"] else 0
    assert_funding_matches(db, assignment_id)  # raises 409, nothing is committed then

    db.execute(text("""
        UPDATE aidaa_core.assignment
        SET status = 'issued', issued_by = CAST(:u AS uuid), issued_at = now(),
            updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE assignment_id = CAST(:id AS uuid)
    """), {"u": str(user_id), "id": str(assignment_id)})
    log_status(db, "assignment", assignment_id, "draft", "issued", user_id)
    if copied:
        log_comment(db, "assignment", assignment_id, f"{copied} budget lines copied from the plan", user_id)
    return get_assignment(db, assignment_id)


def cancel_assignment(db: Session, assignment_id: UUID, reason: str, user_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in ("draft", "issued"):
        raise HTTPException(status_code=409, detail="Only draft or issued assignments can be cancelled")
    if not reason.strip():
        raise HTTPException(status_code=400, detail="reason is required")
    db.execute(text("""
        UPDATE aidaa_core.assignment
        SET status = 'cancelled', updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE assignment_id = CAST(:id AS uuid)
    """), {"u": str(user_id), "id": str(assignment_id)})
    db.execute(text("""
        UPDATE aidaa_core.auditor_schedule SET status = 'cancelled'
        WHERE assignment_id = CAST(:id AS uuid) AND status = 'confirmed'
    """), {"id": str(assignment_id)})
    log_status(db, "assignment", assignment_id, a["status"], "cancelled", user_id)
    log_comment(db, "assignment", assignment_id, f"Cancelled: {reason}", user_id)
    return get_assignment(db, assignment_id)