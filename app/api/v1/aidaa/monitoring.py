from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import finding_read, get_user_accessible_org_ids
from app.schemas.execution import MonevOut
from app.services.execution.monitoring import list_monev

router = APIRouter()


@router.get("/monitoring/temuan", response_model=MonevOut)
def temuan_monitoring(assignment_id: Optional[UUID] = None, overdue_only: bool = False,
                      search: Optional[str] = None,
                      db: Session = Depends(get_db), user=Depends(finding_read)):
    """Monev Temuan: findings and rekomendasi across ALL assignments the caller may see.

    The owner wants this visible beyond the internal audit org, so the scope is the same rule
    as the surat tugas list: a global `audit.finding.read` mapping sees everything; an
    org-mapped caller sees assignments they own or (after issue) the audited units of their
    organisations. Read-only, scoped server-side, never accepts a hand-written org list."""
    org_ids = get_user_accessible_org_ids(db, user.user_id, "audit.finding.read")
    return list_monev(db, org_ids, assignment_id, overdue_only, search)
