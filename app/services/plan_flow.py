import json
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.plan_flow import PlanSubmit
from app.services.masters import _exists
from app.services.plans import get_plan, list_members, _assert_editable
from app.services.approval import create_task, register_handler
from app.services.logs import log_status

_VER_COLS = ("version_id, plan_id, version_no, budget_mode, total_amount, source, "
             "approval_status, approved_by, approved_at, created_at, created_by")


def get_version(db: Session, version_id: UUID) -> dict:
    row = db.execute(text(f"""
        SELECT {_VER_COLS}, snapshot FROM aidaa_core.audit_plan_version
        WHERE version_id = CAST(:id AS uuid)
    """), {"id": str(version_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Plan version not found")
    return dict(row._mapping)


def list_versions(db: Session, plan_id: UUID) -> list[dict]:
    _exists(db, "aidaa_core.audit_plan", "plan_id", plan_id, "Plan")
    rows = db.execute(text(f"""
        SELECT {_VER_COLS} FROM aidaa_core.audit_plan_version
        WHERE plan_id = CAST(:p AS uuid) ORDER BY version_no DESC
    """), {"p": str(plan_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def submit_plan(db: Session, plan_id: UUID, payload: PlanSubmit, user_id: UUID) -> dict:
    plan = get_plan(db, plan_id)
    _assert_editable(plan)  # also blocks a second submit while one is pending

    members = list_members(db, plan_id)
    if not members:
        raise HTTPException(status_code=400, detail="Plan needs at least one team member before submit")

    next_no = db.execute(text("""
        SELECT COALESCE(MAX(version_no), 0) + 1 AS n FROM aidaa_core.audit_plan_version
        WHERE plan_id = CAST(:p AS uuid)
    """), {"p": str(plan_id)}).fetchone().n

    lines = []
    if plan["budget_mode"] == "detailed":
        rows = db.execute(text("""
            SELECT line_id, component_id, location_id, auditor_id, rate_id, quantity, unit_rate,
                   amount, basis, notes
            FROM aidaa_core.budget_line
            WHERE plan_id = CAST(:p AS uuid) AND version_no = :v ORDER BY created_at
        """), {"p": str(plan_id), "v": next_no}).fetchall()
        lines = [dict(r._mapping) for r in rows]
        if not lines:
            raise HTTPException(status_code=400,
                                detail=f"Detailed budget needs lines with version_no {next_no}")
        total = sum(l["amount"] for l in lines)
    else:
        total = plan["lumpsum_amount"]

    plan_snap = {k: v for k, v in plan.items() if k != "has_pending_version"}
    snapshot = {"plan": plan_snap, "members": members, "budget_lines": lines}

    row = db.execute(text("""
        INSERT INTO aidaa_core.audit_plan_version
            (plan_id, version_no, budget_mode, total_amount, snapshot, source, created_by)
        VALUES (CAST(:p AS uuid), :v, :bm, :total, CAST(:snap AS jsonb), 'manual', CAST(:uid AS uuid))
        RETURNING version_id
    """), {"p": str(plan_id), "v": next_no, "bm": plan["budget_mode"], "total": total,
           "snap": json.dumps(snapshot, default=str), "uid": str(user_id)}).fetchone()

    db.execute(text("""
        UPDATE aidaa_core.audit_plan
        SET current_version_no = :v, updated_at = now(), updated_by = CAST(:uid AS uuid)
        WHERE plan_id = CAST(:p AS uuid)
    """), {"v": next_no, "uid": str(user_id), "p": str(plan_id)})

    create_task(db, "plan", row.version_id, 1, user_id, due_date=payload.due_date)
    log_status(db, "plan_version", row.version_id, None, "pending", user_id)
    return get_version(db, row.version_id)


def _on_plan_task(db: Session, task: dict, user_id: UUID):
    """Runs after every decision on a 'plan' task (record_id = version id)."""
    version = get_version(db, task["record_id"])
    if version["approval_status"] != "pending":
        return

    if task["status"] != "approved":  # rejected or returned: plan unlocks, next submit = new version
        db.execute(text("""
            UPDATE aidaa_core.audit_plan_version SET approval_status = 'rejected'
            WHERE version_id = CAST(:id AS uuid)
        """), {"id": str(version["version_id"])})
        log_status(db, "plan_version", version["version_id"], "pending", "rejected", user_id)
        return

    if task["step_no"] == 1:  # Finance verified, now the Board. Requester stays the submitter.
        create_task(db, "plan", version["version_id"], 2, version["created_by"])
        return

    # step 2: Board approved
    db.execute(text("""
        UPDATE aidaa_core.audit_plan_version
        SET approval_status = 'approved', approved_by = CAST(:u AS uuid), approved_at = now()
        WHERE version_id = CAST(:id AS uuid)
    """), {"u": str(user_id), "id": str(version["version_id"])})
    plan = get_plan(db, version["plan_id"])
    new_status = {"planned": "approved", "ai_planned": "ai_approved"}.get(plan["status"], plan["status"])
    db.execute(text("""
        UPDATE aidaa_core.audit_plan
        SET status = :s, updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE plan_id = CAST(:p AS uuid)
    """), {"s": new_status, "u": str(user_id), "p": str(plan["plan_id"])})
    log_status(db, "plan", plan["plan_id"], plan["status"], new_status, user_id)
    log_status(db, "plan_version", version["version_id"], "pending", "approved", user_id)


register_handler("plan", _on_plan_task)