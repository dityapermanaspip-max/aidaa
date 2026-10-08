from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field

Result = Literal["no_exception", "exception"]
Stance = Literal["agree", "partially_agree", "disagree"]


class SkipIn(BaseModel):
    reason: str = Field(..., min_length=1)


class NoteIn(BaseModel):
    note: str = Field(..., min_length=1)


# --- PKA ---

class CopyLibraryIn(BaseModel):
    library_pka_ids: Optional[List[UUID]] = None  # empty = all library PKA of the assignment type


class ExePkaCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    pka_code: Optional[str] = Field(None, max_length=50)
    objective: Optional[str] = None
    assigned_auditor_id: Optional[UUID] = None
    planned_hours: float = Field(0, ge=0)


class ExePkaUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=250)
    objective: Optional[str] = None
    assigned_auditor_id: Optional[UUID] = None
    planned_hours: Optional[float] = Field(None, ge=0)


class PkaComplete(BaseModel):
    actual_hours: Optional[float] = Field(None, ge=0)


class ExePkaOut(BaseModel):
    pka_id: UUID
    assignment_id: UUID
    library_pka_id: Optional[UUID] = None
    pka_code: Optional[str] = None
    title: str
    objective: Optional[str] = None
    assigned_auditor_id: Optional[UUID] = None
    planned_hours: float
    actual_hours: Optional[float] = None
    status: str
    is_skipped: bool
    skip_reason: Optional[str] = None
    source: str
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- Procedure and working paper ---

class ExeProcCreate(BaseModel):
    step_no: Optional[int] = Field(None, ge=1)  # empty = next number
    procedure_text: str = Field(..., min_length=1)


class ExeProcUpdate(BaseModel):
    procedure_text: Optional[str] = Field(None, min_length=1)
    conclusion: Optional[str] = None
    result: Optional[Result] = None


class ExeProcOut(BaseModel):
    procedure_id: UUID
    pka_id: UUID
    library_procedure_id: Optional[UUID] = None
    step_no: int
    procedure_text: str
    is_skipped: bool
    skip_reason: Optional[str] = None
    executed_by: Optional[UUID] = None
    executed_at: Optional[datetime] = None
    conclusion: Optional[str] = None
    result: Optional[str] = None
    status: str
    leader_reviewed_by: Optional[UUID] = None
    leader_reviewed_at: Optional[datetime] = None
    supervisor_reviewed_by: Optional[UUID] = None
    supervisor_reviewed_at: Optional[datetime] = None
    supervisor_review_skipped: bool = False
    created_at: datetime
    updated_at: datetime


class PaperCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    file_url: str = Field(..., min_length=1, max_length=500)
    file_name: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class PaperUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=250)
    file_url: Optional[str] = Field(None, min_length=1, max_length=500)
    file_name: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class PaperOut(BaseModel):
    paper_id: UUID
    procedure_id: UUID
    title: str
    file_url: str
    file_name: Optional[str] = None
    notes: Optional[str] = None
    uploaded_by: Optional[UUID] = None
    uploaded_at: datetime
    updated_at: datetime


# --- Finding, response, recommendation ---

class FindingCreate(BaseModel):
    procedure_id: Optional[UUID] = None
    title: str = Field(..., min_length=1, max_length=250)
    description: Optional[str] = None
    criteria: Optional[str] = None
    materiality_amount: float = Field(0, ge=0)


class FindingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=250)
    description: Optional[str] = None
    criteria: Optional[str] = None
    materiality_amount: Optional[float] = Field(None, ge=0)


class FindingOut(BaseModel):
    finding_id: UUID
    assignment_id: UUID
    procedure_id: Optional[UUID] = None
    finding_no: str
    title: str
    description: Optional[str] = None
    criteria: Optional[str] = None
    materiality_amount: float
    communicated_at: Optional[datetime] = None
    response_due_date: Optional[date] = None
    status: str
    no_response: bool = False
    under_review: bool = False
    created_at: datetime
    updated_at: datetime


class CommunicateIn(BaseModel):
    response_due_date: date
    message: Optional[str] = None


class ExtendDueIn(BaseModel):
    new_due_date: date
    reason: str = Field(..., min_length=1)


class ResponseCreate(BaseModel):
    stance: Stance
    message: Optional[str] = None
    action_plan: Optional[str] = None
    target_date: Optional[date] = None
    evidence_url: Optional[str] = Field(None, max_length=500)


class ResponseOut(BaseModel):
    response_id: UUID
    finding_id: UUID
    round_no: int
    direction: str
    stance: Optional[str] = None
    message: Optional[str] = None
    action_plan: Optional[str] = None
    target_date: Optional[date] = None
    evidence_url: Optional[str] = None
    responded_by: Optional[UUID] = None
    responded_at: datetime


class RekCreate(BaseModel):
    recommendation_text: str = Field(..., min_length=1)
    due_date: Optional[date] = None


class RekUpdate(BaseModel):
    recommendation_text: Optional[str] = Field(None, min_length=1)
    due_date: Optional[date] = None


class RekFollowupIn(BaseModel):
    followup_note: str = Field(..., min_length=1)
    followup_url: Optional[str] = Field(None, max_length=500)


class RekOut(BaseModel):
    rekomend_id: UUID
    finding_id: UUID
    rekomend_no: str
    recommendation_text: str
    due_date: Optional[date] = None
    status: str
    followup_note: Optional[str] = None
    followup_url: Optional[str] = None
    followup_by: Optional[UUID] = None
    followup_at: Optional[datetime] = None
    closed_during_audit: bool
    closed_by: Optional[UUID] = None
    closed_at: Optional[datetime] = None
    last_monitored_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- Report ---

class ReportCreate(BaseModel):
    opinion: Optional[str] = None
    summary: Optional[str] = None
    materiality_threshold_pct: float = Field(5, ge=0)
    report_url: Optional[str] = Field(None, max_length=500)


class ReportUpdate(BaseModel):
    opinion: Optional[str] = None
    summary: Optional[str] = None
    materiality_threshold_pct: Optional[float] = Field(None, ge=0)
    report_url: Optional[str] = Field(None, max_length=500)


class ReportOut(BaseModel):
    report_id: UUID
    assignment_id: UUID
    version_no: int
    opinion: Optional[str] = None
    summary: Optional[str] = None
    materiality_threshold_pct: float
    total_open_materiality: float
    report_url: Optional[str] = None
    source: str
    status: str
    created_at: datetime
    updated_at: datetime


class ReportDetail(ReportOut):
    review_counts: Dict[str, int] = {}
    findings: List[dict] = []
    open_materiality_now: float = 0