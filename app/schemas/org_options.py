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
    # Both optional, at least one must be sent. base_location_id may be sent explicitly as null
    # (clears it); iau_org_id can never be cleared.
    iau_org_id: Optional[UUID] = None
    base_location_id: Optional[UUID] = None


class AuditSettingOut(BaseModel):
    root_org_id: UUID
    iau_org_id: Optional[UUID] = None
    iau_org_code: Optional[str] = None
    iau_org_name: Optional[str] = None
    base_location_id: Optional[UUID] = None
    base_location_code: Optional[str] = None
    base_location_name: Optional[str] = None
    updated_at: Optional[datetime] = None