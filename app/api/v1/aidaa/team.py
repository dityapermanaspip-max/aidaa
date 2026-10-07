from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import team_read, team_manage, check_org_permission, log_audit
from app.schemas.team import MemberAdd, MemberEnd, MemberReplace, MemberRoleChange, MemberOut
from app.services import team as svc
from app.services.roles import assert_assignment_visible

router = APIRouter()


@router.get("/{assignment_id}/team", response_model=List[MemberOut])
def list_team(assignment_id: UUID, current_only: bool = True,
              db: Session = Depends(get_db), user=Depends(team_read)):
    check_org_permission(db, user, "audit.team.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)
    return svc.list_team(db, assignment_id, current_only)


@router.post("/{assignment_id}/team", response_model=MemberOut, status_code=201)
def add_member(assignment_id: UUID, payload: MemberAdd,
               db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "assignment", assignment_id)
    row = svc.add_member(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.member_add", "assignment", assignment_id,
              {"auditor_id": str(payload.auditor_id), "role": payload.role})
    db.commit()
    return row


@router.post("/{assignment_id}/team/from-plan", response_model=List[MemberOut], status_code=201)
def add_from_plan(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "assignment", assignment_id)
    rows = svc.add_from_plan(db, assignment_id, user.user_id)
    log_audit(db, user.user_id, "assignment.team_from_plan", "assignment", assignment_id)
    db.commit()
    return rows


@router.post("/{assignment_id}/team/{member_id}/end", response_model=MemberOut)
def end_member(assignment_id: UUID, member_id: UUID, payload: MemberEnd,
               db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "assignment", assignment_id)
    row = svc.remove_member(db, assignment_id, member_id, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.member_end", "assignment", assignment_id,
              {"member_id": str(member_id), "reason": payload.reason})
    db.commit()
    return row


@router.post("/{assignment_id}/team/{member_id}/replace", response_model=MemberOut, status_code=201)
def replace_member(assignment_id: UUID, member_id: UUID, payload: MemberReplace,
                   db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "assignment", assignment_id)
    row = svc.replace_member(db, assignment_id, member_id, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.member_replace", "assignment", assignment_id,
              payload.model_dump(mode="json"))
    db.commit()
    return row


@router.post("/{assignment_id}/team/{member_id}/role", response_model=MemberOut, status_code=201)
def change_role(assignment_id: UUID, member_id: UUID, payload: MemberRoleChange,
                db: Session = Depends(get_db), user=Depends(team_manage)):
    check_org_permission(db, user, "audit.team.manage", "assignment", assignment_id)
    row = svc.change_role(db, assignment_id, member_id, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.member_role", "assignment", assignment_id,
              payload.model_dump(mode="json"))
    db.commit()
    return row