from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


# --- Master: library_pka and library_procedure ---

class PkaCreate(BaseModel):
    type_id: UUID
    pka_code: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=250)
    objective: Optional[str] = None


class PkaUpdate(BaseModel):
    type_id: Optional[UUID] = None
    title: Optional[str] = Field(None, min_length=1, max_length=250)
    objective: Optional[str] = None
    is_active: Optional[bool] = None


class PkaOut(BaseModel):
    library_pka_id: UUID
    type_id: UUID
    pka_code: str
    title: str
    objective: Optional[str] = None
    procedure_hours: float = 0  # sum of active procedure hours, 0 = no procedure yet
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProcedureCreate(BaseModel):
    step_no: Optional[int] = Field(None, ge=1)  # empty = next number
    procedure_text: str = Field(..., min_length=1)
    expected_evidence: Optional[str] = None
    estimated_hours: Optional[float] = Field(None, ge=0, le=999999.99)


class ProcedureUpdate(BaseModel):
    step_no: Optional[int] = Field(None, ge=1)
    procedure_text: Optional[str] = Field(None, min_length=1)
    expected_evidence: Optional[str] = None
    estimated_hours: Optional[float] = Field(None, ge=0, le=999999.99)
    is_active: Optional[bool] = None


class ProcedureOut(BaseModel):
    procedure_id: UUID
    library_pka_id: UUID
    step_no: int
    procedure_text: str
    expected_evidence: Optional[str] = None
    estimated_hours: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime