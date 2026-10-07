from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class PkaItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    objective: Optional[str] = None
    planned_hours: float = Field(0, ge=0)
    procedures: List[str] = []


class PkaSuggestion(BaseModel):
    pkas: List[PkaItem] = Field(..., min_length=1)


class ReportSuggestion(BaseModel):
    summary: str = Field(..., min_length=1)
    opinion: Optional[str] = None


class SuggestionDecision(BaseModel):
    decision: Literal["accepted", "edited", "rejected"]
    edited_output: Optional[dict] = None  # required when decision is "edited"


class SuggestionOut(BaseModel):
    suggestion_id: UUID
    feature: str
    record_type: str
    record_id: Optional[UUID] = None
    engine: str
    model_name: str
    input_ref: Optional[str] = None
    output: dict
    status: str
    decided_by: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    
class AiRequest(BaseModel):
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = None


class ModelsOut(BaseModel):
    data: List[str]