"""Execution schemas: korespondensi (doc requests, interviews, berita acara penyampaian notisi).

Split out of the old monolithic execution.py by domain; re-exported from app.schemas.execution.
"""
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.execution_core import Stance


class DocReqCreate(BaseModel):
    unit_id: UUID
    item: str = Field(..., min_length=1, max_length=255)
    notes: Optional[str] = None
    deadline: date


class DocReqUpdate(BaseModel):
    item: Optional[str] = Field(None, min_length=1, max_length=255)
    notes: Optional[str] = None
    deadline: Optional[date] = None


class DocReqSubmitIn(BaseModel):
    submitted_url: str = Field(..., min_length=1, max_length=500)
    submitted_desc: Optional[str] = None


class DocReqVerifyIn(BaseModel):
    verify_note: Optional[str] = None


class DocReqOut(BaseModel):
    doc_req_id: UUID
    assignment_id: UUID
    unit_id: UUID
    unit_code: Optional[str] = None
    item: str
    notes: Optional[str] = None
    deadline: date
    status: str
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[UUID] = None
    submitted_url: Optional[str] = None
    submitted_desc: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[UUID] = None
    verify_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CancelIn(BaseModel):
    reason: str = Field(..., min_length=1)


class InterviewCreate(BaseModel):
    unit_id: UUID
    topic: str = Field(..., min_length=1, max_length=255)
    agenda: Optional[str] = None
    held_date: date
    start_time: Optional[str] = Field(None, max_length=8)
    end_time: Optional[str] = Field(None, max_length=8)
    mode: Literal["onsite", "online"] = "onsite"
    location: Optional[str] = Field(None, max_length=500)
    attendees: Optional[str] = None


class InterviewUpdate(BaseModel):
    topic: Optional[str] = Field(None, min_length=1, max_length=255)
    agenda: Optional[str] = None
    held_date: Optional[date] = None
    start_time: Optional[str] = Field(None, max_length=8)
    end_time: Optional[str] = Field(None, max_length=8)
    mode: Optional[Literal["onsite", "online"]] = None
    location: Optional[str] = Field(None, max_length=500)
    attendees: Optional[str] = None


class InterviewResultIn(BaseModel):
    result: Optional[str] = None


class InterviewOut(BaseModel):
    interview_id: UUID
    assignment_id: UUID
    unit_id: UUID
    unit_code: Optional[str] = None
    topic: str
    agenda: Optional[str] = None
    held_date: date
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    mode: str
    location: Optional[str] = None
    attendees: Optional[str] = None
    status: str
    cancel_reason: Optional[str] = None
    result: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BapCreate(BaseModel):
    bap_no: str = Field(..., min_length=1, max_length=50)
    kepada: Optional[str] = Field(None, max_length=255)
    presented_date: date
    deadline: date
    document_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class BapUpdate(BaseModel):
    bap_no: Optional[str] = Field(None, min_length=1, max_length=50)
    kepada: Optional[str] = Field(None, max_length=255)
    presented_date: Optional[date] = None
    deadline: Optional[date] = None
    document_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class BapResultIn(BaseModel):
    stance_result: Stance
    response_id: Optional[UUID] = None
    deadline: Optional[date] = None
    notes: Optional[str] = None


class BapOut(BaseModel):
    bap_id: UUID
    finding_id: UUID
    assignment_id: UUID
    bap_no: str
    kepada: Optional[str] = None
    presented_date: Optional[date] = None
    deadline: Optional[date] = None
    stance_result: Optional[str] = None
    response_id: Optional[UUID] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None
    finding_status: str
    created_at: datetime
    updated_at: datetime


# Flat list row for the assignment BAP listing: every communicated+ finding with nullable BAP
# fields, so the UI can show which findings still lack their berita acara.
class BapItemOut(BaseModel):
    finding_id: UUID
    assignment_id: UUID
    finding_no: str
    title: str
    finding_status: str
    communicated_at: Optional[datetime] = None
    response_due_date: Optional[date] = None
    bap_id: Optional[UUID] = None
    bap_no: Optional[str] = None
    kepada: Optional[str] = None
    presented_date: Optional[date] = None
    deadline: Optional[date] = None
    stance_result: Optional[str] = None
    response_id: Optional[UUID] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


__all__ = [
    "DocReqCreate", "DocReqUpdate", "DocReqSubmitIn", "DocReqVerifyIn", "DocReqOut",
    "CancelIn", "InterviewCreate", "InterviewUpdate", "InterviewResultIn", "InterviewOut",
    "BapCreate", "BapUpdate", "BapResultIn", "BapOut", "BapItemOut",
]
