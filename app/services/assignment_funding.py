from decimal import Decimal
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.budget import FundingAllocCreate
from app.services.assignments import get_assignment
from app.services.budgets import budget_total, funding_total
from app.services.scope import root_of_org

_SQL = """
    SELECT af.assignment_funding_id, af.assignment_id, af.funding_id, f.funding_code,
           f.funding_name, af.amount, af.notes, af.created_at
    FROM aidaa_core.assignment_funding af
    JOIN aidaa_core.ref_funding_source f ON f.funding_id = af.funding_id
"""


def _draft(db: Session, assignment_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] != "draft":
        raise HTTPException(status_code=409, detail="Funding can only change while the assignment is draft")
    return a


def list_funding(db: Session, assignment_id: UUID) -> list[dict]:
    get_assignment(db, assignment_id)
    rows = db.execute(text(f"{_SQL} WHERE af.assignment_id = CAST(:a AS uuid) ORDER BY f.funding_code"),
                      {"a": str(assignment_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def upsert_funding(db: Session, assignment_id: UUID, payload: FundingAllocCreate, user_id: UUID) -> dict:
    a = _draft(db, assignment_id)
    src = db.execute(text("""
        SELECT is_active, ceiling_amount, root_org_id FROM aidaa_core.ref_funding_source
        WHERE funding_id = CAST(:f AS uuid)
    """), {"f": str(payload.funding_id)}).fetchone()
    if not src or str(src.root_org_id) != str(root_of_org(db, a["owner_org_id"])):
        raise HTTPException(status_code=404, detail="Funding source not found")

    amount = Decimal(str(payload.amount))
    if src.ceiling_amount is not None:
        used = db.execute(text("""
            SELECT COALESCE(SUM(af.amount), 0) AS t FROM aidaa_core.assignment_funding af
            JOIN aidaa_core.assignment a ON a.assignment_id = af.assignment_id
            WHERE af.funding_id = CAST(:f AS uuid) AND a.status <> 'cancelled'
              AND af.assignment_id <> CAST(:a AS uuid)
        """), {"f": str(payload.funding_id), "a": str(assignment_id)}).fetchone().t
        if used + amount > src.ceiling_amount:
            raise HTTPException(status_code=409,
                                detail=f"Exceeds the funding ceiling ({src.ceiling_amount}), already used {used}")

    row = db.execute(text("""
        INSERT INTO aidaa_core.assignment_funding (assignment_id, funding_id, amount, notes, created_by)
        VALUES (CAST(:a AS uuid), CAST(:f AS uuid), :amt, :n, CAST(:u AS uuid))
        ON CONFLICT (assignment_id, funding_id)
        DO UPDATE SET amount = EXCLUDED.amount, notes = EXCLUDED.notes
        RETURNING assignment_funding_id
    """), {"a": str(assignment_id), "f": str(payload.funding_id), "amt": amount,
           "n": payload.notes, "u": str(user_id)}).fetchone()
    out = db.execute(text(f"{_SQL} WHERE af.assignment_funding_id = CAST(:id AS uuid)"),
                     {"id": str(row.assignment_funding_id)}).fetchone()
    return dict(out._mapping)


def delete_funding(db: Session, assignment_id: UUID, funding_id: UUID) -> None:
    _draft(db, assignment_id)
    res = db.execute(text("""
        DELETE FROM aidaa_core.assignment_funding
        WHERE assignment_id = CAST(:a AS uuid) AND funding_id = CAST(:f AS uuid)
    """), {"a": str(assignment_id), "f": str(funding_id)})
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Funding allocation not found")


def get_summary(db: Session, assignment_id: UUID) -> dict:
    get_assignment(db, assignment_id)
    t = budget_total(db, assignment_id)
    funded = funding_total(db, assignment_id)
    return {
        "assignment_id": assignment_id,
        "lines_total": float(t["lines_total"]), "plan_lumpsum": float(t["plan_lumpsum"]),
        "budget_total": float(t["budget_total"]), "funding_total": float(funded),
        "difference": float(t["budget_total"] - funded), "balanced": t["budget_total"] == funded,
    }