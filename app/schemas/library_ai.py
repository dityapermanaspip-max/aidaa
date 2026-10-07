from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class LibraryDraftRequest(BaseModel):
    type_id: UUID
    source_text: str = Field(..., min_length=50, max_length=30000)  # pasted report text, upload and looping come later
    instruction: Optional[str] = Field(None, max_length=1000)
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = None


class DraftProcedure(BaseModel):
    procedure_text: str = Field(..., min_length=1)
    expected_evidence: Optional[str] = None
    estimated_hours: Optional[float] = Field(0, ge=0, le=999999.99)


class DraftPka(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    objective: Optional[str] = None
    procedures: List[DraftProcedure] = Field(..., min_length=1)

    @field_validator("procedures", mode="before")
    @classmethod
    def _plain_strings(cls, v):
        # small models sometimes answer with plain strings instead of objects
        if isinstance(v, list):
            return [{"procedure_text": x} if isinstance(x, str) else x for x in v]
        return v


class LibraryDraft(BaseModel):
    pkas: List[DraftPka] = Field(..., min_length=1)