"""Execution schemas: kuesioner (procedure-linked questionnaires, batch 07).

Split out of the old monolithic execution.py by domain; re-exported from app.schemas.execution.
"""
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field

QuestionKind = Literal["single_choice", "multi_select", "free_text", "scale"]


class QuestionnaireCreate(BaseModel):
    procedure_id: UUID
    unit_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    intro: Optional[str] = None
    respondents_needed: int = Field(1, ge=1)


class QuestionnaireUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    intro: Optional[str] = None
    respondents_needed: Optional[int] = Field(None, ge=1)


class QuestionnaireQuestionIn(BaseModel):
    kind: QuestionKind
    question_text: str = Field(..., min_length=1, max_length=500)
    choices: Optional[List[str]] = None
    scale_max: Optional[int] = None


class QuestionOut(BaseModel):
    question_id: UUID
    questionnaire_id: UUID
    question_no: int
    kind: str
    question_text: str
    choices: Optional[List[str]] = None
    scale_max: Optional[int] = None


class QuestionnaireOut(BaseModel):
    questionnaire_id: UUID
    procedure_id: UUID
    assignment_id: UUID
    unit_id: UUID
    unit_code: Optional[str] = None
    title: str
    intro: Optional[str] = None
    status: str
    respondents_needed: int
    public_token: UUID
    link_expires_at: Optional[datetime] = None
    issued_at: Optional[datetime] = None
    question_count: int
    responses_count: int
    created_at: datetime
    updated_at: datetime


# Team planning row: every non-skipped procedure of the assignment LEFT JOINed with its
# questionnaire, so the UI can flag, build, issue and monitor coverage in one table.
class QuestionnaireProcedureOut(BaseModel):
    procedure_id: UUID
    pka_id: UUID
    pka_title: str
    step_no: int
    procedure_text: str
    needs_questionnaire: bool
    questionnaire_id: Optional[UUID] = None
    questionnaire_title: Optional[str] = None
    questionnaire_intro: Optional[str] = None
    questionnaire_status: Optional[str] = None
    respondents_needed: Optional[int] = None
    question_count: Optional[int] = None
    responses_count: Optional[int] = None
    public_token: Optional[UUID] = None
    link_expires_at: Optional[datetime] = None


class NeedsQuestionnaireIn(BaseModel):
    needs_questionnaire: bool


class QuestionnaireAnswerIn(BaseModel):
    question_id: UUID
    single_index: Optional[int] = Field(None, ge=1)
    multi_indexes: Optional[List[int]] = None
    scale_value: Optional[int] = Field(None, ge=1)
    text_value: Optional[str] = Field(None, max_length=2000)  # anonymous write, so the free text is capped


class QuestionnaireResponseIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    position: str = Field(..., min_length=1, max_length=150)
    age: int = Field(..., ge=0, le=130)
    last_degree: str = Field(..., min_length=1, max_length=100)
    gender: Literal["L", "P"]
    answers: List[QuestionnaireAnswerIn] = Field(..., min_length=1)


# Anonymous public surface: questionnaire text plus questions and bare counters only - never the
# token itself, the stored responses or the team results.
class PublicQuestionnaireOut(BaseModel):
    title: str
    intro: Optional[str] = None
    respondents_needed: int
    responses_count: int
    link_expires_at: datetime
    questions: List[QuestionOut]


class ProgressOut(BaseModel):
    responses_count: int
    respondents_needed: int


class OptionCount(BaseModel):
    label: str
    count: int


class QuestionResults(BaseModel):
    question_id: UUID
    question_no: int
    kind: str
    question_text: str
    choices: Optional[List[str]] = None
    scale_max: Optional[int] = None
    option_counts: Optional[List[OptionCount]] = None
    scale_counts: Optional[List[OptionCount]] = None
    average: Optional[float] = None
    texts: Optional[List[str]] = None


class RespondentRow(BaseModel):
    name: str
    position: str
    age: int
    last_degree: str
    gender: str
    submitted_via: str


class ResultsOut(BaseModel):
    questionnaire_id: UUID
    title: str
    status: str
    respondents_needed: int
    responses_count: int
    respondents: List[RespondentRow]
    questions: List[QuestionResults]


__all__ = [
    "QuestionKind",
    "QuestionnaireCreate", "QuestionnaireUpdate", "QuestionnaireQuestionIn", "QuestionOut",
    "QuestionnaireOut", "QuestionnaireProcedureOut", "NeedsQuestionnaireIn",
    "QuestionnaireAnswerIn", "QuestionnaireResponseIn",
    "PublicQuestionnaireOut", "ProgressOut", "OptionCount", "QuestionResults",
    "RespondentRow", "ResultsOut",
]
