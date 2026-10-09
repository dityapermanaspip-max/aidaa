from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.realisation import AdvanceCreate, AdvanceUpdate, AdvanceOut
from app.services.masters import _update_row
from app.services.logs import log_comment
from app.services.realisation_common import assert_realisable, assert_member, username_map

_ADV_COLS = ("advance_id, assignment_id, auditor_id, amount, advance_date, notes, "
             "created_at, updated_at")


def _out(row, names: dict) -> dict:
    d = dict(row) if isinstance(row, dict) else dict(row._mapping)
    d["username"] = names.get(d["auditor_id"])
    return AdvanceOut(**d).model_dump()


def _get(db: Session, advance_id: UUID) -> dict:
    row = db.execute(text(f"""
        SELECT {_ADV_COLS} FROM aidaa_core.realisation_advance WHERE advance_id = CAST(:id AS uuid)
    """), {"id": str(advance_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Advance not found")
    return dict(row._mapping)


def list_advances(db: Session, assignment_id: UUID) -> list[dict]:
    assert_realisable(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {_ADV_COLS} FROM aidaa_core.realisation_advance
        WHERE assignment_id = CAST(:a AS uuid) ORDER BY advance_date, created_at
    """), {"a": str(assignment_id)}).fetchall()
    names = username_map(db, assignment_id)
    return [_out(r, names) for r in rows]


def create_advance(db: Session, assignment_id: UUID, payload: AdvanceCreate, user_id: UUID) -> dict:
    assert_realisable(db, assignment_id)
    assert_member(db, assignment_id, payload.auditor_id)
    row = db.execute(text("""
        INSERT INTO aidaa_core.realisation_advance
            (assignment_id, auditor_id, amount, advance_date, notes, created_by, updated_by)
        VALUES (CAST(:a AS uuid), CAST(:au AS uuid), :amt, :d, :n, CAST(:u AS uuid), CAST(:u AS uuid))
        RETURNING advance_id
    """), {"a": str(assignment_id), "au": str(payload.auditor_id), "amt": payload.amount,
           "d": payload.advance_date, "n": payload.notes, "u": str(user_id)}).fetchone()
    log_comment(db, "realisation_advance", row.advance_id,
                f"Advance {payload.amount} on {payload.advance_date}", user_id)
    return _out(_get(db, row.advance_id), username_map(db, assignment_id))


def update_advance(db: Session, advance_id: UUID, payload: AdvanceUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    current = _get(db, advance_id)
    assert_realisable(db, current["assignment_id"])
    if data.get("auditor_id"):
        assert_member(db, current["assignment_id"], data["auditor_id"])
    _update_row(db, "aidaa_core.realisation_advance", "advance_id", advance_id, data,
                {"auditor_id"}, user_id, "advance_id")
    log_comment(db, "realisation_advance", advance_id, "Advance updated", user_id)
    return _out(_get(db, advance_id), username_map(db, current["assignment_id"]))


def delete_advance(db: Session, advance_id: UUID, user_id: UUID) -> dict:
    current = _get(db, advance_id)
    assert_realisable(db, current["assignment_id"])
    db.execute(text("DELETE FROM aidaa_core.realisation_advance WHERE advance_id = CAST(:id AS uuid)"),
               {"id": str(advance_id)})
    log_comment(db, "realisation_advance", advance_id, "Advance deleted", user_id)
    return {"deleted": True}