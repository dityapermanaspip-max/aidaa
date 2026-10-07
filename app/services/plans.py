from typing import Optional, List
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.aidaa import (
    PlanCreate, PlanUpdate, PlanMemberCreate, PlanMemberUpdate,
)
from app.services.masters import _exists, _update_row
from app.services.logs import log_edit, log_status, log_team
from app.services.conflict import check_conflict
from app.services.org_options import assert_owner_org
from app.services.scope import get_root, assert_in_root
from app.services.unit_links import (
    clean_units, check_units, unit_org_ids, unit_ids_for, unit_ids_of, sync_units,
)

_PLAN_COLS = ("plan_id, plan_no, fiscal_year, owner_org_id, unit_id, type_id, period_start, "
              "period_end, planned_auditors, planned_days, budget_mode, lumpsum_amount, status, "
              "current_version_no, is_closed, notes, is_active, created_at, updated_at")

_EDITABLE = ("planned", "ai_planned")


def _check_dates(start, end):
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="period_end cannot be before period_start")


def _assert_editable(plan: dict):
    if plan["status"] not in _EDITABLE or plan["is_closed"]:
        raise HTTPException(status_code=409, detail="Plan is approved or closed and can no longer be edited")
    if plan.get("has_pending_version"):
        raise HTTPException(status_code=409, detail="Plan is under approval review and cannot be edited")


def _recheck_members(db: Session, plan_id: UUID, org_ids: list, user_id: UUID):
    """New units must not create a conflict of interest for people already on the plan team."""
    members = db.execute(text("SELECT auditor_id FROM aidaa_core.audit_plan_member WHERE plan_id = CAST(:p AS uuid)"),
                         {"p": str(plan_id)}).fetchall()
    for m in members:
        for org_id in org_ids:
            check_conflict(db, m.auditor_id, org_id, user_id, plan_id=plan_id)


# --- audit_plan ---

def get_plan(db: Session, plan_id: UUID) -> dict:
    row = db.execute(
        text(f"""SELECT {_PLAN_COLS},
                 EXISTS (SELECT 1 FROM aidaa_core.audit_plan_version v
                         WHERE v.plan_id = audit_plan.plan_id
                           AND v.approval_status = 'pending') AS has_pending_version
                 FROM aidaa_core.audit_plan WHERE plan_id = CAST(:id AS uuid)"""),
        {"id": str(plan_id)},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = dict(row._mapping)
    plan["unit_ids"] = unit_ids_of(db, "plan", plan_id)
    return plan


def list_plans(db: Session, org_ids: Optional[List[UUID]], active_only: bool = True,
               fiscal_year: Optional[int] = None, status: Optional[str] = None,
               search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_PLAN_COLS} FROM aidaa_core.audit_plan
        WHERE (:all_orgs OR owner_org_id = ANY(CAST(:orgs AS uuid[])))
          AND (:active_only = FALSE OR is_active = TRUE)
          AND (CAST(:fy AS int) IS NULL OR fiscal_year = CAST(:fy AS int))
          AND (CAST(:st AS text) IS NULL OR status = CAST(:st AS text))
          AND (CAST(:q AS text) IS NULL OR plan_no ILIKE CAST(:q AS text))
        ORDER BY fiscal_year DESC, plan_no
    """), {"all_orgs": org_ids is None, "orgs": [str(o) for o in (org_ids or [])],
           "active_only": active_only, "fy": fiscal_year, "st": status,
           "q": f"%{search}%" if search else None}).fetchall()
    plans = [dict(r._mapping) for r in rows]
    units = unit_ids_for(db, "plan", [p["plan_id"] for p in plans])
    for p in plans:
        p["unit_ids"] = units.get(str(p["plan_id"]), [])
    return plans


def create_plan(db: Session, payload: PlanCreate, user_id: UUID) -> dict:
    assert_owner_org(db, user_id, payload.owner_org_id)
    unit_ids = clean_units(payload.unit_id, payload.extra_unit_ids)
    check_units(db, unit_ids)
    assert_in_root(db, "aidaa_core.ref_audit_type", payload.type_id, get_root(db, user_id), "Audit type")    
    _check_dates(payload.period_start, payload.period_end)
    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.audit_plan
                (plan_no, fiscal_year, owner_org_id, unit_id, type_id, period_start, period_end,
                 planned_auditors, planned_days, budget_mode, lumpsum_amount, notes,
                 created_by, updated_by)
            VALUES (:no, :fy, CAST(:org AS uuid), CAST(:unit AS uuid), CAST(:type AS uuid),
                    :ps, :pe, :pa, :pd, :bm, :lump, :notes, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING plan_id, status
        """), {"no": payload.plan_no, "fy": payload.fiscal_year, "org": str(payload.owner_org_id),
               "unit": str(payload.unit_id), "type": str(payload.type_id),
               "ps": payload.period_start, "pe": payload.period_end,
               "pa": payload.planned_auditors, "pd": payload.planned_days,
               "bm": payload.budget_mode, "lump": payload.lumpsum_amount,
               "notes": payload.notes, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="plan_no already exists")
    sync_units(db, "plan", row.plan_id, unit_ids, user_id)
    log_status(db, "plan", row.plan_id, None, row.status, user_id)
    return get_plan(db, row.plan_id)


def update_plan(db: Session, plan_id: UUID, payload: PlanUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    extras = data.pop("extra_unit_ids", None)
    if not data and extras is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    for key in ("unit_id", "type_id"):
        if key in data and data[key] is None:
            raise HTTPException(status_code=400, detail=f"{key} cannot be cleared")
    current = get_plan(db, plan_id)
    _assert_editable(current)
    if data.get("type_id"):
        assert_in_root(db, "aidaa_core.ref_audit_type", data["type_id"], get_root(db, user_id), "Audit type")
    _check_dates(data.get("period_start", current["period_start"]),
                 data.get("period_end", current["period_end"]))

    old_units = [str(u) for u in current["unit_ids"]]
    units_touched = "unit_id" in data or extras is not None
    new_units = old_units
    if units_touched:
        if extras is None:  # only the primary unit changed, keep the existing extras
            extras = [u for u in old_units if u != str(current["unit_id"])]
        new_units = clean_units(data.get("unit_id", current["unit_id"]), extras)
        added = [u for u in new_units if u not in old_units]
        if added:
            check_units(db, added)
            _recheck_members(db, plan_id, unit_org_ids(db, added), user_id)

    _update_row(db, "aidaa_core.audit_plan", "plan_id", plan_id, data,
                {"unit_id", "type_id"}, user_id, "plan_id")
    if units_touched:
        sync_units(db, "plan", plan_id, new_units, user_id)
        if set(new_units) != set(old_units):
            log_edit(db, "audit_plan", plan_id, "unit_ids", old_units, new_units, user_id)
    for key, new in data.items():
        if str(current[key]) != str(new):
            log_edit(db, "audit_plan", plan_id, key, current[key], new, user_id)
    return get_plan(db, plan_id)


def deactivate_plan(db: Session, plan_id: UUID, user_id: UUID) -> dict:
    current = get_plan(db, plan_id)
    _assert_editable(current)
    _update_row(db, "aidaa_core.audit_plan", "plan_id", plan_id,
                {"is_active": False}, set(), user_id, "plan_id")
    return get_plan(db, plan_id)


# --- audit_plan_member ---

_MEM_SQL = """
    SELECT m.plan_member_id, m.plan_id, m.auditor_id, u.username, m.assignment_role,
           m.is_budget_drafter, m.created_at
    FROM aidaa_core.audit_plan_member m
    JOIN aidaa_core.auditor a ON a.auditor_id = m.auditor_id
    JOIN iam.users u ON u.user_id = a.user_id
"""


def list_members(db: Session, plan_id: UUID) -> list[dict]:
    _exists(db, "aidaa_core.audit_plan", "plan_id", plan_id, "Plan")
    rows = db.execute(text(f"{_MEM_SQL} WHERE m.plan_id = CAST(:p AS uuid) ORDER BY m.created_at"),
                      {"p": str(plan_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def _get_member(db: Session, plan_id: UUID, plan_member_id: UUID) -> dict:
    row = db.execute(text(f"""{_MEM_SQL}
        WHERE m.plan_member_id = CAST(:m AS uuid) AND m.plan_id = CAST(:p AS uuid)
    """), {"m": str(plan_member_id), "p": str(plan_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Plan member not found")
    return dict(row._mapping)


def _overlap_warnings(db: Session, plan: dict, auditor_id: UUID) -> list[str]:
    rows = db.execute(text("""
        SELECT p.plan_no FROM aidaa_core.audit_plan_member m
        JOIN aidaa_core.audit_plan p ON p.plan_id = m.plan_id
        WHERE m.auditor_id = CAST(:a AS uuid) AND m.plan_id <> CAST(:p AS uuid)
          AND p.is_active = TRUE AND p.status <> 'finished'
          AND p.period_start <= CAST(:e AS date) AND p.period_end >= CAST(:s AS date)
    """), {"a": str(auditor_id), "p": str(plan["plan_id"]),
           "s": plan["period_start"], "e": plan["period_end"]}).fetchall()
    return [f"Auditor also planned in {r.plan_no} during an overlapping period" for r in rows]


def add_member(db: Session, plan_id: UUID, payload: PlanMemberCreate, user_id: UUID) -> dict:
    plan = get_plan(db, plan_id)
    _assert_editable(plan)

    aud = db.execute(text("""
        SELECT auditor_id, user_id, status, is_active FROM aidaa_core.auditor
        WHERE auditor_id = CAST(:a AS uuid)
    """), {"a": str(payload.auditor_id)}).fetchone()
    if not aud:
        raise HTTPException(status_code=404, detail="Auditor not found")
    if not aud.is_active or aud.status != "active":
        raise HTTPException(status_code=409, detail="Auditor is not active")

    holds = db.execute(text("""
        SELECT 1 FROM iam.active_user_roles m JOIN iam.roles r ON r.role_id = m.role_id
        WHERE m.user_id = CAST(:u AS uuid) AND r.role_code = 'AIDAA.AUDITOR' AND r.is_active = TRUE
        LIMIT 1
    """), {"u": str(aud.user_id)}).fetchone()
    if not holds:
        raise HTTPException(status_code=409, detail="Person does not hold the AIDAA.AUDITOR role")

    # conflict of interest against EVERY unit of the plan (usually just one)
    for org_id in unit_org_ids(db, plan["unit_ids"]) or [None]:
        check_conflict(db, payload.auditor_id, org_id, user_id, plan_id=plan_id)

    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.audit_plan_member
                (plan_id, auditor_id, assignment_role, is_budget_drafter, created_by)
            VALUES (CAST(:p AS uuid), CAST(:a AS uuid), :r, :d, CAST(:uid AS uuid))
            RETURNING plan_member_id
        """), {"p": str(plan_id), "a": str(payload.auditor_id), "r": payload.assignment_role,
               "d": payload.is_budget_drafter, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Auditor is already a member of this plan")

    log_team(db, "add", user_id, plan_id=plan_id, auditor_id=payload.auditor_id,
             role=payload.assignment_role)
    out = _get_member(db, plan_id, row.plan_member_id)
    out["warnings"] = _overlap_warnings(db, plan, payload.auditor_id)
    return out


def update_member(db: Session, plan_id: UUID, plan_member_id: UUID,
                  payload: PlanMemberUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    _assert_editable(get_plan(db, plan_id))
    current = _get_member(db, plan_id, plan_member_id)
    sets, params = [], {"id": str(plan_member_id)}
    for key, value in data.items():  # keys come from the Pydantic model only
        sets.append(f"{key} = :{key}")
        params[key] = value
    db.execute(text(f"UPDATE aidaa_core.audit_plan_member SET {', '.join(sets)} "
                    f"WHERE plan_member_id = CAST(:id AS uuid)"), params)
    if "assignment_role" in data and data["assignment_role"] != current["assignment_role"]:
        log_team(db, "role_change", user_id, plan_id=plan_id, auditor_id=current["auditor_id"],
                 role=data["assignment_role"], reason=f"from {current['assignment_role']}")
    return _get_member(db, plan_id, plan_member_id)


def remove_member(db: Session, plan_id: UUID, plan_member_id: UUID, user_id: UUID):
    _assert_editable(get_plan(db, plan_id))
    current = _get_member(db, plan_id, plan_member_id)
    db.execute(text("DELETE FROM aidaa_core.audit_plan_member WHERE plan_member_id = CAST(:id AS uuid)"),
               {"id": str(plan_member_id)})
    log_team(db, "remove", user_id, plan_id=plan_id, auditor_id=current["auditor_id"],
             role=current["assignment_role"])