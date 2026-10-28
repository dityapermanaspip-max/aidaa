"""Request/response schemas for the background job endpoints."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class JobAccepted(BaseModel):
    """202 answer of every AI/OCR endpoint: the work is queued, poll GET /jobs/{job_id}."""
    job_id: UUID
    status: str = "queued"


class JobOut(JobAccepted):
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
