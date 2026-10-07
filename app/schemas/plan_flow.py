from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class PlanSubmit(BaseModel):
    due_date: Optional[date] = None  # due date for the Finance step


class PlanVersionOut(BaseModel):
    version_id: UUID
    plan_id: UUID
    version_no: int
    budget_mode: str
    total_amount: float
    source: str
    approval_status: str
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[UUID] = None


class PlanVersionDetail(PlanVersionOut):
    snapshot: dict