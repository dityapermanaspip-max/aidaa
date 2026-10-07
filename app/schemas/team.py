from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.aidaa import AssignmentRole


class MemberAdd(BaseModel):
    auditor_id: UUID
    role: AssignmentRole
    start_date: Optional[date] = None


class MemberEnd(BaseModel):
    reason: str = Field(..., min_length=1, max_length=200)
    end_date: Optional[date] = None


class MemberReplace(BaseModel):
    new_auditor_id: UUID
    reason: str = Field(..., min_length=1, max_length=200)
    role: Optional[AssignmentRole] = None  # empty = same role as the person replaced
    effective_date: Optional[date] = None


class MemberRoleChange(BaseModel):
    role: AssignmentRole
    reason: str = Field(..., min_length=1, max_length=200)
    effective_date: Optional[date] = None


class MemberOut(BaseModel):
    member_id: UUID
    assignment_id: UUID
    auditor_id: UUID
    username: Optional[str] = None
    role: str
    start_date: date
    end_date: Optional[date] = None
    end_reason: Optional[str] = None
    created_at: datetime