from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AdvanceCreate(BaseModel):
    auditor_id: UUID
    amount: float = Field(..., ge=0)
    advance_date: date
    notes: Optional[str] = None


class AdvanceUpdate(BaseModel):
    auditor_id: Optional[UUID] = None
    amount: Optional[float] = Field(None, ge=0)
    advance_date: Optional[date] = None
    notes: Optional[str] = None


class AdvanceOut(BaseModel):
    advance_id: UUID
    assignment_id: UUID
    auditor_id: UUID
    username: Optional[str] = None
    amount: float
    advance_date: date
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CostCreate(BaseModel):
    auditor_id: UUID
    component_id: UUID
    location_id: Optional[UUID] = None
    quantity: float = Field(1, ge=0)
    unit_rate: float = Field(..., ge=0)
    cost_date: date
    evidence_url: Optional[str] = None
    evidence_name: Optional[str] = None
    notes: Optional[str] = None


class CostUpdate(BaseModel):
    auditor_id: Optional[UUID] = None
    component_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    quantity: Optional[float] = Field(None, ge=0)
    unit_rate: Optional[float] = Field(None, ge=0)
    cost_date: Optional[date] = None
    evidence_url: Optional[str] = None
    evidence_name: Optional[str] = None
    notes: Optional[str] = None


class CostOut(BaseModel):
    rc_id: UUID
    assignment_id: UUID
    auditor_id: UUID
    username: Optional[str] = None
    component_id: UUID
    component_code: Optional[str] = None
    component_name: Optional[str] = None
    location_id: Optional[UUID] = None
    quantity: float
    unit_rate: float
    amount: float
    cost_date: date
    evidence_url: Optional[str] = None
    evidence_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BalanceLine(BaseModel):
    auditor_id: UUID
    username: Optional[str] = None
    advance_total: float
    realised_total: float
    balance: float  # advance - realised; positive = to be returned


class BalanceOut(BaseModel):
    lines: List[BalanceLine]
    advance_total: float
    realised_total: float
    balance: float


class VarianceLine(BaseModel):
    component_id: UUID
    component_code: str
    component_name: str
    planned: float
    realised: float
    variance: float  # planned - realised


class VarianceOut(BaseModel):
    lines: List[VarianceLine]
    planned: float
    realised: float
    variance: float