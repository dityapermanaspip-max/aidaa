from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    assignment_no: str = Field(..., min_length=1, max_length=100)
    plan_id: Optional[UUID] = None       # empty = unplanned audit
    owner_org_id: Optional[UUID] = None  # required only when plan_id is empty
    unit_id: Optional[UUID] = None       # required only when plan_id is empty (the first unit)
    extra_unit_ids: List[UUID] = []      # unplanned audits only, a planned one follows the plan's units
    type_id: Optional[UUID] = None       # required only when plan_id is empty
    start_date: Optional[date] = None    # defaults to plan period when planned
    end_date: Optional[date] = None
    notes: Optional[str] = None


class AssignmentUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    extra_unit_ids: Optional[List[UUID]] = None  # unplanned drafts only, replaces the extra units
    assignment_doc_url: Optional[str] = Field(None, max_length=500)
    assignment_doc_name: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class AssignmentChangeIn(BaseModel):
    """Staged post-issue change for the supervisor approval step; omitted fields are unchanged."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    extra_unit_ids: Optional[List[UUID]] = None  # replaces the extra units, unplanned audits only
    assignment_doc_url: Optional[str] = Field(None, max_length=500)
    assignment_doc_name: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None
    reason: str = Field(..., min_length=1)
    due_date: Optional[date] = None


class AssignmentChangeOut(BaseModel):
    change_id: UUID
    assignment_id: UUID
    requested_by: UUID
    reason: str
    payload: dict
    status: str
    task_id: Optional[UUID] = None
    step: Optional[str] = None
    due_date: Optional[date] = None
    decided_by: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime


class AssignmentCancel(BaseModel):
    reason: str = Field(..., min_length=1)


class AssignmentOut(BaseModel):
    assignment_id: UUID
    assignment_no: str
    plan_id: Optional[UUID] = None
    owner_org_id: UUID
    unit_id: UUID
    unit_ids: List[UUID] = []  # all units, the first is the primary unit_id
    type_id: UUID
    start_date: date
    end_date: date
    assignment_doc_url: Optional[str] = None
    assignment_doc_name: Optional[str] = None
    status: str
    issued_by: Optional[UUID] = None
    issued_at: Optional[datetime] = None
    notes: Optional[str] = None
    is_unplanned: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    my_role: Optional[str] = None  # filled on the single GET only