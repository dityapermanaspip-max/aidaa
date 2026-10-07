from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import budget_read, budget_draft, check_org_permission, log_audit
from app.schemas.ai import SuggestionDecision, SuggestionOut
from app.schemas.plan_budget_ai import PlanBudgetRequest
from app.services import plan_budget_ai as svc

router = APIRouter()


@router.get("/{plan_id}/ai/budget-drafts", response_model=List[SuggestionOut])
def list_drafts(plan_id: UUID, status: Optional[str] = Query(None),
                db: Session = Depends(get_db), user=Depends(budget_read)):
    check_org_permission(db, user, "audit.budget.read", "plan", plan_id)
    return svc.list_drafts(db, user.user_id, plan_id, status)


@router.post("/{plan_id}/ai/budget-drafts", response_model=SuggestionOut, status_code=201)
def create_draft(plan_id: UUID, payload: Optional[PlanBudgetRequest] = None,
                 db: Session = Depends(get_db), user=Depends(budget_draft)):
    check_org_permission(db, user, "audit.budget.draft", "plan", plan_id)
    p = payload or PlanBudgetRequest()
    row = svc.generate_draft(db, plan_id, p, user.user_id)
    log_audit(db, user.user_id, "ai.plan_budget_draft", "ai_suggestion", row["suggestion_id"],
              {"plan_id": str(plan_id), "engine": row["engine"], "model": row["model_name"]})
    db.commit()
    return row


@router.get("/{plan_id}/ai/budget-drafts/{suggestion_id}", response_model=SuggestionOut)
def get_draft(plan_id: UUID, suggestion_id: UUID,
              db: Session = Depends(get_db), user=Depends(budget_read)):
    check_org_permission(db, user, "audit.budget.read", "plan", plan_id)
    return svc.get_draft(db, user.user_id, plan_id, suggestion_id)


@router.post("/{plan_id}/ai/budget-drafts/{suggestion_id}/decide", response_model=SuggestionOut)
def decide_draft(plan_id: UUID, suggestion_id: UUID, payload: SuggestionDecision,
                 db: Session = Depends(get_db), user=Depends(budget_draft)):
    check_org_permission(db, user, "audit.budget.draft", "plan", plan_id)
    row = svc.decide_draft(db, plan_id, suggestion_id, payload, user.user_id)
    log_audit(db, user.user_id, f"ai.plan_budget_draft_{payload.decision}", "ai_suggestion", suggestion_id,
              {"plan_id": str(plan_id)})
    db.commit()
    return row