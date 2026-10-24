"""Execution schemas: plan deviation and Monev Temuan (cross-assignment monitoring).

Split out of the old monolithic execution.py by domain; re-exported from app.schemas.execution.
"""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


# --- Plan deviation (read-only, aidaa_core.v_plan_deviation) ---

class DeviationOut(BaseModel):
    assignment_id: UUID
    assignment_no: str
    plan_id: Optional[UUID] = None
    plan_no: Optional[str] = None
    is_unplanned: bool
    planned_auditors: Optional[int] = None
    actual_auditors: int
    planned_days: Optional[int] = None
    actual_days: int
    planned_man_days: Optional[int] = None
    actual_man_days: int
    planned_budget: Optional[float] = None
    actual_budget: float
    leader_changed: Optional[bool] = None
    pka_planned_days: Optional[float] = None


# --- Monev Temuan (cross-assignment findings/rekomendasi monitoring) ---

class MonevFindingOut(BaseModel):
    finding_id: UUID
    assignment_id: UUID
    assignment_no: str
    finding_no: str
    title: str
    status: str
    materiality_amount: float
    communicated_at: Optional[datetime] = None
    response_due_date: Optional[date] = None
    no_response: bool = False
    under_review: bool = False
    unit_names: Optional[str] = None


class MonevRekomendOut(BaseModel):
    rekomend_id: UUID
    finding_id: UUID
    assignment_id: UUID
    assignment_no: str
    finding_no: str
    finding_title: str
    rekomend_no: str
    recommendation_text: str
    due_date: Optional[date] = None
    status: str
    followup_at: Optional[datetime] = None
    last_monitored_at: Optional[datetime] = None
    overdue: bool = False
    closed_during_audit: bool
    closed_at: Optional[datetime] = None
    unit_names: Optional[str] = None


class MonevOut(BaseModel):
    findings: List[MonevFindingOut]
    rekomendasi: List[MonevRekomendOut]


__all__ = ["DeviationOut", "MonevFindingOut", "MonevRekomendOut", "MonevOut"]
