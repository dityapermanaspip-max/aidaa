from datetime import date
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class TripDraftRequest(BaseModel):
    instruction: Optional[str] = Field(None, max_length=1000)
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = None


# What the AI answers: where, when and who. It never writes money amounts or routes.
class AiVisit(BaseModel):
    unit_id: UUID
    start_date: date
    end_date: date
    purpose: str = Field("", max_length=500)
    auditor_ids: List[UUID] = []
    reason: str = Field("", max_length=500)


class TripNaming(BaseModel):
    visits: List[AiVisit] = Field(..., min_length=1)


# What the service builds from the AI answer, and what the human edits.
class AirportOption(BaseModel):
    location_id: UUID
    name: str
    province: Optional[str] = None


class DraftVisit(BaseModel):
    location_id: UUID
    location_name: str
    visit_start: date
    visit_end: date
    purpose: Optional[str] = Field(None, max_length=500)
    attendee_ids: List[UUID] = []
    reason: Optional[str] = Field(None, max_length=500)


class DraftLeg(BaseModel):
    auditor_id: UUID
    username: Optional[str] = None
    direction: Literal["outbound", "return"]
    origin_location_id: UUID
    origin_name: str
    destination_location_id: UUID  # the airport city, the human may change it from the airports list
    destination_name: str
    travel_date: date
    ticket_class: Literal["economy", "business"] = "economy"
    component_id: Optional[UUID] = None
    component_code: Optional[str] = None
    estimated_cost: float = Field(0, ge=0)  # half of the round-trip reference rate, 0 when no rate
    status: Literal["ok", "no_rate", "manual"] = "ok"  # manual: several places match, choose one
    note: Optional[str] = Field(None, max_length=500)


class TripDraft(BaseModel):
    assignment_id: UUID
    visits: List[DraftVisit] = []
    legs: List[DraftLeg] = []
    airports: List[AirportOption] = []  # cities that have a ticket rate, for the searchable dropdown
    warnings: List[str] = []