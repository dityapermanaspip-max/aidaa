from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


# --- Master: auditor ---

class AuditorCreate(BaseModel):
    user_id: UUID
    home_org_id: Optional[UUID] = None
    home_location_id: Optional[UUID] = None
    employee_no: Optional[str] = Field(None, max_length=50)
    grade: Optional[str] = Field(None, max_length=30)
    joined_date: Optional[date] = None


class AuditorUpdate(BaseModel):
    home_org_id: Optional[UUID] = None
    home_location_id: Optional[UUID] = None
    employee_no: Optional[str] = Field(None, max_length=50)
    grade: Optional[str] = Field(None, max_length=30)
    status: Optional[Literal["active", "leave", "resigned"]] = None
    joined_date: Optional[date] = None
    left_date: Optional[date] = None
    is_active: Optional[bool] = None


class AuditorOut(BaseModel):
    auditor_id: UUID
    user_id: UUID
    username: Optional[str] = None
    email: Optional[str] = None
    home_org_id: Optional[UUID] = None
    home_location_id: Optional[UUID] = None
    employee_no: Optional[str] = None
    grade: Optional[str] = None
    status: str
    joined_date: Optional[date] = None
    left_date: Optional[date] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Master: expertise ---

ExpertiseType = Literal["certification", "degree", "training", "past_experience", "internal_experience"]


class ExpertiseCreate(BaseModel):
    expertise_type: ExpertiseType
    title: str = Field(..., min_length=1, max_length=200)
    issuer: Optional[str] = Field(None, max_length=200)
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    type_id: Optional[UUID] = None


class ExpertiseUpdate(BaseModel):
    expertise_type: Optional[ExpertiseType] = None
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    issuer: Optional[str] = Field(None, max_length=200)
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    type_id: Optional[UUID] = None


class ExpertiseVerify(BaseModel):
    decision: Literal["verified", "rejected"]
    reject_reason: Optional[str] = None
    points: Optional[float] = Field(None, ge=0, le=999999.99)


class ExpertiseOut(BaseModel):
    expertise_id: UUID
    auditor_id: UUID
    expertise_type: str
    title: str
    issuer: Optional[str] = None
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    type_id: Optional[UUID] = None
    points: float
    source: str
    verification_status: str
    verified_by: Optional[UUID] = None
    verified_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DocumentCreate(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_path: str = Field(..., min_length=1, max_length=500)


class DocumentOut(BaseModel):
    doc_id: UUID
    expertise_id: UUID
    file_name: str
    file_path: str
    uploaded_by: Optional[UUID] = None
    uploaded_at: datetime