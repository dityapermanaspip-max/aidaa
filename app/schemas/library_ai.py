from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class LibraryDraftRequest(BaseModel):
    type_id: UUID
    source_text: str = Field(..., min_length=50, max_length=30000)  # pasted report text, upload and looping come later
    instruction: Optional[str] = Field(None, max_length=1000)
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = None


def _plain_strings(v):
    # small models sometimes answer with plain strings instead of objects
    if isinstance(v, list):
        return [{"procedure_text": x} if isinstance(x, str) else x for x in v]
    return v


class DraftProcedure(BaseModel):
    procedure_text: str = Field(..., min_length=1)
    expected_evidence: Optional[str] = None
    estimated_hours: Optional[float] = Field(0, ge=0, le=999999.99)


class DraftPka(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    objective: Optional[str] = None
    procedures: List[DraftProcedure] = Field(..., min_length=1)

    _plain = field_validator("procedures", mode="before")(_plain_strings)


class LibraryDraft(BaseModel):
    pkas: List[DraftPka] = Field(..., min_length=1)


# --- library_improvement: rewrite ONE library PKA; accept deactivates the old row ---

class LibraryImproveRequest(BaseModel):
    instruction: Optional[str] = Field(None, max_length=1000)
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = None


class LibraryImprovement(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    objective: Optional[str] = None
    procedures: List[DraftProcedure] = Field(..., min_length=1)

    _plain = field_validator("procedures", mode="before")(_plain_strings)
