"""Layer 2: the caller's role inside one assignment, and audit-team vs auditee-PIC access."""
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps_org import check_org_permission, get_user_accessible_org_ids
from app.services.roles import (
    assignment_scope, assert_assignment_visible, my_assignment_role, pic_unit_orgs,
)

ROLES_WORK = ("member", "leader")
ROLES_LEAD = ("leader",)
ROLES_SUP = ("supervisor",)
ROLES_LEAD_SUP = ("leader", "supervisor")


def authorize_assignment(db: Session, user, code: str, assignment_id: UUID, roles=None) -> Optional[str]:
    """Layer 1 (org of the assignment) then Layer 2 (assignment role). Returns the caller's role."""
    check_org_permission(db, user, code, "assignment", assignment_id)
    role = my_assignment_role(db, user.user_id, assignment_id)
    if roles is not None and role not in roles:
        raise HTTPException(status_code=403,
                            detail=f"Assignment role {list(roles)} required, yours is {role or 'none (not on the team)'}")
    return role


def authorize_view(db: Session, user, code: str, assignment_id: UUID) -> str:
    """Read access. Returns 'team' (audit side) or 'pic' (auditee PIC of ANY audited unit, after issue)."""
    scope = assignment_scope(db, assignment_id)
    org_ids = get_user_accessible_org_ids(db, user.user_id, code)
    if org_ids is None or scope["owner_org_id"] in org_ids:
        assert_assignment_visible(db, user.user_id, assignment_id)
        return "team"
    if scope["status"] != "draft":
        mine = [o for o in pic_unit_orgs(db, user.user_id, scope["unit_org_ids"]) if o in org_ids]
        if mine:
            return "pic"
    raise HTTPException(status_code=403, detail="Access denied: assignment is outside your organizations")


def authorize_pic(db: Session, user, code: str, assignment_id: UUID):
    if authorize_view(db, user, code, assignment_id) != "pic":
        raise HTTPException(status_code=403, detail="Only the auditee PIC of this unit can do this")