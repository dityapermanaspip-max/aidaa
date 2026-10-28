"""Schemas for the expertise extraction helper: pasted certificate text to pending rows."""
from typing import List, Literal, Optional
from re import match as _re_match

from pydantic import BaseModel, Field, field_validator


class ExpertiseExtractRequest(BaseModel):
    # Pasted certificate, decree or course-attendant text for ONE auditor.
    source_text: str = Field(..., min_length=20, max_length=30000)
    instruction: Optional[str] = Field(None, max_length=1000)
    engine: Optional[Literal["OLLAMA", "WEB_API"]] = None
    model: Optional[str] = Field(None, max_length=100)  # audit #7


def _clean_date(v) -> Optional[str]:
    """A sloppy AI date is easier to drop than to reject the whole extraction on."""
    return v.strip() if (isinstance(v, str) and _re_match(r"^\d{4}-\d{2}-\d{2}$", v.strip())) else None


class ExtractedCertificate(BaseModel):
    expertise_type: Literal["certification", "degree", "training", "past_experience"]
    title: str = Field(..., min_length=1, max_length=200)
    issuer: Optional[str] = Field(None, max_length=200)
    issued_date: Optional[str] = None   # YYYY-MM-DD, cleaner drops anything else
    expiry_date: Optional[str] = None

    _i = field_validator("issued_date", mode="before")(_clean_date)
    _e = field_validator("expiry_date", mode="before")(_clean_date)


class ExpertiseExtract(BaseModel):
    certificates: List[ExtractedCertificate] = Field(..., min_length=1, max_length=10)
