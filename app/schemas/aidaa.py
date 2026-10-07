from datetime import date, datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field

# Moved to their own files, re-exported so existing imports keep working.
from app.schemas.masters_auditor import (  # noqa: F401
    AuditorCreate, AuditorUpdate, AuditorOut, ExpertiseType,
    ExpertiseCreate, ExpertiseUpdate, ExpertiseVerify, ExpertiseOut,
    DocumentCreate, DocumentOut,
)
from app.schemas.masters_library import (  # noqa: F401
    PkaCreate, PkaUpdate, PkaOut, ProcedureCreate, ProcedureUpdate, ProcedureOut,
)
from app.schemas.masters_costing import (  # noqa: F401
    CalcBasis, CostComponentCreate, CostComponentUpdate, CostComponentOut,
    CostRateCreate, CostRateUpdate, CostRateDecision, CostRateOut,
)


# --- Master: ref_location ---

class LocationCreate(BaseModel):
    location_code: str = Field(..., min_length=1, max_length=30)
    location_name: str = Field(..., min_length=1, max_length=150)
    country: str = Field("Indonesia", min_length=1, max_length=100)
    province: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None


class LocationUpdate(BaseModel):
    location_name: Optional[str] = Field(None, min_length=1, max_length=150)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    province: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None
    is_active: Optional[bool] = None


class LocationOut(BaseModel):
    location_id: UUID
    location_code: str
    location_name: str
    country: str
    province: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Master: ref_audit_type ---

class AuditTypeCreate(BaseModel):
    type_code: str = Field(..., min_length=1, max_length=30)
    type_name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None


class AuditTypeUpdate(BaseModel):
    type_name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AuditTypeOut(BaseModel):
    type_id: UUID
    type_code: str
    type_name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Master: ref_auditable_unit ---

class UnitCreate(BaseModel):
    unit_code: str = Field(..., min_length=1, max_length=30)
    unit_name: str = Field(..., min_length=1, max_length=200)
    org_id: UUID
    location_id: UUID
    unit_type: Optional[str] = Field(None, max_length=50)
    risk_score: Optional[float] = Field(None, ge=0, le=9999.99)


class UnitUpdate(BaseModel):
    unit_name: Optional[str] = Field(None, min_length=1, max_length=200)
    org_id: Optional[UUID] = None
    unit_type: Optional[str] = Field(None, max_length=50)
    location_id: Optional[UUID] = None
    risk_score: Optional[float] = Field(None, ge=0, le=9999.99)
    is_active: Optional[bool] = None


class UnitOut(BaseModel):
    unit_id: UUID
    org_id: Optional[UUID] = None
    unit_code: str
    unit_name: str
    unit_type: Optional[str] = None
    location_id: Optional[UUID] = None
    risk_score: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Approval engine: approval_task ---

class TaskDecision(BaseModel):
    decision: Literal["approved", "rejected", "returned"]
    note: Optional[str] = None


class TaskOut(BaseModel):
    task_id: UUID
    record_type: str
    record_id: UUID
    step_id: UUID
    step_no: int
    step_code: str
    assigned_user_id: Optional[UUID] = None
    requested_by: UUID
    status: str
    due_date: Optional[date] = None
    decided_by: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime


# --- Plan core: audit_plan and audit_plan_member ---

PlanBudgetMode = Literal["lumpsum", "detailed"]
AssignmentRole = Literal["supervisor", "leader", "member"]


class PlanCreate(BaseModel):
    plan_no: str = Field(..., min_length=1, max_length=50)
    fiscal_year: int = Field(..., ge=2000, le=2100)
    owner_org_id: UUID
    unit_id: UUID  # the first unit, most plans have only this one
    extra_unit_ids: List[UUID] = []  # optional additional units of the same plan
    type_id: UUID
    period_start: date
    period_end: date
    planned_auditors: int = Field(1, ge=1)
    planned_days: int = Field(1, ge=1)
    budget_mode: PlanBudgetMode = "lumpsum"
    lumpsum_amount: float = Field(0, ge=0)
    notes: Optional[str] = None


class PlanUpdate(BaseModel):
    fiscal_year: Optional[int] = Field(None, ge=2000, le=2100)
    unit_id: Optional[UUID] = None
    extra_unit_ids: Optional[List[UUID]] = None  # replaces the extra units, empty list = single unit
    type_id: Optional[UUID] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    planned_auditors: Optional[int] = Field(None, ge=1)
    planned_days: Optional[int] = Field(None, ge=1)
    budget_mode: Optional[PlanBudgetMode] = None
    lumpsum_amount: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class PlanOut(BaseModel):
    plan_id: UUID
    plan_no: str
    fiscal_year: int
    owner_org_id: UUID
    unit_id: UUID
    unit_ids: List[UUID] = []  # all units, the first is the primary unit_id
    type_id: UUID
    period_start: date
    period_end: date
    planned_auditors: int
    planned_days: int
    budget_mode: str
    lumpsum_amount: float
    status: str
    current_version_no: int
    is_closed: bool
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PlanMemberCreate(BaseModel):
    auditor_id: UUID
    assignment_role: AssignmentRole
    is_budget_drafter: bool = False


class PlanMemberUpdate(BaseModel):
    assignment_role: Optional[AssignmentRole] = None
    is_budget_drafter: Optional[bool] = None


class PlanMemberOut(BaseModel):
    plan_member_id: UUID
    plan_id: UUID
    auditor_id: UUID
    username: Optional[str] = None
    assignment_role: str
    is_budget_drafter: bool
    created_at: datetime
    warnings: List[str] = []