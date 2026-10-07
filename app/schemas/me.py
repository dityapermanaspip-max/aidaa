from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


class AssignmentAccessOut(BaseModel):
    assignment_id: UUID
    assignment_role: Optional[str] = None  # supervisor, leader, member, or None
    is_auditee_pic: bool = False
    global_roles: List[str] = []
    actions: List[str] = []