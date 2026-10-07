from datetime import date, datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field

TripMode = Literal["plane", "bus", "boat", "train", "car", "other"]


class ReasonIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=200)


class VisitCreate(BaseModel):
    location_id: UUID
    visit_start: date
    visit_end: date
    purpose: Optional[str] = None
    attendee_ids: List[UUID] = []


class VisitUpdate(BaseModel):
    location_id: Optional[UUID] = None
    visit_start: Optional[date] = None
    visit_end: Optional[date] = None
    purpose: Optional[str] = None
    attendee_ids: Optional[List[UUID]] = None  # replaces the whole attendee list


class VisitOut(BaseModel):
    visit_id: UUID
    assignment_id: UUID
    location_id: UUID
    visit_start: date
    visit_end: date
    purpose: Optional[str] = None
    status: str
    cancel_reason: Optional[str] = None
    attendee_ids: List[UUID] = []
    created_at: datetime
    updated_at: datetime


class LegCreate(BaseModel):
    auditor_id: UUID
    origin_location_id: UUID
    destination_location_id: UUID
    mode: TripMode
    component_id: Optional[UUID] = None  # at_cost cost component of the budget line, empty = code TRANSPORT
    depart_at: Optional[datetime] = None
    arrive_at: Optional[datetime] = None
    estimated_cost: float = Field(0, ge=0)


class LegUpdate(BaseModel):
    origin_location_id: Optional[UUID] = None
    destination_location_id: Optional[UUID] = None
    mode: Optional[TripMode] = None
    component_id: Optional[UUID] = None  # only while the leg is planned
    depart_at: Optional[datetime] = None
    arrive_at: Optional[datetime] = None
    estimated_cost: Optional[float] = Field(None, ge=0)
    actual_cost: Optional[float] = Field(None, ge=0)  # only on a confirmed leg


class LegOut(BaseModel):
    leg_id: UUID
    assignment_id: UUID
    auditor_id: UUID
    leg_no: int
    origin_location_id: UUID
    destination_location_id: UUID
    mode: str
    component_id: Optional[UUID] = None  # taken from the leg's budget line
    depart_at: Optional[datetime] = None
    arrive_at: Optional[datetime] = None
    estimated_cost: float
    actual_cost: Optional[float] = None
    status: str
    created_at: datetime
    updated_at: datetime