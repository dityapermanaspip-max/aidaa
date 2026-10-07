from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class BudgetLineCreate(BaseModel):
    component_id: UUID
    auditor_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    rate_id: Optional[UUID] = None        # required unless the component is at_cost
    quantity: float = Field(1, ge=0)
    unit_rate: Optional[float] = Field(None, ge=0)  # only for at_cost components
    notes: Optional[str] = None


class BudgetLineUpdate(BaseModel):
    quantity: Optional[float] = Field(None, ge=0)
    unit_rate: Optional[float] = Field(None, ge=0)  # only for at_cost lines
    notes: Optional[str] = None


class BudgetLineOut(BaseModel):
    line_id: UUID
    plan_id: Optional[UUID] = None
    assignment_id: Optional[UUID] = None
    version_no: int
    auditor_id: Optional[UUID] = None
    component_id: UUID
    location_id: Optional[UUID] = None
    rate_id: Optional[UUID] = None
    trip_leg_id: Optional[UUID] = None
    copied_from_line_id: Optional[UUID] = None
    quantity: float
    unit_rate: float
    amount: float
    basis: str
    source: str
    approval_status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FundingAllocCreate(BaseModel):
    funding_id: UUID
    amount: float = Field(..., ge=0)
    notes: Optional[str] = None


class FundingAllocOut(BaseModel):
    assignment_funding_id: UUID
    assignment_id: UUID
    funding_id: UUID
    funding_code: str
    funding_name: str
    amount: float
    notes: Optional[str] = None
    created_at: datetime


class BudgetSummaryOut(BaseModel):
    assignment_id: UUID
    lines_total: float
    plan_lumpsum: float
    budget_total: float
    funding_total: float
    difference: float
    balanced: bool