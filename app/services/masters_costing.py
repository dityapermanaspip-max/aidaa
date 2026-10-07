import json
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.aidaa import (
    CostComponentCreate, CostComponentUpdate, CostRateCreate, CostRateUpdate, CostRateDecision,
)
from app.services.masters import _update_row, _like
from app.services.scope import get_root, assert_in_root, scoped_get

# --- ref_cost_component (scoped by root_org_id) ---

_COMP = "aidaa_core.ref_cost_component"
_COMP_COLS = ("component_id, component_code, component_name, calc_basis, sort_order, "
              "is_active, created_at, updated_at")


def list_components(db: Session, user_id: UUID, active_only: bool = True, search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_COMP_COLS} FROM {_COMP}
        WHERE root_org_id = CAST(:r AS uuid) AND (:active_only = FALSE OR is_active = TRUE)
          AND (CAST(:q AS text) IS NULL
               OR component_name ILIKE CAST(:q AS text) OR component_code ILIKE CAST(:q AS text))
        ORDER BY sort_order, component_code
    """), {"r": str(get_root(db, user_id)), "active_only": active_only, "q": _like(search)}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_component(db: Session, user_id: UUID, component_id: UUID) -> dict:
    return scoped_get(db, _COMP, _COMP_COLS, component_id, get_root(db, user_id), "Cost component")


def create_component(db: Session, payload: CostComponentCreate, user_id: UUID) -> dict:
    try:
        row = db.execute(text(f"""
            INSERT INTO {_COMP}
                (root_org_id, component_code, component_name, calc_basis, sort_order, created_by, updated_by)
            VALUES (CAST(:r AS uuid), :code, :name, :basis, :sort, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING {_COMP_COLS}
        """), {"r": str(get_root(db, user_id)), "code": payload.component_code, "name": payload.component_name,
               "basis": payload.calc_basis, "sort": payload.sort_order, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="component_code already exists")
    return dict(row._mapping)


def update_component(db: Session, component_id: UUID, payload: CostComponentUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    row = _update_row(db, _COMP, "component_id", component_id, data, set(), user_id, _COMP_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Cost component not found")
    return row


def deactivate_component(db: Session, component_id: UUID, user_id: UUID) -> dict:
    row = _update_row(db, _COMP, "component_id", component_id, {"is_active": False}, set(), user_id,
                      _COMP_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Cost component not found")
    return row


# --- ref_cost_rate (no root column, the root comes from its cost component) ---

_RATE_COLS = ("rate_id, component_id, location_id, grade, amount, effective_from, effective_to, "
              "approval_status, approved_by, approved_at, is_active, created_at, updated_at")
_RATE_COLS_R = ", ".join("r." + c.strip() for c in _RATE_COLS.split(","))
_RATE_FROM = f"FROM aidaa_core.ref_cost_rate r JOIN {_COMP} c ON c.component_id = r.component_id"


def _rate(db: Session, rate_id: UUID, root_id: UUID) -> dict:
    row = db.execute(text(f"""
        SELECT {_RATE_COLS_R}, r.created_by {_RATE_FROM}
        WHERE r.rate_id = CAST(:id AS uuid) AND c.root_org_id = CAST(:r AS uuid)
    """), {"id": str(rate_id), "r": str(root_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Cost rate not found")
    return dict(row._mapping)


def get_rate(db: Session, user_id: UUID, rate_id: UUID) -> dict:
    return _rate(db, rate_id, get_root(db, user_id))


def _check_rate_dates(start, end):
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="effective_to cannot be before effective_from")


def list_rates(db: Session, user_id: UUID, active_only: bool = True, component_id: Optional[UUID] = None,
               location_id: Optional[UUID] = None, status: Optional[str] = None,
               grade: Optional[str] = None, limit: Optional[int] = None, offset: int = 0) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_RATE_COLS_R} {_RATE_FROM}
        WHERE c.root_org_id = CAST(:r AS uuid) AND (:active_only = FALSE OR r.is_active = TRUE)
          AND (CAST(:c AS uuid) IS NULL OR r.component_id = CAST(:c AS uuid))
          AND (CAST(:l AS uuid) IS NULL OR r.location_id = CAST(:l AS uuid))
          AND (CAST(:s AS text) IS NULL OR r.approval_status = CAST(:s AS text))
          AND (CAST(:g AS text) IS NULL OR r.grade IS NULL OR r.grade @> jsonb_build_array(CAST(:g AS text)))
        ORDER BY r.effective_from DESC, r.created_at DESC, r.rate_id
        LIMIT CAST(:lim AS int) OFFSET CAST(:off AS int)
    """), {"r": str(get_root(db, user_id)), "active_only": active_only,
           "c": str(component_id) if component_id else None,
           "l": str(location_id) if location_id else None, "s": status,
           "g": grade, "lim": limit, "off": offset}).fetchall()
    return [dict(r._mapping) for r in rows]

def _gj(g):
    """grade list -> JSON text for the jsonb column. None or empty means all grades (NULL)."""
    return json.dumps(g) if g else None


def _check_overlap(db: Session, cur: dict):
    """Same component, place and grade must not have two live rates with overlapping dates."""
    clash = db.execute(text("""
        SELECT r.rate_id FROM aidaa_core.ref_cost_rate r
        WHERE r.rate_id <> CAST(:id AS uuid) AND r.component_id = CAST(:c AS uuid)
          AND r.is_active = TRUE AND r.approval_status IN ('pending','approved')
          AND r.location_id IS NOT DISTINCT FROM CAST(:l AS uuid)
          AND r.effective_from <= COALESCE(CAST(:to AS date), DATE '9999-12-31')
          AND COALESCE(r.effective_to, DATE '9999-12-31') >= CAST(:frm AS date)
          AND (r.grade IS NULL OR CAST(:g AS jsonb) IS NULL OR EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(r.grade) x WHERE CAST(:g AS jsonb) @> to_jsonb(x)))
        LIMIT 1
    """), {"id": str(cur["rate_id"]), "c": str(cur["component_id"]),
           "l": str(cur["location_id"]) if cur["location_id"] else None,
           "to": cur["effective_to"], "frm": cur["effective_from"], "g": _gj(cur["grade"])}).fetchone()
    if clash:
        raise HTTPException(status_code=409, detail="Another pending or approved rate overlaps this one (same component, place, grade and dates)")


def create_rate(db: Session, payload: CostRateCreate, user_id: UUID) -> dict:
    root = get_root(db, user_id)
    assert_in_root(db, _COMP, payload.component_id, root, "Cost component")
    if payload.location_id:
        assert_in_root(db, "aidaa_core.ref_location", payload.location_id, root, "Location")
    _check_rate_dates(payload.effective_from, payload.effective_to)
    row = db.execute(text(f"""
        INSERT INTO aidaa_core.ref_cost_rate
            (component_id, location_id, grade, amount, effective_from, effective_to,
             approval_status, created_by, updated_by)
        VALUES (CAST(:c AS uuid), CAST(:l AS uuid), CAST(:grade AS jsonb), :amt, :frm, :to, 'draft',
                CAST(:uid AS uuid), CAST(:uid AS uuid))
        RETURNING {_RATE_COLS}
    """), {"c": str(payload.component_id),
           "l": str(payload.location_id) if payload.location_id else None,
           "grade": _gj(payload.grade), "amt": payload.amount, "frm": payload.effective_from,
           "to": payload.effective_to, "uid": str(user_id)}).fetchone()
    return dict(row._mapping)


def update_rate(db: Session, rate_id: UUID, payload: CostRateUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    root = get_root(db, user_id)
    current = _rate(db, rate_id, root)
    if current["approval_status"] in ("pending", "approved"):
        raise HTTPException(status_code=409, detail="Only draft or rejected rates can be edited")
    if data.get("component_id"):
        assert_in_root(db, _COMP, data["component_id"], root, "Cost component")
    if data.get("location_id"):
        assert_in_root(db, "aidaa_core.ref_location", data["location_id"], root, "Location")
    _check_rate_dates(data.get("effective_from", current["effective_from"]),
                      data.get("effective_to", current["effective_to"]))
    if "grade" in data:
        data["grade"] = _gj(data["grade"])    
    if current["approval_status"] == "rejected":  # edited after rejection: back to draft
        data.update({"approval_status": "draft", "approved_by": None, "approved_at": None})
    return _update_row(db, "aidaa_core.ref_cost_rate", "rate_id", rate_id, data,
                       {"component_id", "location_id", "approved_by"}, user_id, _RATE_COLS)


def submit_rate(db: Session, rate_id: UUID, user_id: UUID) -> dict:
    current = _rate(db, rate_id, get_root(db, user_id))
    if current["approval_status"] != "draft":
        raise HTTPException(status_code=409, detail="Only draft rates can be submitted")
    _check_overlap(db, current)
    return _update_row(db, "aidaa_core.ref_cost_rate", "rate_id", rate_id,
                       {"approval_status": "pending"}, set(), user_id, _RATE_COLS)

def decide_rate(db: Session, rate_id: UUID, payload: CostRateDecision, user_id: UUID) -> dict:
    current = _rate(db, rate_id, get_root(db, user_id))
    if current["approval_status"] != "pending":
        raise HTTPException(status_code=409, detail="Only pending rates can be decided")
    if str(current["created_by"]) == str(user_id):
        raise HTTPException(status_code=403, detail="You cannot approve your own rate")
    row = db.execute(text(f"""
        UPDATE aidaa_core.ref_cost_rate
        SET approval_status = :st, approved_by = CAST(:uid AS uuid), approved_at = now(),
            updated_at = now(), updated_by = CAST(:uid AS uuid)
        WHERE rate_id = CAST(:id AS uuid)
        RETURNING {_RATE_COLS}
    """), {"st": payload.decision, "uid": str(user_id), "id": str(rate_id)}).fetchone()
    return dict(row._mapping)


def deactivate_rate(db: Session, rate_id: UUID, user_id: UUID) -> dict:
    _rate(db, rate_id, get_root(db, user_id))
    return _update_row(db, "aidaa_core.ref_cost_rate", "rate_id", rate_id,
                       {"is_active": False}, set(), user_id, _RATE_COLS)