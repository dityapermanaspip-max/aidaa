from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import assignment_read
from app.schemas.me import AssignmentAccessOut
from app.services import roles as svc

router = APIRouter()


@router.get("/assignments/{assignment_id}/role", response_model=AssignmentAccessOut)
def my_role_in_assignment(assignment_id: UUID, db: Session = Depends(get_db),
                          user=Depends(assignment_read)):
    """For the UI to show or hide buttons. The backend still enforces every write."""
    return svc.get_my_access(db, user.user_id, assignment_id)