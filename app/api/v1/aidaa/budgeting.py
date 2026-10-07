from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    budget_read, budget_draft, assignment_update, check_org_permission, log_audit,
)
from app.schemas.budget import (
    BudgetLineCreate, BudgetLineUpdate, BudgetLineOut,
    FundingAllocCreate, FundingAllocOut, BudgetSummaryOut,
)
from app.services import budgets as svc
from app.services import assignment_funding as fsvc
from app.services.roles import assert_assignment_visible

router = APIRouter()


def _line_org_check(db: Session, user, line: dict, code: str):
    if line["plan_id"]:
        check_org_permission(db, user, code, "plan", line["plan_id"])
    else:
        check_org_permission(db, user, code, "assignment", line["assignment_id"])


# --- Plan budget lines ---

@router.get("/plan/{plan_id}/budget-lines", response_model=List[BudgetLineOut])
def list_plan_lines(plan_id: UUID, version_no: Optional[int] = None,
                    db: Session = Depends(get_db), user=Depends(budget_read)):
    check_org_permission(db, user, "audit.budget.read", "plan", plan_id)
    return svc.list_plan_lines(db, plan_id, version_no)


@router.post("/plan/{plan_id}/budget-lines", response_model=BudgetLineOut, status_code=201)
def create_plan_line(plan_id: UUID, payload: BudgetLineCreate,
                     db: Session = Depends(get_db), user=Depends(budget_draft)):
    check_org_permission(db, user, "audit.budget.draft", "plan", plan_id)
    row = svc.create_plan_line(db, plan_id, payload, user.user_id)
    log_audit(db, user.user_id, "budget_line.create", "budget_line", row["line_id"],
              {"plan_id": str(plan_id), "version_no": row["version_no"], "amount": float(row["amount"])})
    db.commit()
    return row


@router.post("/plan/{plan_id}/budget-lines/carry-over", response_model=List[BudgetLineOut], status_code=201)
def carry_over(plan_id: UUID, db: Session = Depends(get_db), user=Depends(budget_draft)):
    check_org_permission(db, user, "audit.budget.draft", "plan", plan_id)
    rows = svc.carry_over_plan_lines(db, plan_id, user.user_id)
    log_audit(db, user.user_id, "budget_line.carry_over", "audit_plan", plan_id, {"lines": len(rows)})
    db.commit()
    return rows


# --- Assignment budget lines, summary and funding ---

@router.get("/assignment/{assignment_id}/budget-lines", response_model=List[BudgetLineOut])
def list_assignment_lines(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(budget_read)):
    check_org_permission(db, user, "audit.budget.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)
    return svc.list_assignment_lines(db, assignment_id)


@router.post("/assignment/{assignment_id}/budget-lines", response_model=BudgetLineOut, status_code=201)
def create_assignment_line(assignment_id: UUID, payload: BudgetLineCreate,
                           db: Session = Depends(get_db), user=Depends(budget_draft)):
    check_org_permission(db, user, "audit.budget.draft", "assignment", assignment_id)
    row = svc.create_assignment_line(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "budget_line.create", "budget_line", row["line_id"],
              {"assignment_id": str(assignment_id), "amount": float(row["amount"])})
    db.commit()
    return row


@router.get("/assignment/{assignment_id}/budget-summary", response_model=BudgetSummaryOut)
def budget_summary(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(budget_read)):
    check_org_permission(db, user, "audit.budget.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)
    return fsvc.get_summary(db, assignment_id)


@router.get("/assignment/{assignment_id}/funding", response_model=List[FundingAllocOut])
def list_funding(assignment_id: UUID, db: Session = Depends(get_db), user=Depends(budget_read)):
    check_org_permission(db, user, "audit.budget.read", "assignment", assignment_id)
    assert_assignment_visible(db, user.user_id, assignment_id)
    return fsvc.list_funding(db, assignment_id)


@router.post("/assignment/{assignment_id}/funding", response_model=FundingAllocOut, status_code=201)
def upsert_funding(assignment_id: UUID, payload: FundingAllocCreate,
                   db: Session = Depends(get_db), user=Depends(assignment_update)):
    check_org_permission(db, user, "audit.assignment.update", "assignment", assignment_id)
    row = fsvc.upsert_funding(db, assignment_id, payload, user.user_id)
    log_audit(db, user.user_id, "assignment.funding_set", "assignment", assignment_id,
              {"funding_id": str(payload.funding_id), "amount": payload.amount})
    db.commit()
    return row


@router.delete("/assignment/{assignment_id}/funding/{funding_id}", status_code=204)
def delete_funding(assignment_id: UUID, funding_id: UUID,
                   db: Session = Depends(get_db), user=Depends(assignment_update)):
    check_org_permission(db, user, "audit.assignment.update", "assignment", assignment_id)
    fsvc.delete_funding(db, assignment_id, funding_id)
    log_audit(db, user.user_id, "assignment.funding_remove", "assignment", assignment_id,
              {"funding_id": str(funding_id)})
    db.commit()


# --- Single line ---

@router.patch("/budget-lines/{line_id}", response_model=BudgetLineOut)
def update_line(line_id: UUID, payload: BudgetLineUpdate,
                db: Session = Depends(get_db), user=Depends(budget_draft)):
    _line_org_check(db, user, svc.get_line(db, line_id), "audit.budget.draft")
    row = svc.update_line(db, line_id, payload, user.user_id)
    log_audit(db, user.user_id, "budget_line.update", "budget_line", line_id,
              payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return row


@router.delete("/budget-lines/{line_id}", status_code=204)
def delete_line(line_id: UUID, db: Session = Depends(get_db), user=Depends(budget_draft)):
    _line_org_check(db, user, svc.get_line(db, line_id), "audit.budget.draft")
    svc.delete_line(db, line_id, user.user_id)
    log_audit(db, user.user_id, "budget_line.delete", "budget_line", line_id)
    db.commit()