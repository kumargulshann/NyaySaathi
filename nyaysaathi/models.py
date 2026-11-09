"""Structured case data. Defaults must never imply facts about a grievance."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


class CaseFile(BaseModel):
    """An empty case is valid; missing facts stay unknown until supplied."""

    model_config = ConfigDict(extra="forbid")

    issue_type: str | None = None
    user_language: Literal["en", "hi", "hinglish"] | None = None
    user_summary: str | None = None
    company_or_seller: str | None = None
    amount_inr: Decimal | None = Field(default=None, ge=0)
    incident_date: date | None = None
    # App-owned literal purchase details. A partial date is never an incident date.
    product_or_service: str | None = None
    purchase_date_text: str | None = None
    timeline: list[str] = Field(default_factory=list)
    evidence_available: list[str] = Field(default_factory=list)
    evidence_missing: list[str] = Field(default_factory=list)
    desired_resolution: str | None = None
    unanswered_questions: list[str] = Field(default_factory=list)
    confidence_or_uncertainty: str | None = None
    case_status: Literal["not_started", "in_progress", "ready_for_review"] = "not_started"
    # App-owned consistency metadata; Gemini's FactChange cannot set these fields.
    narrative_review_required: bool = False
    uncertain_fields: dict[
        Literal["issue_type", "company_or_seller", "amount_inr", "incident_date", "purchase_date_text", "desired_resolution"],
        Literal["withdrawn", "conflicting"],
    ] = Field(default_factory=dict)


class FactChange(BaseModel):
    """A proposed change grounded in the user's words, not an assistant reply."""

    model_config = ConfigDict(extra="forbid")

    field: Literal[
        "issue_type", "user_language", "user_summary", "company_or_seller",
        "amount_inr", "incident_date", "timeline", "evidence_available",
        "desired_resolution",
    ]
    # Amounts are decimal strings; dates are ISO strings. CaseFile validates both.
    value: str | list[str] | None
    source_quote: str = Field(min_length=1)
    is_correction: bool = False


class GuidanceSelection(BaseModel):
    """A source choice and an exact, audited plain-language statement."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=60)
    explanation: str = Field(min_length=1, max_length=1800)


class IntakeResponse(BaseModel):
    """A structured intake question, or a completed-intake handoff."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["in_scope", "out_of_scope", "unclear"]
    reply_language: Literal["en", "hi", "hinglish"]
    changes: list[FactChange] = Field(default_factory=list, max_length=20)
    evidence_missing: list[str] = Field(default_factory=list, max_length=15)
    missing_details: list[str] = Field(default_factory=list, max_length=15)
    uncertainty: str | None = None
    case_status: Literal["in_progress", "ready_for_review"] = "in_progress"
    next_question: str | None = Field(default=None, max_length=350)
    guidance: list[GuidanceSelection] = Field(default_factory=list, max_length=4)
    safety_flag: Literal[
        "none", "urgent_notice", "threat_or_crime", "out_of_scope", "insufficient_sources"
    ] = "none"

    @model_validator(mode="after")
    def require_one_question(self) -> "IntakeResponse":
        if self.scope != "out_of_scope":
            completed = self.scope == "in_scope" and self.case_status == "ready_for_review"
            if (not self.next_question or not self.next_question.strip()) and not completed:
                raise PydanticCustomError("missing_intake_question", "An intake turn must ask one question")
            if self.next_question and self.next_question.count("?") + self.next_question.count("？") > 1:
                raise PydanticCustomError("multiple_intake_questions", "Ask one question at a time")
        return self
