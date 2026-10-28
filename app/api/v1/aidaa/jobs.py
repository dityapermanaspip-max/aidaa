"""Poll endpoint for background jobs (AI generation and PDF/OCR extraction).

Mounted without the root-scoped dependency: the worker already pinned the root when it ran, and a
job id is scoped to its owner here, so the poll never needs the root and never exposes another
user's work.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.schemas.jobs import JobOut
from app.services import jobs as svc

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return svc.get_job(db, job_id, user.user_id)
