from datetime import date
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.masters_costing import CalcBasis


class SbmDraftRequest(BaseModel):
    source_text: str = Field(..., min_length=50, max_length=30000)  # ONE annex page per paste
    annex_label: str = Field(..., min_length=1, max_length=100)  # example: "PMK 54/2026 Lampiran I No. 31"
    effective_from: date
    effective_to: Optional[date] = None
    instruction: Optional[str] = Field(None, max_length=1000)
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = None

    @field_validator("effective_to")
    @classmethod
    def _dates(cls, v, info):
        start = info.data.get("effective_from")
        if v and start and v < start:
            raise ValueError("effective_to cannot be before effective_from")
        return v


def _grades(v):
    """None, a string or a list becomes a clean list of codes (max 30 chars each)."""
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    out = []
    for x in v:
        s = str(x).strip().upper().replace(" ", "_")
        if len(s) > 30:
            raise ValueError("each grade code is at most 30 characters")
        if s and s not in out:
            out.append(s)
    return out


# What the AI names. It never writes amounts, the code parser reads those.
class SbmComponent(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=150)
    calc_basis: CalcBasis
    column: str = Field(..., min_length=1, max_length=60)  # table column heading, example "FULLDAY"


class SbmBlock(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)  # example "b. Pejabat Eselon I dan II"
    grades: List[str] = []  # empty = all grades

    _g = field_validator("grades", mode="before")(_grades)


class SbmNaming(BaseModel):
    components: List[SbmComponent] = Field(..., min_length=1)
    blocks: List[SbmBlock] = Field(..., min_length=1)


# What the parser builds, and what the human reviews, edits and accepts.
class SbmRate(BaseModel):
    component_code: str = Field(..., min_length=1, max_length=30)
    location_code: str = Field(..., min_length=1, max_length=30)  # PROV-xx
    grade: List[str] = []
    amount: float = Field(..., ge=0)
    in_source: bool = True  # the amount text was found in the pasted source

    _g = field_validator("grade", mode="before")(_grades)


class SbmDraft(BaseModel):
    annex_label: str
    effective_from: date
    effective_to: Optional[date] = None
    components: List[SbmComponent] = Field(..., min_length=1)
    blocks: List[SbmBlock] = []
    rates: List[SbmRate] = Field(..., min_length=1)
    unknown_provinces: List[str] = []  # names in the text that the fixed province map did not know