"""HTTP contracts: case facts are user allegations, never verified legal records."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nyaysaathi.action_package import EvidenceChecklist, Readiness
from nyaysaathi.models import CaseFile


Language = Literal["en", "hi", "hinglish"]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(RequestModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12_000)


class CaseRequest(RequestModel):
    case: CaseFile = Field(default_factory=CaseFile)
    history: list[Message] = Field(default_factory=list, max_length=12)

    @field_validator("case")
    @classmethod
    def bounded_case(cls, value):
        if len(value.model_dump_json().encode("utf-8")) > 24_000:
            raise ValueError("Case exceeds the request limit")
        return value

    @field_validator("history")
    @classmethod
    def bounded_history(cls, value):
        if sum(len(item.content) for item in value) > 24_000:
            raise ValueError("Conversation context exceeds the request limit")
        return value


class ChatRequest(CaseRequest):
    message: str = Field(min_length=1, max_length=12_000)
    language: Language = "en"

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A message is required")
        return value.strip()


class PackageRequest(CaseRequest):
    language: Literal["en", "hi"] = "en"
    provisional: bool = False


class SafeError(BaseModel):
    code: str
    message: str


class Citation(BaseModel):
    source_id: str
    title: str
    url: str
    explanation: str
    next_step: str
    limitation: str
    location: str
    date_checked: str


class GuidanceResponse(BaseModel):
    status: str
    language: Language
    message: str
    citations: list[Citation] = Field(default_factory=list)


class ChatResponse(BaseModel):
    case: CaseFile
    reply: str
    guidance: GuidanceResponse
    missing_information: list[str]
    readiness: Readiness
    fingerprint: str
    error: SafeError | None = None


class PackageContent(BaseModel):
    complaint: str
    summary: str
    checklist: EvidenceChecklist
    fingerprint: str
    language: Literal["en", "hi"]


class PackageResponse(BaseModel):
    readiness: Readiness
    package: PackageContent | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    application: str = "NyaySaathi AI"
