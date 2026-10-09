"""Realisation settlement: per-auditor open -> settled via an AIDAA.FINANCE approval task."""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.realisation import SettlementCreate, SettlementOut
from app.services.approval import create_task, register_handler
from app.services.logs import log_comment
from app.services.realisation_common import assert_realisable, assert_member, username_map
from app.services.realisation_report import balance_out

_SS_COLS = ("settlement_id, assignment_id, auditor_id, status, notes, "
            "created_at, created_by, settled_at, settled_by")


def _row_to_out(db: Session, r) -> dict:
    d = dict(r._mapping)
    d["has_pending"] = bool(
        db.execute(text("""
            SELECT 1 FROM aidaa_core.approval_task
            WHERE record_type = 'settlement' AND record_id = CAST(:id AS uuid) AND status = 'pending'
        """), {"id": str(d["settlement_id"])}).fetchone()
    )
    status = d.pop("status")
    d["status"] = "settled" if status == "settled" else ("pending" if d["has_pending"] else "open")
    names = username_map(db, d["assignment_id"])
    d["username"] = names.get(d["auditor_id"])
    bal = balance_out(db, d["assignment_id"])
    line = next((x for x in bal["lines"] if x["auditor_id"] == d["auditor_id"]), None)
    d["advance_total"] = line["advance_total"] if line else 0.0
    d["realised_total"] = line["realised_total"] if line else 0.0
    d["balance"] = line["balance"] if line else 0.0
    return SettlementOut(**d).model_dump()


def list_settlements(db: Session, assignment_id: UUID) -> list[dict]:
    assert_realisable(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {_SS_COLS} FROM aidaa_core.realisation_settlement
        WHERE assignment_id = CAST(:a AS uuid) ORDER BY created_at
    """), {"a": str(assignment_id)}).fetchall()
    return [_row_to_out(db, r) for r in rows]


def submit_settlement(db: Session, assignment_id: UUID, payload: SettlementCreate, user_id: UUID) -> dict:
    assert_realisable(db, assignment_id)
    assert_member(db, assignment_id, payload.auditor_id)
    current = db.execute(text(f"""
        SELECT {_SS_COLS} FROM aidaa_core.realisation_settlement
        WHERE assignment_id = CAST(:a AS uuid) AND auditor_id = CAST(:au AS uuid)
    """), {"a": str(assignment_id), "au": str(payload.auditor_id)}).fetchone()
    if current and current.status == "settled":
        raise HTTPException(status_code=409, detail="Settlement for this auditor is already settled")
    if current:
        settlement_id = current.settlement_id
        db.execute(text("""
            UPDATE aidaa_core.realisation_settlement SET notes = :n
            WHERE settlement_id = CAST(:id AS uuid)
        """), {"n": payload.notes, "id": str(settlement_id)})
    else:
        settlement_id = db.execute(text("""
            INSERT INTO aidaa_core.realisation_settlement
                (assignment_id, auditor_id, status, notes, created_by)
            VALUES (CAST(:a AS uuid), CAST(:au AS uuid), 'open', :n, CAST(:u AS uuid))
            RETURNING settlement_id
        """), {"a": str(assignment_id), "au": str(payload.auditor_id),
               "n": payload.notes, "u": str(user_id)}).fetchone().settlement_id
    create_task(db, "settlement", settlement_id, 1, user_id)
    log_comment(db, "realisation_settlement", settlement_id,
                f"Settlement submitted for approval by {user_id}", user_id)
    row = db.execute(text(f"""
        SELECT {_SS_COLS} FROM aidaa_core.realisation_settlement WHERE settlement_id = CAST(:id AS uuid)
    """), {"id": str(settlement_id)}).fetchone()
    return _row_to_out(db, row)


def _on_settlement_task(db: Session, task: dict, user_id: UUID):
    """Runs after each decision on a 'settlement' task. record_id = settlement_id."""
    if task["status"] == "approved":
        updated = db.execute(text("""
            UPDATE aidaa_core.realisation_settlement
            SET status = 'settled', settled_at = now(), settled_by = CAST(:u AS uuid)
            WHERE settlement_id = CAST(:id AS uuid) AND status = 'open'
            RETURNING settlement_id
        """), {"u": str(user_id), "id": str(task["record_id"])}).fetchone()
        if updated:
            log_comment(db, "realisation_settlement", updated.settlement_id,
                        "Settlement approved and settled", user_id)


register_handler("settlement", _on_settlement_task)