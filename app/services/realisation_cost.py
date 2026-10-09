from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.realisation import CostCreate, CostUpdate, CostOut
from app.services.masters import _update_row
from app.services.logs import log_comment
from app.services.realisation_common import assert_realisable, assert_member, assert_cost_ref, username_map

_COST_COLS = ("rc_id, assignment_id, auditor_id, component_id, location_id, quantity, unit_rate, "
              "amount, cost_date, evidence_url, evidence_name, notes, created_at, updated_at")
_COST_COLS_Q = ", ".join(f"rc.{c}" for c in _COST_COLS.split(", "))


def _out(row, names: dict) -> dict:
    d = dict(row) if isinstance(row, dict) else dict(row._mapping)
    d["username"] = names.get(d["auditor_id"])
    d.setdefault("component_code", "")
    d.setdefault("component_name", "")
    return CostOut(**d).model_dump()


def _get(db: Session, rc_id: UUID) -> dict:
    row = db.execute(text(f"""
        SELECT {_COST_COLS} FROM aidaa_core.realisation_cost WHERE rc_id = CAST(:id AS uuid)
    """), {"id": str(rc_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Real cost not found")
    return dict(row._mapping)


def list_costs(db: Session, assignment_id: UUID) -> list[dict]:
    assert_realisable(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {_COST_COLS_Q}, c.component_code, c.component_name
        FROM aidaa_core.realisation_cost rc
        JOIN aidaa_core.ref_cost_component c ON c.component_id = rc.component_id
        WHERE rc.assignment_id = CAST(:a AS uuid) ORDER BY rc.cost_date, rc.created_at
    """), {"a": str(assignment_id)}).fetchall()
    names = username_map(db, assignment_id)
    return [_out(dict(r._mapping), names) for r in rows]


def create_cost(db: Session, assignment_id: UUID, payload: CostCreate, user_id: UUID) -> dict:
    assert_realisable(db, assignment_id)
    assert_member(db, assignment_id, payload.auditor_id)
    assert_cost_ref(db, user_id, payload.component_id, payload.location_id)
    row = db.execute(text("""
        INSERT INTO aidaa_core.realisation_cost
            (assignment_id, auditor_id, component_id, location_id, quantity, unit_rate,
             cost_date, evidence_url, evidence_name, notes, created_by, updated_by)
        VALUES (CAST(:a AS uuid), CAST(:au AS uuid), CAST(:c AS uuid), CAST(:l AS uuid),
                :q, :r, :d, :eu, :en, :n, CAST(:u AS uuid), CAST(:u AS uuid))
        RETURNING rc_id
    """), {"a": str(assignment_id), "au": str(payload.auditor_id), "c": str(payload.component_id),
           "l": str(payload.location_id) if payload.location_id else None, "q": payload.quantity,
           "r": payload.unit_rate, "d": payload.cost_date, "eu": payload.evidence_url,
           "en": payload.evidence_name, "n": payload.notes, "u": str(user_id)}).fetchone()
    log_comment(db, "realisation_cost", row.rc_id,
                f"Real cost {payload.unit_rate} x {payload.quantity} on {payload.cost_date}", user_id)
    return _out(_get(db, row.rc_id), username_map(db, assignment_id))


def update_cost(db: Session, rc_id: UUID, payload: CostUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    current = _get(db, rc_id)
    assert_realisable(db, current["assignment_id"])
    if data.get("auditor_id"):
        assert_member(db, current["assignment_id"], data["auditor_id"])
    if data.get("component_id") or data.get("location_id"):
        assert_cost_ref(db, user_id, data.get("component_id", current["component_id"]),
                        data.get("location_id", current["location_id"]))
    _update_row(db, "aidaa_core.realisation_cost", "rc_id", rc_id, data,
                {"auditor_id", "component_id", "location_id"}, user_id, "rc_id")
    log_comment(db, "realisation_cost", rc_id, "Real cost updated", user_id)
    return _out(_get(db, rc_id), username_map(db, current["assignment_id"]))


def delete_cost(db: Session, rc_id: UUID, user_id: UUID) -> dict:
    current = _get(db, rc_id)
    assert_realisable(db, current["assignment_id"])
    db.execute(text("DELETE FROM aidaa_core.realisation_cost WHERE rc_id = CAST(:id AS uuid)"),
               {"id": str(rc_id)})
    log_comment(db, "realisation_cost", rc_id, "Real cost deleted", user_id)
    return {"deleted": True}