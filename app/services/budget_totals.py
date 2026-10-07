from decimal import Decimal
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.budget_core import get_assignment_row


def budget_total(db: Session, assignment_id: UUID) -> dict:
    a = get_assignment_row(db, assignment_id)
    lines = db.execute(text("""
        SELECT COALESCE(SUM(amount), 0) AS t FROM aidaa_core.budget_line
        WHERE assignment_id = CAST(:a AS uuid)
    """), {"a": str(assignment_id)}).fetchone().t
    lump = Decimal(0)
    if a.plan_id:
        row = db.execute(text("""
            SELECT total_amount FROM aidaa_core.audit_plan_version
            WHERE plan_id = CAST(:p AS uuid) AND approval_status = 'approved' AND budget_mode = 'lumpsum'
            ORDER BY version_no DESC LIMIT 1
        """), {"p": str(a.plan_id)}).fetchone()
        if row:
            lump = row.total_amount
    return {"lines_total": lines, "plan_lumpsum": lump, "budget_total": lines + lump}


def funding_total(db: Session, assignment_id: UUID) -> Decimal:
    return db.execute(text("""
        SELECT COALESCE(SUM(amount), 0) AS t FROM aidaa_core.assignment_funding
        WHERE assignment_id = CAST(:a AS uuid)
    """), {"a": str(assignment_id)}).fetchone().t


def assert_funding_matches(db: Session, assignment_id: UUID):
    total = budget_total(db, assignment_id)["budget_total"]
    funded = funding_total(db, assignment_id)
    if total != funded:
        raise HTTPException(status_code=409,
                            detail=f"Funding ({funded}) must equal the approved budget total ({total}) to issue")