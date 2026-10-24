"""Schemas for the team composition helper: view-only ranked candidates."""
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class TeamCandidate(BaseModel):
    auditor_id: UUID
    rank: int = Field(..., ge=1, le=99)
    reason: str = Field(..., min_length=1, max_length=300)  # one short sentence, why this person fits


class TeamSuggestion(BaseModel):
    candidates: List[TeamCandidate] = Field(..., min_length=1, max_length=8)
