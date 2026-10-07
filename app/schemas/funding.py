from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field

FundingType = Literal["budget", "additional_financing", "paid_by_auditee", "other"]


class FundingCreate(BaseModel):
    funding_code: str = Field(..., min_length=1, max_length=30)
    funding_name: str = Field(..., min_length=1, max_length=200)
    fiscal_year: int = Field(..., ge=2000, le=2100)
    funding_type: FundingType
    ceiling_amount: Optional[float] = Field(None, ge=0)


class FundingUpdate(BaseModel):
    funding_name: Optional[str] = Field(None, min_length=1, max_length=200)
    fiscal_year: Optional[int] = Field(None, ge=2000, le=2100)
    funding_type: Optional[FundingType] = None
    ceiling_amount: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None


class FundingOut(BaseModel):
    funding_id: UUID
    funding_code: str
    funding_name: str
    fiscal_year: int
    funding_type: str
    ceiling_amount: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FundingDocCreate(BaseModel):
    doc_type: str = Field(..., min_length=1, max_length=50)
    doc_no: Optional[str] = Field(None, max_length=100)
    doc_date: Optional[date] = None
    doc_url: str = Field(..., min_length=1, max_length=500)


class FundingDocOut(BaseModel):
    doc_id: UUID
    funding_id: UUID
    doc_type: str
    doc_no: Optional[str] = None
    doc_date: Optional[date] = None
    doc_url: str
    uploaded_by: Optional[UUID] = None
    uploaded_at: datetime