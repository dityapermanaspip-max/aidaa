from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class PlanBudgetRequest(BaseModel):
    instruction: Optional[str] = Field(None, max_length=1000)
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = None


# What the AI answers: only on-site days per audited unit and why. It never writes amounts or rates.
class AiSite(BaseModel):
    unit_id: UUID
    days: float = Field(..., ge=0, le=365)
    reason: str = Field("", max_length=500)


class PlanBudgetNaming(BaseModel):
    sites: List[AiSite] = Field(..., min_length=1)


# What the service builds from the AI answer and the approved rates, and what the human edits.
class PlanBudgetLine(BaseModel):
    component_id: UUID
    component_code: str
    auditor_id: Optional[UUID] = None
    username: Optional[str] = None
    location_id: Optional[UUID] = None
    rate_id: Optional[UUID] = None  # empty for at_cost lines and for lines without a rate
    quantity: float = Field(..., ge=0)
    unit_rate: float = Field(0, ge=0)
    amount: float = Field(0, ge=0)
    basis: Literal["standard", "at_cost"] = "standard"
    status: Literal["ok", "no_rate", "manual"] = "ok"  # no_rate: nothing fits, manual: several fit or typed by hand
    note: Optional[str] = Field(None, max_length=500)


class PlanBudgetDraft(BaseModel):
    plan_id: UUID
    effort_hours: float = Field(0, ge=0)  # sum of library procedure hours for the plan's audit type
    effort_days: float = Field(0, ge=0)  # effort_hours / 8
    sites: List[AiSite] = []
    lines: List[PlanBudgetLine] = Field(..., min_length=1)
    warnings: List[str] = []