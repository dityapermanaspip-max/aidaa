from datetime import date, datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# --- Master: ref_cost_component ---

CalcBasis = Literal["per_day_worked", "per_travel_day", "per_night", "at_cost", "fixed"]


class CostComponentCreate(BaseModel):
    component_code: str = Field(..., min_length=1, max_length=30)
    component_name: str = Field(..., min_length=1, max_length=150)
    calc_basis: CalcBasis
    sort_order: int = 0


class CostComponentUpdate(BaseModel):
    component_name: Optional[str] = Field(None, min_length=1, max_length=150)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CostComponentOut(BaseModel):
    component_id: UUID
    component_code: str
    component_name: str
    calc_basis: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Master: ref_cost_rate ---

def _clean_grades(v):
    """grade is a list of grade codes. None or an empty list means all grades. A plain string becomes a one-item list."""
    if v is None:
        return None
    if isinstance(v, str):
        v = [v]
    out = []
    for x in v:
        s = str(x).strip()
        if len(s) > 30:
            raise ValueError("each grade code is at most 30 characters")
        if s and s not in out:
            out.append(s)
    return out or None


class CostRateCreate(BaseModel):
    component_id: UUID
    location_id: Optional[UUID] = None
    grade: Optional[List[str]] = None
    amount: float = Field(..., ge=0)
    effective_from: date
    effective_to: Optional[date] = None

    _grade = field_validator("grade", mode="before")(_clean_grades)


class CostRateUpdate(BaseModel):
    component_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    grade: Optional[List[str]] = None
    amount: Optional[float] = Field(None, ge=0)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    _grade = field_validator("grade", mode="before")(_clean_grades)


class CostRateDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None


class CostRateOut(BaseModel):
    rate_id: UUID
    component_id: UUID
    location_id: Optional[UUID] = None
    grade: Optional[List[str]] = None
    amount: float
    effective_from: date
    effective_to: Optional[date] = None
    approval_status: str
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime