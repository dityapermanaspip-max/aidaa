from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.aidaa import (
    LocationCreate, LocationUpdate, AuditTypeCreate, AuditTypeUpdate, UnitCreate, UnitUpdate,
)
from app.services.org_options import assert_client_org
from app.services.scope import get_root, assert_in_root, scoped_get


# --- shared helpers (the other master services import these) ---

def _exists(db: Session, table: str, pk: str, value: UUID, label: str):
    row = db.execute(
        text(f"SELECT 1 FROM {table} WHERE {pk} = CAST(:v AS uuid)"), {"v": str(value)}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def _like(search: Optional[str]) -> Optional[str]:
    return f"%{search}%" if search else None


def _update_row(db: Session, table: str, pk: str, pk_value: UUID, data: dict,
                uuid_cols: set, user_id: UUID, cols: str, root_id: Optional[UUID] = None) -> Optional[dict]:
    # table, pk, cols are internal constants; keys come from Pydantic models only
    sets, params = [], {"id": str(pk_value), "uid": str(user_id)}
    for key, value in data.items():
        if key in uuid_cols:
            sets.append(f"{key} = CAST(:{key} AS uuid)")
            params[key] = str(value) if value else None
        else:
            sets.append(f"{key} = :{key}")
            params[key] = value
    sets += ["updated_at = now()", "updated_by = CAST(:uid AS uuid)"]
    scope = ""
    if root_id is not None:  # tables with root_org_id: a row of another root is simply not found
        scope = " AND root_org_id = CAST(:_root AS uuid)"
        params["_root"] = str(root_id)
    row = db.execute(text(f"""
        UPDATE {table} SET {", ".join(sets)}
        WHERE {pk} = CAST(:id AS uuid){scope} RETURNING {cols}
    """), params).fetchone()
    return dict(row._mapping) if row else None


# --- ref_location ---

_LOC = "aidaa_core.ref_location"
_LOC_COLS = ("location_id, location_code, location_name, country, province, city, address, "
             "is_active, created_at, updated_at")


def list_locations(db: Session, user_id: UUID, active_only: bool = True, search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_LOC_COLS} FROM {_LOC}
        WHERE root_org_id = CAST(:r AS uuid) AND (:active_only = FALSE OR is_active = TRUE)
          AND (CAST(:q AS text) IS NULL
               OR location_name ILIKE CAST(:q AS text) OR location_code ILIKE CAST(:q AS text)
               OR city ILIKE CAST(:q AS text) OR province ILIKE CAST(:q AS text))
        ORDER BY country, province, city, location_code
    """), {"r": str(get_root(db, user_id)), "active_only": active_only, "q": _like(search)}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_location(db: Session, user_id: UUID, location_id: UUID) -> dict:
    return scoped_get(db, _LOC, _LOC_COLS, location_id, get_root(db, user_id), "Location")


def create_location(db: Session, payload: LocationCreate, user_id: UUID) -> dict:
    try:
        row = db.execute(text(f"""
            INSERT INTO {_LOC}
                (root_org_id, location_code, location_name, country, province, city, address, created_by, updated_by)
            VALUES (CAST(:r AS uuid), :code, :name, :country, :prov, :city, :addr, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING {_LOC_COLS}
        """), {"r": str(get_root(db, user_id)), "code": payload.location_code, "name": payload.location_name,
               "country": payload.country, "prov": payload.province, "city": payload.city,
               "addr": payload.address, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="location_code already exists")
    return dict(row._mapping)


def update_location(db: Session, location_id: UUID, payload: LocationUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    row = _update_row(db, _LOC, "location_id", location_id, data, set(), user_id, _LOC_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")
    return row


def deactivate_location(db: Session, location_id: UUID, user_id: UUID) -> dict:
    row = _update_row(db, _LOC, "location_id", location_id, {"is_active": False}, set(), user_id,
                      _LOC_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")
    return row


# --- ref_audit_type ---

_TYPE = "aidaa_core.ref_audit_type"
_TYPE_COLS = "type_id, type_code, type_name, description, is_active, created_at, updated_at"


def list_audit_types(db: Session, user_id: UUID, active_only: bool = True, search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_TYPE_COLS} FROM {_TYPE}
        WHERE root_org_id = CAST(:r AS uuid) AND (:active_only = FALSE OR is_active = TRUE)
          AND (CAST(:q AS text) IS NULL
               OR type_name ILIKE CAST(:q AS text) OR type_code ILIKE CAST(:q AS text))
        ORDER BY type_code
    """), {"r": str(get_root(db, user_id)), "active_only": active_only, "q": _like(search)}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_audit_type(db: Session, user_id: UUID, type_id: UUID) -> dict:
    return scoped_get(db, _TYPE, _TYPE_COLS, type_id, get_root(db, user_id), "Audit type")


def create_audit_type(db: Session, payload: AuditTypeCreate, user_id: UUID) -> dict:
    try:
        row = db.execute(text(f"""
            INSERT INTO {_TYPE} (root_org_id, type_code, type_name, description, created_by, updated_by)
            VALUES (CAST(:r AS uuid), :code, :name, :descr, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING {_TYPE_COLS}
        """), {"r": str(get_root(db, user_id)), "code": payload.type_code, "name": payload.type_name,
               "descr": payload.description, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="type_code already exists")
    return dict(row._mapping)


def update_audit_type(db: Session, type_id: UUID, payload: AuditTypeUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    row = _update_row(db, _TYPE, "type_id", type_id, data, set(), user_id, _TYPE_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Audit type not found")
    return row


def deactivate_audit_type(db: Session, type_id: UUID, user_id: UUID) -> dict:
    row = _update_row(db, _TYPE, "type_id", type_id, {"is_active": False}, set(), user_id,
                      _TYPE_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Audit type not found")
    return row


# --- ref_auditable_unit (scoped through root_org_id, the root of the tagged IAM organisation) ---

_UNIT_COLS = ("unit_id, org_id, unit_code, unit_name, unit_type, location_id, "
              "risk_score, is_active, created_at, updated_at")
_UNIT_COLS_U = ", ".join("u." + c.strip() for c in _UNIT_COLS.split(","))
_UNIT_FROM = """
    FROM aidaa_core.ref_auditable_unit u
    WHERE u.root_org_id = CAST(:r AS uuid)
"""


def _check_unit_refs(db: Session, user_id: UUID, org_id: Optional[UUID], location_id: Optional[UUID],
                     unit_id: Optional[UUID] = None):
    if org_id:
        assert_client_org(db, user_id, org_id)
        dup = db.execute(text("""
            SELECT unit_code FROM aidaa_core.ref_auditable_unit
            WHERE org_id = CAST(:o AS uuid) AND (CAST(:me AS uuid) IS NULL OR unit_id <> CAST(:me AS uuid))
        """), {"o": str(org_id), "me": str(unit_id) if unit_id else None}).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail=f"This organization is already tagged as unit {dup.unit_code}")
    if location_id:
        assert_in_root(db, _LOC, location_id, get_root(db, user_id), "Location")


def list_units(db: Session, user_id: UUID, active_only: bool = True, search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_UNIT_COLS_U} {_UNIT_FROM}
          AND (:active_only = FALSE OR u.is_active = TRUE)
          AND (CAST(:q AS text) IS NULL
               OR u.unit_name ILIKE CAST(:q AS text) OR u.unit_code ILIKE CAST(:q AS text))
        ORDER BY u.unit_code
    """), {"r": str(get_root(db, user_id)), "active_only": active_only, "q": _like(search)}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_unit(db: Session, user_id: UUID, unit_id: UUID) -> dict:
    row = db.execute(text(f"SELECT {_UNIT_COLS_U} {_UNIT_FROM} AND u.unit_id = CAST(:id AS uuid)"),
                     {"r": str(get_root(db, user_id)), "id": str(unit_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Unit not found")
    return dict(row._mapping)


def create_unit(db: Session, payload: UnitCreate, user_id: UUID) -> dict:
    _check_unit_refs(db, user_id, payload.org_id, payload.location_id)
    try:
        row = db.execute(text(f"""
            INSERT INTO aidaa_core.ref_auditable_unit
                (root_org_id, org_id, unit_code, unit_name, unit_type, location_id, risk_score, created_by, updated_by)
            VALUES (CAST(:r AS uuid), CAST(:org AS uuid), :code, :name, :utype, CAST(:loc AS uuid), :risk,
                    CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING {_UNIT_COLS}
        """), {
            "r": str(get_root(db, user_id)),
            "org": str(payload.org_id) if payload.org_id else None,
            "code": payload.unit_code, "name": payload.unit_name, "utype": payload.unit_type,
            "loc": str(payload.location_id) if payload.location_id else None,
            "risk": payload.risk_score, "uid": str(user_id),
        }).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="unit_code already exists in this root organization")
    return dict(row._mapping)


def update_unit(db: Session, unit_id: UUID, payload: UnitUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "org_id" in data and data["org_id"] is None:
        raise HTTPException(status_code=400, detail="org_id cannot be cleared")
    get_unit(db, user_id, unit_id)  # 404 when the unit belongs to another root
    _check_unit_refs(db, user_id, data.get("org_id"), data.get("location_id"), unit_id)
    row = _update_row(db, "aidaa_core.ref_auditable_unit", "unit_id", unit_id, data,
                      {"org_id", "location_id"}, user_id, _UNIT_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Unit not found")
    return row


def deactivate_unit(db: Session, unit_id: UUID, user_id: UUID) -> dict:
    get_unit(db, user_id, unit_id)
    row = _update_row(db, "aidaa_core.ref_auditable_unit", "unit_id", unit_id,
                      {"is_active": False}, set(), user_id, _UNIT_COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Unit not found")
    return row