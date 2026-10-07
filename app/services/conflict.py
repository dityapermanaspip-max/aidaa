from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.logs import log_team


def check_conflict(db: Session, auditor_id: UUID, unit_org_id: Optional[UUID], actor_id: UUID,
                   plan_id: Optional[UUID] = None, assignment_id: Optional[UUID] = None):
    """Hard block: auditor's home org is the audited unit's org or one of its children."""
    if unit_org_id is None:
        return
    hit = db.execute(text("""
        WITH RECURSIVE sub AS (
            SELECT org_id FROM iam.organizations WHERE org_id = CAST(:u AS uuid)
            UNION ALL
            SELECT o.org_id FROM iam.organizations o JOIN sub s ON o.parent_id = s.org_id
        )
        SELECT 1 FROM aidaa_core.auditor a
        JOIN sub ON sub.org_id = a.home_org_id
        WHERE a.auditor_id = CAST(:a AS uuid)
    """), {"u": str(unit_org_id), "a": str(auditor_id)}).fetchone()
    if hit:
        log_team(db, "blocked_conflict", actor_id, plan_id, assignment_id, auditor_id,
                 reason="Auditor home org is the audited unit org or its child")
        db.commit()  # keep the log row, the exception below would otherwise roll it back
        raise HTTPException(status_code=409,
                            detail="Conflict of interest: auditor belongs to the audited unit")