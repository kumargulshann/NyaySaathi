"""Deterministic consumer preparation documents. No model, network, or UI calls."""

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Literal

from nyaysaathi.knowledge import detect_safety, matches
from nyaysaathi.models import CaseFile
from nyaysaathi.consistency import DATE_MENTION, protect_narratives


DocumentLanguage = Literal["en", "hi"]


def labels(en: str, hi: str) -> dict[str, str]:
    return {"en": en, "hi": hi}


FIELDS = {
    "company_or_seller": labels("Seller/company", "विक्रेता/कंपनी"),
    "user_summary": labels("Problem description", "समस्या का विवरण"),
    "desired_resolution": labels("Desired resolution", "इच्छित समाधान"),
    "incident_date": labels("Incident date and what it refers to", "घटना की तारीख और उसका संदर्भ"),
    "amount_inr": labels("Amount and what it refers to", "राशि और उसका संदर्भ"),
    "evidence_available": labels("Evidence availability", "साक्ष्य की उपलब्धता"),
}

READINESS_LABELS = {
    "ready": labels("Ready to draft", "मसौदा बनाने के लिए तैयार"),
    "missing": labels("Draft contains missing information", "मसौदे में जानकारी अधूरी है"),
    "insufficient": labels("Insufficient information", "जानकारी अपर्याप्त है"),
    "out_of_scope": labels("Out of scope", "दायरे से बाहर"),
}

# Free-text fields are user allegations, not a channel for threats or legal claims.
# If a field needs review, substitute a visible placeholder instead of rewriting it.
REVIEW_TEXT = re.compile(
    r"https?://|§|\b(?:section|article|rule)\s*\d|धारा\s*[\d०-९]|"
    r"\blegal notice\b|\blegally entitled\b|\b(?:jail|prison|penalty|penalties|kill|threat\w*)\b|"
    r"\b(?:entitled|statutory|mandatory|must|shall)\b|\b(?:act|code|rules?)\s*,?\s*(?:19|20)\d{2}\b|"
    r"\b(?:sue|punish|ruin|destroy|expose)\s+(?:you|your)\b|"
    r"\bor else\b|"
    r"\b(?:guaranteed|guarantee|definitely)\b.*\b(?:refund|compensation|win)\b|"
    r"\bwithin\s+\d+\s+(?:days?|hours?)\b|कानूनी नोटिस|धमकी|जेल|जुर्माना|मार दूँ|गारंटी",
    re.IGNORECASE,
)

COMMUNICATION = re.compile(
    r"\b(?:contacted|emailed|e-mailed|called|wrote to|messaged|requested|asked|sent|complained)\b|"
    r"संपर्क किया|ईमेल किया|मेल किया|शिकायत की|अनुरोध किया|भेजा|बात की|"
    r"(?:email|call|contact|message|request|complaint)\s+(?:kiya|ki|bheja|karke)",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(?:not|never|no|haven't|didn't|nahi|nahin)\b|नहीं|नही", re.IGNORECASE)
NO_COMMUNICATION = re.compile(
    r"\b(?:not|never|haven't|didn't)\s+(?:yet\s+)?(?:contact\w*|email\w*|call\w*|message\w*|request\w*|sent|send\w*)|"
    r"(?:संपर्क|ईमेल|मेल|शिकायत|अनुरोध|बात)\s+नहीं|(?:contact|email|call|message|request)\s+nahi",
    re.IGNORECASE,
)


def clean(value: str | None) -> str | None:
    if not value or not value.strip() or REVIEW_TEXT.search(value):
        return None
    # Keep document structure intact even when a single-line field contains newlines.
    return " ".join(value.split())


@dataclass(frozen=True)
class Readiness:
    status: str
    missing: tuple[str, ...]
    review: tuple[str, ...]
    provisional_allowed: bool


def assess_readiness(case: CaseFile, *, out_of_scope: bool = False) -> Readiness:
    scope_text = " ".join(filter(None, (case.issue_type, case.user_summary)))
    explicit_scope = (case.issue_type or "").casefold().replace("_", " ").strip()
    if out_of_scope or explicit_scope == "out of scope" or detect_safety(scope_text) != "none":
        return Readiness("out_of_scope", (), (), False)
    case = protect_narratives(case)
    review = tuple(name for name in ("company_or_seller", "user_summary", "desired_resolution")
                   if getattr(case, name) and clean(getattr(case, name)) is None)
    if any(clean(item) is None for item in case.timeline + case.evidence_available):
        review += ("timeline/evidence",)
    if case.narrative_review_required:
        review += ("narrative",)
    missing = []
    for name in FIELDS:
        value = getattr(case, name)
        if name == "evidence_available":
            known = any(clean(item) and not NEGATION.search(item) for item in value)
        elif name in ("incident_date", "amount_inr"):
            known = value is not None
        else:
            known = clean(value) is not None
        if not known:
            missing.append(name)
    if case.narrative_review_required and all(clean(value) for value in (
        case.issue_type, case.company_or_seller, case.desired_resolution,
    )):
        status = "missing"  # Structured facts can support a provisional draft.
    elif not clean(case.user_summary):
        status = "insufficient"
    else:
        status = "missing" if missing else "ready"
    provisional_allowed = bool(clean(case.user_summary) or clean(case.issue_type)) or (
        case.narrative_review_required and any((
            clean(case.company_or_seller), case.amount_inr is not None, case.incident_date is not None,
        ))
    )
    return Readiness(status, tuple(missing), review, provisional_allowed)


def case_fingerprint(case: CaseFile) -> str:
    case = protect_narratives(case)
    data = case.model_dump(mode="json", exclude={"case_status", "confidence_or_uncertainty"})
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceChecklist:
    reported: tuple[str, ...]
    collect: tuple[str, ...]
    unknown: tuple[str, ...]


EVIDENCE = (
    (labels("Order confirmation", "ऑर्डर की पुष्टि"), ("order confirmation", "order email", "order details", "ऑर्डर पुष्टि"), "base"),
    (labels("Invoice or receipt", "बिल या रसीद"), ("invoice", "receipt", "bill", "बिल", "रसीद", "चालान"), "base"),
    (labels("Payment proof", "भुगतान का प्रमाण"), ("payment", "bank statement", "upi", "भुगतान"), "base"),
    (labels("Delivery tracking", "डिलीवरी ट्रैकिंग"), ("tracking", "shipment record", "ट्रैकिंग"), "delivery"),
    (labels("Photos/videos (if defects are involved)", "फोटो/वीडियो (खराबी होने पर)"), ("photo", "video", "फोटो", "तस्वीर", "वीडियो"), "defect"),
    (labels("Refund requests", "रिफंड के अनुरोध"), ("refund request", "return request", "refund email", "रिफंड अनुरोध", "वापसी अनुरोध"), "refund"),
    (labels("Seller/support communication", "विक्रेता/सहायता से बातचीत"), ("chat", "email", "message", "communication", "whatsapp", "संदेश", "पत्राचार"), "base"),
)


def evidence_checklist(case: CaseFile, language: DocumentLanguage) -> EvidenceChecklist:
    case = protect_narratives(case)
    reported = tuple(dict.fromkeys(
        clean(item) for item in case.evidence_available
        if clean(item) and not NEGATION.search(item)
    ))
    available_text = " ".join(reported).casefold()
    missing_text = " ".join(clean(item) or "" for item in case.evidence_missing).casefold()
    context = " ".join(clean(item) or "" for item in (
        case.issue_type, case.user_summary, case.desired_resolution,
    )).casefold()
    collect, unknown = [], []
    for name, aliases, relevance in EVIDENCE:
        # The reported group preserves the exact record description; it never
        # upgrades 'photo' into a verified photograph of a particular defect.
        if any(matches(available_text, alias) for alias in aliases):
            continue
        relevant = relevance == "base" or (
            relevance == "delivery" and any(term in context for term in ("deliver", "delivery", "डिलीवरी", "नहीं मिला"))
        ) or (
            relevance == "defect" and any(term in context for term in ("defect", "damage", "broken", "खराब", "kharab"))
        ) or (
            relevance == "refund" and any(term in context for term in ("refund", "रिफंड", "पैसे वापस"))
        )
        bucket = collect if relevant or any(matches(missing_text, alias) for alias in aliases) else unknown
        bucket.append(name[language])
    return EvidenceChecklist(reported, tuple(collect), tuple(unknown))


@dataclass(frozen=True)
class ActionPackage:
    complaint: str
    summary: str
    checklist: EvidenceChecklist
    readiness: Readiness
    fingerprint: str
    language: DocumentLanguage


def download_bytes(text: str) -> bytes:
    """UTF-8 BOM makes Hindi and rupee characters readable in common text editors."""
    return text.encode("utf-8-sig")


def generate_package(
    case: CaseFile, language: DocumentLanguage = "en", *, provisional: bool = False,
    out_of_scope: bool = False,
) -> ActionPackage:
    # Revalidate a fresh model even if a caller assigned invalid values after initialization.
    case = CaseFile.model_validate(case.model_dump())
    if language not in ("en", "hi"):
        raise ValueError("Choose English or Hindi for formal documents")
    readiness = assess_readiness(case, out_of_scope=out_of_scope)
    case = protect_narratives(case)
    if readiness.status == "out_of_scope":
        raise ValueError("Complaint generation is disabled outside consumer scope")
    if not readiness.provisional_allowed:
        raise ValueError("A consumer problem description or issue type is required")
    if readiness.status != "ready" and not provisional:
        raise ValueError("Explicitly choose a provisional draft with placeholders")
    hi = language == "hi"

    def t(en: str, hindi: str) -> str:
        return hindi if hi else en

    seller = clean(case.company_or_seller) or t("[Seller/company]", "[विक्रेता/कंपनी]")
    problem = clean(case.user_summary) or t("[Describe the consumer problem in neutral factual language]", "[उपभोक्ता समस्या का निष्पक्ष तथ्यात्मक विवरण]")
    if case.narrative_review_required:
        problem = t("[Fresh neutral description required after correction/conflict; earlier narrative was invalidated]",
                    "[सुधार/विरोधाभास के बाद नया निष्पक्ष विवरण आवश्यक है; पहले का विवरण हटाया गया]")
    resolution = clean(case.desired_resolution) or t("[Desired resolution]", "[इच्छित समाधान]")
    product = clean(case.product_or_service)
    recorded_purchase_date = clean(case.purchase_date_text)
    purchase_year_missing = bool(recorded_purchase_date and not DATE_MENTION.search(recorded_purchase_date))
    purchase_date = recorded_purchase_date or t("[Purchase date]", "[खरीद की तारीख]")
    if purchase_year_missing:
        purchase_date += t(" [Year]", " [वर्ष]")
    incident = case.incident_date.isoformat() if case.incident_date else t("[Incident date]", "[घटना की तारीख]")
    # amount_inr does not tell us whether money was paid, charged, requested, or refunded.
    amount = f"₹{case.amount_inr:,f}" if case.amount_inr is not None else t("[Amount in INR]", "[राशि रुपये में]")
    timeline = tuple(clean(item) for item in case.timeline if clean(item))
    attempts = tuple(item for item in timeline if COMMUNICATION.search(item) and not NO_COMMUNICATION.search(item))
    attempts_text = "\n".join(f"- {item}" for item in attempts) or t(
        "[Add previous communication only if it happened; otherwise say 'not contacted']",
        "[पिछला संपर्क हुआ हो तभी लिखें; अन्यथा 'संपर्क नहीं किया' लिखें]",
    )
    checklist = evidence_checklist(case, language)
    reported = "\n".join(f"- {item}" for item in checklist.reported) or t(
        "[Evidence availability not confirmed]", "[साक्ष्य की उपलब्धता की पुष्टि नहीं हुई है]",
    )
    timeline_text = "\n".join(f"- {item}" for item in timeline) or t("[Timeline not provided]", "[घटनाक्रम नहीं बताया गया]")
    if case.narrative_review_required:
        timeline_text = t("[Previous timeline invalidated; confirm events before adding them]",
                          "[पहले का घटनाक्रम हटाया गया; जोड़ने से पहले घटनाओं की पुष्टि करें]")
    complaint = "\n\n".join((
        t("Subject: Consumer complaint — ", "विषय: उपभोक्ता शिकायत — ") + (clean(case.issue_type) or t("[Issue]", "[समस्या]")),
        t("To: ", "प्रति: ") + seller,
        t("Dear Customer Support Team,", "माननीय ग्राहक सहायता टीम,"),
        t("I am writing about my consumer grievance. The following is my account of events, subject to review:",
          "मैं अपनी उपभोक्ता शिकायत के संबंध में लिख रहा/रही हूँ। नीचे मेरे बताए अनुसार घटनाओं का विवरण है; इसकी समीक्षा की जानी है:"),
        problem,
        t("Order/reference ID: [Order ID]\nProduct/service: ", "ऑर्डर/संदर्भ संख्या: [ऑर्डर आईडी]\nउत्पाद/सेवा: ")
        + (product or t("[Product/service]", "[उत्पाद/सेवा]"))
        + t("\nPurchase/order date: ", "\nखरीद/ऑर्डर की तारीख: ") + purchase_date,
        t("Reported incident date (confirm what this date refers to): ", "बताई गई घटना की तारीख (तारीख का संदर्भ स्पष्ट करें): ") + incident,
        t("Amount reported for this grievance (confirm whether price, payment or refund): ", "शिकायत में बताई गई राशि (कीमत, भुगतान या रिफंड का संदर्भ स्पष्ट करें): ") + amount,
        t("Timeline supplied by me:\n", "मेरे बताए अनुसार घटनाक्रम:\n") + timeline_text,
        t("Evidence I report having:\n", "मेरे बताए अनुसार उपलब्ध साक्ष्य:\n") + reported,
        t("Previous communication reported by me:\n", "मेरे बताए अनुसार पिछला संपर्क:\n") + attempts_text,
        t("My requested resolution: ", "मेरा अनुरोधित समाधान: ") + resolution,
        t("Please review my concern and provide a written response explaining the proposed resolution.",
          "कृपया मेरी शिकायत की समीक्षा करें और प्रस्तावित समाधान बताते हुए लिखित उत्तर दें।"),
        t("Thank you,\n[Your name]\n[Your contact details]", "धन्यवाद,\n[आपका नाम]\n[आपकी संपर्क जानकारी]"),
    ))
    missing = [FIELDS[name][language] for name in readiness.missing]
    missing += [t("Order ID", "ऑर्डर आईडी"), t("Name and contact details", "नाम और संपर्क जानकारी")]
    if purchase_year_missing:
        missing.append(t("Purchase year", "खरीद का वर्ष"))
    elif not recorded_purchase_date:
        missing.append(t("Purchase date", "खरीद की तारीख"))
    if not product:
        missing.append(t("Exact product/service", "सटीक उत्पाद/सेवा"))
    if not case.narrative_review_required:
        missing += [clean(item) for item in case.unanswered_questions if clean(item)]
    sections = (
        (t("Company/seller", "कंपनी/विक्रेता"), seller),
        (t("Product/service", "उत्पाद/सेवा"), product or t("[Product/service — confirm from your order]", "[उत्पाद/सेवा — ऑर्डर देखकर पुष्टि करें]")),
        (t("Issue category", "समस्या की श्रेणी"), clean(case.issue_type) or t("[Issue type]", "[समस्या की श्रेणी]")),
        (t("Transaction details", "लेनदेन का विवरण"), t("Order ID: [Order ID]\nPurchase date: ",
             "ऑर्डर आईडी: [ऑर्डर आईडी]\nखरीद की तारीख: ") + purchase_date + t("\nRecorded amount: ", "\nदर्ज राशि: ") + amount),
        (t("Reported incident date (type of event to confirm)", "बताई गई घटना की तारीख (घटना का प्रकार स्पष्ट करें)"), incident),
        (t("Grievance — user's account", "शिकायत — उपयोगकर्ता के बताए अनुसार"), problem),
        (t("Timeline — user's account", "घटनाक्रम — उपयोगकर्ता के बताए अनुसार"), timeline_text),
        (t("Evidence reported by user; not inspected", "उपयोगकर्ता द्वारा बताए गए साक्ष्य; जाँचे नहीं गए"), reported),
        (t("Previous resolution attempts — user-reported", "पिछले समाधान प्रयास — उपयोगकर्ता के बताए अनुसार"), attempts_text),
        (t("Desired outcome", "इच्छित परिणाम"), resolution),
        (t("Information to review or provide", "समीक्षा या भरने के लिए जानकारी"), "\n".join(f"- {item}" for item in dict.fromkeys(missing))),
    )
    summary = "\n\n".join((
        t("NCH preparation summary", "NCH के लिए तैयारी सारांश"),
        t("Personal preparation only. This is not submitted to NCH and is not officially validated. All case facts are the user's account.",
          "केवल व्यक्तिगत तैयारी। यह NCH को प्रस्तुत नहीं किया गया है और आधिकारिक रूप से सत्यापित नहीं है। सभी केस तथ्य उपयोगकर्ता के बताए अनुसार हैं।"),
        *(f"{heading}:\n{body}" for heading, body in sections),
    ))
    return ActionPackage(complaint, summary, checklist, readiness, case_fingerprint(case), language)
