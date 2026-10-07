from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.funding import FundingCreate, FundingUpdate, FundingDocCreate
from app.services.masters import _update_row, _like
from app.services.scope import get_root, assert_in_root, scoped_get

# --- ref_funding_source (master, scoped by root_org_id) ---
# The per-assignment allocation lives in assignment_funding.py, not here.

_SRC = "aidaa_core.ref_funding_source"
_COLS = ("funding_id, funding_code, funding_name, fiscal_year, funding_type, ceiling_amount, "
         "is_active, created_at, updated_at")


def list_funding(db: Session, user_id: UUID, active_only: bool = True, fiscal_year: Optional[int] = None,
                 funding_type: Optional[str] = None, search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_COLS} FROM {_SRC}
        WHERE root_org_id = CAST(:r AS uuid) AND (:active_only = FALSE OR is_active = TRUE)
          AND (CAST(:fy AS int) IS NULL OR fiscal_year = CAST(:fy AS int))
          AND (CAST(:ft AS text) IS NULL OR funding_type = CAST(:ft AS text))
          AND (CAST(:q AS text) IS NULL
               OR funding_name ILIKE CAST(:q AS text) OR funding_code ILIKE CAST(:q AS text))
        ORDER BY fiscal_year DESC, funding_code
    """), {"r": str(get_root(db, user_id)), "active_only": active_only, "fy": fiscal_year,
           "ft": funding_type, "q": _like(search)}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_funding(db: Session, user_id: UUID, funding_id: UUID) -> dict:
    return scoped_get(db, _SRC, _COLS, funding_id, get_root(db, user_id), "Funding source")


def create_funding(db: Session, payload: FundingCreate, user_id: UUID) -> dict:
    try:
        row = db.execute(text(f"""
            INSERT INTO {_SRC}
                (root_org_id, funding_code, funding_name, fiscal_year, funding_type, ceiling_amount,
                 created_by, updated_by)
            VALUES (CAST(:r AS uuid), :code, :name, :fy, :ft, :ceil, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING {_COLS}
        """), {"r": str(get_root(db, user_id)), "code": payload.funding_code, "name": payload.funding_name,
               "fy": payload.fiscal_year, "ft": payload.funding_type, "ceil": payload.ceiling_amount,
               "uid": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="funding_code already exists")
    return dict(row._mapping)


def update_funding(db: Session, funding_id: UUID, payload: FundingUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    row = _update_row(db, _SRC, "funding_id", funding_id, data, set(), user_id, _COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Funding source not found")
    return row


def deactivate_funding(db: Session, funding_id: UUID, user_id: UUID) -> dict:
    row = _update_row(db, _SRC, "funding_id", funding_id, {"is_active": False}, set(), user_id,
                      _COLS, get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Funding source not found")
    return row


# --- funding_document (metadata only, no file storage yet) ---

_DOC_COLS = "doc_id, funding_id, doc_type, doc_no, doc_date, doc_url, uploaded_by, uploaded_at"


def list_docs(db: Session, user_id: UUID, funding_id: UUID) -> list[dict]:
    assert_in_root(db, _SRC, funding_id, get_root(db, user_id), "Funding source")
    rows = db.execute(text(f"""
        SELECT {_DOC_COLS} FROM aidaa_core.funding_document
        WHERE funding_id = CAST(:f AS uuid) ORDER BY uploaded_at DESC
    """), {"f": str(funding_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def add_doc(db: Session, funding_id: UUID, payload: FundingDocCreate, user_id: UUID) -> dict:
    assert_in_root(db, _SRC, funding_id, get_root(db, user_id), "Funding source")
    row = db.execute(text(f"""
        INSERT INTO aidaa_core.funding_document (funding_id, doc_type, doc_no, doc_date, doc_url, uploaded_by)
        VALUES (CAST(:f AS uuid), :dt, :dn, :dd, :du, CAST(:uid AS uuid))
        RETURNING {_DOC_COLS}
    """), {"f": str(funding_id), "dt": payload.doc_type, "dn": payload.doc_no,
           "dd": payload.doc_date, "du": payload.doc_url, "uid": str(user_id)}).fetchone()
    return dict(row._mapping)