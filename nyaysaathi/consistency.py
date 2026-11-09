"""Conservative narrative invalidation, never global string replacement."""

from decimal import Decimal, InvalidOperation
import re

from nyaysaathi.models import CaseFile


SCALAR_FACTS = frozenset({"issue_type", "company_or_seller", "amount_inr", "incident_date", "desired_resolution"})
AMBIGUITY = re.compile(
    r"\b(?:contradictory|conflicting|cannot confirm|can't confirm|not sure|am unsure|is uncertain|"
    r"do not know which|don't know which)\b|पुष्टि नहीं|निश्चित नहीं|पक्का नहीं|विरोधाभास|"
    r"sure nahi|confirm nahi|pata nahi kaun",
    re.IGNORECASE,
)
FIELD_WORDS = {
    "amount_inr": r"\b(?:amount|price|paid|cost)\b|राशि|कीमत|भुगतान",
    "incident_date": r"\b(?:date|dates)\b|तारीख|दिनांक|तिथि",
    "company_or_seller": r"\b(?:seller|company)\b|विक्रेता|कंपनी",
    "desired_resolution": r"\bresolution\b|समाधान",
    "issue_type": r"\bissue type\b|समस्या की श्रेणी",
}
MONEY = re.compile(r"(?:₹|\bRs\.?|\bINR)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", re.IGNORECASE)
MONTH = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर)"
)
DAY = r"(?:3[01]|[12][0-9]|0?[1-9])"
PURCHASE_DATE_VALUE = re.compile(
    rf"(?<!\w)(?P<day_month>{MONTH}\s+{DAY}|{DAY}\s+{MONTH})(?:,?\s+(?P<year>\d{{4}}))?(?!\w)", re.IGNORECASE,
)
DATE_MENTION = re.compile(
    rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}\s+{MONTH}\s+\d{{4}}|{MONTH}\s+\d{{1,2}},?\s+\d{{4}})\b",
    re.IGNORECASE,
)

REVIEW_NOTICE = {
    "en": "Earlier narrative assertions were cleared after a correction, withdrawal, or potential conflict. "
          "Review current fields and supply a fresh neutral description when editing the draft.",
    "hi": "सुधार, वापसी या संभावित विरोधाभास के बाद पहले का विवरण हटाया गया है। "
          "वर्तमान फ़ील्ड जाँचें और मसौदा संपादित करते समय नया निष्पक्ष विवरण दें।",
    "hinglish": "Correction, withdrawal ya possible conflict ke baad purana narrative hata diya gaya hai. "
                "Current fields review karein aur draft edit karte waqt fresh neutral description dein.",
}
CLARIFY = {
    "en": {
        "amount_inr": "What amount can you confirm for this grievance?",
        "incident_date": "Which incident date can you confirm from your records?",
        "purchase_date_text": "What purchase date can you confirm from the order record?",
        "company_or_seller": "Which seller or platform did you order from?",
        "desired_resolution": "What resolution are you requesting now?",
        "issue_type": "What consumer problem can you confirm?",
    },
    "hi": {
        "amount_inr": "इस शिकायत के लिए किस राशि की पुष्टि कर सकते हैं?",
        "incident_date": "अपने रिकॉर्ड से किस घटना की तारीख की पुष्टि कर सकते हैं?",
        "purchase_date_text": "ऑर्डर रिकॉर्ड से आप खरीद की कौन-सी तारीख की पुष्टि कर सकते हैं?",
        "company_or_seller": "आपने किस विक्रेता या प्लेटफ़ॉर्म से ऑर्डर किया था?",
        "desired_resolution": "अब आप क्या समाधान चाहते हैं?",
        "issue_type": "किस उपभोक्ता समस्या की पुष्टि कर सकते हैं?",
    },
    "hinglish": {
        "amount_inr": "Is grievance ke liye kaunsi amount confirm kar sakte hain?",
        "incident_date": "Apne records se kaunsi incident date confirm kar sakte hain?",
        "purchase_date_text": "Order record se kaunsi purchase date confirm kar sakte hain?",
        "company_or_seller": "Aapne kis seller ya platform se order kiya tha?",
        "desired_resolution": "Ab aap kya resolution chahte hain?",
        "issue_type": "Kaunsi consumer problem confirm kar sakte hain?",
    },
}


def possible_stale_assertion(case: CaseFile, text: str) -> bool:
    """Backup for legacy records lacking a correction marker. No inferred replacements.

    Currency conflicts and explicit dates when the scalar date is unknown are
    review triggers, not claims that this parser understands every event/date.
    """
    for amount in MONEY.findall(text):
        try:
            if case.amount_inr is None or Decimal(amount.replace(",", "")) != case.amount_inr:
                return True
        except InvalidOperation:
            return True
    if case.incident_date is not None:
        return False
    purchase_date = " ".join((case.purchase_date_text or "").replace(",", "").casefold().split())
    return any(" ".join(match[0].replace(",", "").casefold().split()) != purchase_date
               for match in DATE_MENTION.finditer(text))


def unresolved_fields(text: str) -> set[str]:
    """Conservative, field-specific uncertainty cues; never infer a replacement."""
    unresolved = set()
    # Do not let "dates conflict" invalidate an unrelated following sentence
    # such as "Seller and amount are unchanged."
    clauses = re.split(r"[.!?;।\n]+|,\s+(?=[A-Za-z\u0900-\u097f])", text)
    for clause in clauses:
        if AMBIGUITY.search(clause):
            unresolved.update(field for field, pattern in FIELD_WORDS.items()
                              if re.search(pattern, clause, re.IGNORECASE))
    return unresolved


def protect_narratives(case: CaseFile) -> CaseFile:
    """Return a safe copy. Unknown provenance invalidates the whole narrative.

    The marker stays sticky: old conversation quotes cannot silently resurrect
    a superseded summary/timeline on a subsequent model turn.
    """
    safe = CaseFile.model_validate(case.model_dump())
    narrative = " ".join([safe.user_summary or "", *safe.timeline])
    if not (safe.narrative_review_required or safe.uncertain_fields or possible_stale_assertion(safe, narrative)):
        return safe
    safe.narrative_review_required = True
    for field in safe.uncertain_fields:
        if field == "purchase_date_text":
            # An unresolved year may still have a confirmed day and month.
            partial = PURCHASE_DATE_VALUE.fullmatch(safe.purchase_date_text or "")
            safe.purchase_date_text = partial["day_month"] if partial else None
        else:
            setattr(safe, field, None)
    safe.user_summary = None
    safe.timeline = []
    safe.evidence_missing = []
    safe.confidence_or_uncertainty = REVIEW_NOTICE[safe.user_language or "en"]
    # These free-text descriptors can also embed a superseded price/date.
    # Drop the complete descriptor/entry when dependence cannot be established.
    for field in ("issue_type", "desired_resolution"):
        value = getattr(safe, field)
        if value and possible_stale_assertion(safe, value):
            setattr(safe, field, None)
    safe.evidence_available = [
        text for text in safe.evidence_available if not possible_stale_assertion(safe, text)
    ]
    return safe


def consistency_question(case: CaseFile, language: str) -> str | None:
    """Ask for an unresolved fact. Narrative review by itself is a notice."""
    language = language if language in CLARIFY else "en"
    if case.uncertain_fields:
        return CLARIFY[language][next(iter(case.uncertain_fields))]
    for field in ("company_or_seller", "desired_resolution", "issue_type"):
        if getattr(case, field) is None:
            return CLARIFY[language][field]
    return None
