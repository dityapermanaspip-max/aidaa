from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import deviation_read, get_user_accessible_org_ids
from app.schemas.execution import DeviationOut
from app.services.execution.deviations import list_deviations

router = APIRouter()


@router.get("/deviations", response_model=List[DeviationOut])
def get_deviations(limit: Optional[int] = Query(None, ge=1, le=200), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db), user=Depends(deviation_read)):
    org_ids = get_user_accessible_org_ids(db, user.user_id, "audit.deviation.read")
    return list_deviations(db, org_ids, limit, offset)
