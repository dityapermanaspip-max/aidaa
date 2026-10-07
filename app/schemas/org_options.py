from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class OrgOptionOut(BaseModel):
    org_id: UUID
    org_code: str
    org_name: Optional[str] = None
    parent_id: Optional[UUID] = None
    in_iau: bool


class AuditorCandidateOut(BaseModel):
    user_id: UUID
    username: str
    full_name: str
    email: str
    org_id: UUID
    org_code: str
    org_name: Optional[str] = None


class AuditSettingIn(BaseModel):
    iau_org_id: UUID


class AuditSettingOut(BaseModel):
    root_org_id: UUID
    iau_org_id: Optional[UUID] = None
    iau_org_code: Optional[str] = None
    iau_org_name: Optional[str] = None
    updated_at: Optional[datetime] = None