"""Small local knowledge base and explainable keyword retrieval. No network I/O."""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, model_validator

from nyaysaathi.models import CaseFile


Language = Literal["en", "hi", "hinglish"]
OFFICIAL_HOSTS = {
    "www.indiacode.nic.in", "indiacode.nic.in", "consumeraffairs.gov.in",
    "consumerhelpline.gov.in", "e-jagriti.gov.in",
}
DATA_FILE = Path(__file__).resolve().parent / "data" / "legal_knowledge.json"


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    topic: str
    keywords: list[str]
    guidance: dict[Language, str]
    next_step: dict[Language, str]
    limitation: dict[Language, str]
    source_title: str
    source_url: str
    provision_or_location: str
    date_checked: date
    review_after: date
    kind: Literal["legal_information", "official_service", "practical_caution"]

    @model_validator(mode="after")
    def require_auditable_source(self) -> "KnowledgeEntry":
        url = urlparse(self.source_url)
        if url.scheme != "https" or url.hostname not in OFFICIAL_HOSTS or url.username or url.password:
            raise ValueError("Knowledge sources must use an approved official HTTPS host")
        for texts in (self.guidance, self.next_step, self.limitation):
            if set(texts) != {"en", "hi", "hinglish"} or not all(texts.values()):
                raise ValueError("Audited text is required in all three supported languages")
        if self.review_after < self.date_checked:
            raise ValueError("Invalid review interval")
        return self


@lru_cache(maxsize=1)
def load_knowledge() -> tuple[KnowledgeEntry, ...]:
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    entries = tuple(KnowledgeEntry.model_validate(record) for record in records)
    if len({entry.source_id for entry in entries}) != len(entries):
        raise ValueError("Duplicate source IDs")
    return entries


@dataclass(frozen=True)
class RetrievalContext:
    entries: tuple[KnowledgeEntry, ...] = ()
    reasons: tuple[str, ...] = ()
    safety: str = "none"

    def as_payload(self) -> dict:
        return {
            "safety": self.safety,
            "selection_reasons": list(self.reasons),
            "records": [entry.model_dump(mode="json") for entry in self.entries],
        }


def matches(text: str, keyword: str) -> bool:
    # Bound Latin terms so 'fir' cannot match 'first' and 'tax' cannot match 'taxi'.
    if keyword.isascii() and keyword.replace(" ", "").replace("-", "").isalnum():
        return re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text) is not None
    return keyword in text


def detect_safety(question: str) -> str:
    text = question.casefold()
    groups = (
        ("threat_or_crime", (
            "threat", "threats", "threatened", "violence", "violent", "assault", "criminal",
            "fir", "police", "arrest", "injury", "धमकी", "हिंसा", "पुलिस", "गिरफ्तार",
            "dhamki", "maar dunga", "jaan se", "चोट",
        )),
        ("urgent_notice", (
            "legal notice", "court notice", "summons", "hearing", "deadline", "limitation",
            "appeal", "कानूनी नोटिस", "समन", "सुनवाई", "समय सीमा", "अपील", "tareekh kal",
        )),
        ("out_of_scope", (
            "divorce", "custody", "bail", "inheritance", "land dispute", "eviction",
            "landlord", "employment", "income tax", "तलाक", "जमानत", "विरासत", "जमीन",
            "kirayedar", "talaq", "talak", "naukri",
        )),
    )
    for status, terms in groups:
        if any(matches(text, term) for term in terms):
            return status
    return "none"


def retrieve(
    question: str, case: CaseFile, *, today: date | None = None, limit: int = 6,
) -> RetrievalContext:
    safety = detect_safety(question + " " + (case.user_summary or ""))
    if safety != "none":
        return RetrievalContext(safety=safety)
    today = today or datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    if case.incident_date is not None and case.incident_date > today:
        return RetrievalContext(safety="insufficient_sources")
    question = question.casefold()
    case_text = " ".join(filter(None, (
        case.issue_type, case.user_summary, case.desired_resolution,
    ))).casefold()
    try:
        entries = load_knowledge()
    except (OSError, ValueError):
        return RetrievalContext(safety="insufficient_sources")
    requested_sections = re.findall(r"(?:\bsection\s*|धारा\s*)([\d०-९]+)", question)
    if any(not any(
        re.search(r"(?<!\d)" + re.escape(number) + r"(?!\d)", entry.provision_or_location)
        for entry in entries
    ) for number in requested_sections):
        return RetrievalContext(safety="insufficient_sources")
    scored = []
    for entry in entries:
        if not entry.date_checked <= today <= entry.review_after:
            continue
        direct = [term for term in entry.keywords if matches(question, term)]
        case_hits = [term for term in entry.keywords if matches(case_text, term)]
        score = 5 * len(direct) + len(case_hits)
        if score:
            reason = f"{entry.source_id}: question={','.join(direct)}; case={','.join(case_hits)}"
            scored.append((score, entry.source_id, entry, reason))
    scored.sort(key=lambda row: (-row[0], row[1]))
    selected = scored[:limit]
    if not selected:
        return RetrievalContext(safety="insufficient_sources")
    return RetrievalContext(
        entries=tuple(row[2] for row in selected),
        reasons=tuple(row[3] for row in selected),
    )
