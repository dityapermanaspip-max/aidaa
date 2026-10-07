from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.aidaa import PkaCreate, PkaUpdate, ProcedureCreate, ProcedureUpdate
from app.services.masters import _update_row, _like
from app.services.scope import get_root, assert_in_root

# --- library_pka (scoped by root_org_id, hours are calculated from active procedures) ---

_PKA = "aidaa_core.library_pka"
_PKA_COLS = ("k.library_pka_id, k.type_id, k.pka_code, k.title, k.objective, "
             "k.is_active, k.created_at, k.updated_at")
_PKA_SQL = f"""
    SELECT {_PKA_COLS},
           COALESCE((SELECT SUM(p.estimated_hours) FROM aidaa_core.library_procedure p
                     WHERE p.library_pka_id = k.library_pka_id AND p.is_active = TRUE), 0) AS procedure_hours
    FROM {_PKA} k
"""


def _pka(db: Session, root_id: UUID, library_pka_id: UUID) -> dict:
    row = db.execute(text(f"{_PKA_SQL} WHERE k.library_pka_id = CAST(:id AS uuid) AND k.root_org_id = CAST(:r AS uuid)"),
                     {"id": str(library_pka_id), "r": str(root_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Library PKA not found")
    return dict(row._mapping)


def list_pka(db: Session, user_id: UUID, active_only: bool = True, type_id: Optional[UUID] = None,
             search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""{_PKA_SQL}
        WHERE k.root_org_id = CAST(:r AS uuid) AND (:active_only = FALSE OR k.is_active = TRUE)
          AND (CAST(:t AS uuid) IS NULL OR k.type_id = CAST(:t AS uuid))
          AND (CAST(:q AS text) IS NULL
               OR k.title ILIKE CAST(:q AS text) OR k.pka_code ILIKE CAST(:q AS text))
        ORDER BY k.pka_code
    """), {"r": str(get_root(db, user_id)), "active_only": active_only,
           "t": str(type_id) if type_id else None, "q": _like(search)}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_pka(db: Session, user_id: UUID, library_pka_id: UUID) -> dict:
    return _pka(db, get_root(db, user_id), library_pka_id)


def create_pka(db: Session, payload: PkaCreate, user_id: UUID) -> dict:
    root = get_root(db, user_id)
    assert_in_root(db, "aidaa_core.ref_audit_type", payload.type_id, root, "Audit type")
    try:
        row = db.execute(text(f"""
            INSERT INTO {_PKA} (root_org_id, type_id, pka_code, title, objective, created_by, updated_by)
            VALUES (CAST(:r AS uuid), CAST(:t AS uuid), :code, :title, :obj, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING library_pka_id
        """), {"r": str(root), "t": str(payload.type_id), "code": payload.pka_code, "title": payload.title,
               "obj": payload.objective, "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="pka_code already exists")
    return _pka(db, root, row.library_pka_id)


def update_pka(db: Session, library_pka_id: UUID, payload: PkaUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    root = get_root(db, user_id)
    if data.get("type_id"):
        assert_in_root(db, "aidaa_core.ref_audit_type", data["type_id"], root, "Audit type")
    row = _update_row(db, _PKA, "library_pka_id", library_pka_id, data, {"type_id"}, user_id,
                      "library_pka_id", root)
    if not row:
        raise HTTPException(status_code=404, detail="Library PKA not found")
    return _pka(db, root, library_pka_id)


def deactivate_pka(db: Session, library_pka_id: UUID, user_id: UUID) -> dict:
    root = get_root(db, user_id)
    row = _update_row(db, _PKA, "library_pka_id", library_pka_id, {"is_active": False}, set(), user_id,
                      "library_pka_id", root)
    if not row:
        raise HTTPException(status_code=404, detail="Library PKA not found")
    return _pka(db, root, library_pka_id)


# --- library_procedure (scoped through its PKA) ---

_PROC_COLS = ("procedure_id, library_pka_id, step_no, procedure_text, expected_evidence, "
              "estimated_hours, is_active, created_at, updated_at")


def _assert_procedure_in_root(db: Session, procedure_id: UUID, root_id: UUID):
    row = db.execute(text("""
        SELECT 1 FROM aidaa_core.library_procedure p
        JOIN aidaa_core.library_pka k ON k.library_pka_id = p.library_pka_id
        WHERE p.procedure_id = CAST(:p AS uuid) AND k.root_org_id = CAST(:r AS uuid)
    """), {"p": str(procedure_id), "r": str(root_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Procedure not found")


def list_procedures(db: Session, user_id: UUID, library_pka_id: UUID, active_only: bool = True) -> list[dict]:
    _pka(db, get_root(db, user_id), library_pka_id)
    rows = db.execute(text(f"""
        SELECT {_PROC_COLS} FROM aidaa_core.library_procedure
        WHERE library_pka_id = CAST(:p AS uuid) AND (:active_only = FALSE OR is_active = TRUE)
        ORDER BY step_no
    """), {"p": str(library_pka_id), "active_only": active_only}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_procedure(db: Session, library_pka_id: UUID, payload: ProcedureCreate, user_id: UUID) -> dict:
    _pka(db, get_root(db, user_id), library_pka_id)
    try:
        row = db.execute(text(f"""
            INSERT INTO aidaa_core.library_procedure
                (library_pka_id, step_no, procedure_text, expected_evidence, estimated_hours,
                 created_by, updated_by)
            VALUES (
                CAST(:p AS uuid),
                COALESCE(CAST(:step AS int),
                         (SELECT COALESCE(MAX(step_no), 0) + 1 FROM aidaa_core.library_procedure
                          WHERE library_pka_id = CAST(:p AS uuid))),
                :txt, :ev, :hrs, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING {_PROC_COLS}
        """), {"p": str(library_pka_id), "step": payload.step_no, "txt": payload.procedure_text,
               "ev": payload.expected_evidence, "hrs": payload.estimated_hours,
               "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="step_no already used in this PKA")
    return dict(row._mapping)


def update_procedure(db: Session, procedure_id: UUID, payload: ProcedureUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    _assert_procedure_in_root(db, procedure_id, get_root(db, user_id))
    try:
        row = _update_row(db, "aidaa_core.library_procedure", "procedure_id", procedure_id, data,
                          set(), user_id, _PROC_COLS)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="step_no already used in this PKA")
    if not row:
        raise HTTPException(status_code=404, detail="Procedure not found")
    return row


def deactivate_procedure(db: Session, procedure_id: UUID, user_id: UUID) -> dict:
    _assert_procedure_in_root(db, procedure_id, get_root(db, user_id))
    row = _update_row(db, "aidaa_core.library_procedure", "procedure_id", procedure_id,
                      {"is_active": False}, set(), user_id, _PROC_COLS)
    if not row:
        raise HTTPException(status_code=404, detail="Procedure not found")
    return row