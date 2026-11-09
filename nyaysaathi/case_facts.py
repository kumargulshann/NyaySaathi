"""Conservative checks for facts whose meaning matters in complaint drafts."""

import re

from nyaysaathi.consistency import CLARIFY, DATE_MENTION, MONTH, possible_stale_assertion
from nyaysaathi.models import CaseFile


GENERIC_SELLERS = frozenset({
    "seller", "vendor", "retailer", "company", "platform", "marketplace", "unknown",
    "online seller", "online vendor", "online retailer", "online store", "online shop",
    "online platform", "online marketplace", "e-commerce seller", "e-commerce platform",
    "e-commerce website", "ecommerce seller", "website", "विक्रेता", "ऑनलाइन विक्रेता",
    "ऑनलाइन दुकान", "ऑनलाइन प्लेटफॉर्म", "company ka naam nahi pata",
})


def named_seller(value: str, quote: str) -> bool:
    name = value.strip()
    descriptor = re.sub(r"^(?:a|an|the)\s+", "", " ".join(name.casefold().split()))
    return bool(name and descriptor.rstrip(".") not in GENERIC_SELLERS and
                re.search(rf"(?<!\w){re.escape(name)}(?!\w)", quote, re.IGNORECASE))


# Accept positive first-person requests in a user clause, in any of the three
# supported chat languages. A seller's actions or a past request do not match.
REMEDY_REQUEST = re.compile(
    r"^(?:now\s+)?I\s+(?:now\s+)?(?:want|would like|am asking for|request|prefer)\s+"
    r"(?:to\s+(?:get|receive)\s+)?(?P<en>.+)$|"
    r"^(?:ab\s+)?(?:mujhe|mujhko)\s+(?P<hinglish>.+?)\s+chahiye$|"
    r"^(?:अब\s+)?मुझे\s+(?P<hi>.+?)\s+चाहिए$",
    re.IGNORECASE,
)
REMEDIES = {
    "refund": r"refund|my money back|money back|paise\s+(?:wapas|vapas)|रिफंड|धनवापसी|(?:(?:मेरे|अपने)\s+)?पैसे वापस",
    "replacement": r"replacement|new one|replacement product|रिप्लेसमेंट|बदली|नया उत्पाद",
    "repair": r"repair|मरम्मत",
}
REMEDY_SHIFT = re.compile(r"\b(?:now|instead|correction|actually|ab)\b|अब|इसके बजाय", re.IGNORECASE)


def _remedy_key(text: str) -> str:
    text = re.sub(r"^(?:a|an|the)\s+", "", text.casefold().strip(" .!।"))
    text = re.sub(r",?\s+please$", "", text)
    return next((key for key, variants in REMEDIES.items() if re.fullmatch(variants, text)), text)


def requested_remedy(value: str, quote: str, latest: str, *, answering_remedy_question: bool = False) -> bool:
    # Match a complete clause in the latest user turn. This prevents a quote
    # such as "replacement" from borrowing meaning from a seller's refusal.
    clauses = re.split(r"(?<=[.!?।])\s+|[;\n]+|,?\s+(?:but\s+(?=now\b)|lekin\s+(?=ab\b)|लेकिन\s+(?=अब))",
                       latest, flags=re.IGNORECASE)
    requested = []
    for clause in clauses:
        clause = clause.strip()
        if clause.endswith(("?", "？")):
            continue
        statement = clause.rstrip(".!।")
        match = REMEDY_REQUEST.fullmatch(statement)
        if match:
            target = next(item for item in match.groups() if item is not None)
            # Questions, negatives, alternatives, and discussion of a request
            # are not a confirmed outcome. The requested text must be explicit.
            if re.search(r"^to\s|\b(?:not|no|or|whether|why|if|nahi|nahin|ya|complaint|options|advice|guidance)\b|"
                         r"नहीं|या\s|शिकायत|जानकारी", target, re.IGNORECASE):
                continue
            requested.append((target, statement))
        elif answering_remedy_question and len(clauses) == 1 and _remedy_key(statement) in REMEDIES:
            requested.append((statement, statement))
    if not requested:
        return False
    if len({_remedy_key(target) for target, _ in requested}) > 1 and not REMEDY_SHIFT.search(latest):
        return False
    target, statement = requested[-1]
    # A remedy keyword alone could have been copied from a refusal elsewhere
    # in the message. Require the quote to cover the actual request.
    return _remedy_key(value) == _remedy_key(target) and statement in quote


PURCHASE = re.compile(
    r"^I\s+(?:ordered|bought|purchased)\s+(?:an?\s+|the\s+|my\s+)?"
    r"(?P<product>[^.!?;\n]{1,100}?)(?=\s+(?:worth|from|online|on|for)\b|[.!]|$)",
    re.IGNORECASE,
)
DAY = r"(?:0?[1-9]|[12][0-9]|3[01])"
PURCHASE_DATE = re.compile(rf"\bon\s+((?:{MONTH}\s+{DAY}|{DAY}\s+{MONTH})(?:,?\s+\d{{4}})?)(?!\w)", re.IGNORECASE)


def record_purchase_details(case: CaseFile, latest: str, prior_question: str = "") -> None:
    """Keep literal details from an unambiguous purchase statement."""
    if case.narrative_review_required:
        return
    if case.purchase_date_text and not DATE_MENTION.search(case.purchase_date_text):
        year = re.fullmatch(r"(?:in\s+)?(\d{4})[.!।]?", latest.strip(), re.IGNORECASE)
        if year and any(prior_question.endswith(question) for question in PURCHASE_YEAR_QUESTION.values()):
            separator = " " if case.purchase_date_text[0].isdigit() else ", "
            case.purchase_date_text += separator + year[1]
    statements = re.split(r"(?<=[.!?।])\s+|\n+", latest)
    purchases = [(sentence, match) for sentence in statements if (match := PURCHASE.match(sentence))]
    if len(purchases) != 1:
        return
    sentence, match = purchases[0]
    if sentence.endswith(("?", "？")):
        return
    product = match["product"].strip()
    if (len(product) < 2 or re.search(r"^(?:from|online|on|for)\b|\b(?:or|and|something|item|product|thing|it)\b|\[|\]",
                                     product, re.IGNORECASE)
            or (case.product_or_service and case.product_or_service.casefold() != product.casefold())):
        return
    case.product_or_service = product
    purchase_date = PURCHASE_DATE.search(sentence)
    if purchase_date and not case.purchase_date_text:
        case.purchase_date_text = purchase_date[1]
    # Preserve the channel and incomplete date in the user's own words.
    if re.search(r"\bonline\b", sentence, re.IGNORECASE) or case.purchase_date_text:
        if not possible_stale_assertion(case, sentence) and sentence not in case.timeline:
            case.timeline.insert(0, sentence)


PURCHASE_YEAR_QUESTION = {
    "en": "What year did you place the order?",
    "hi": "आपने किस साल ऑर्डर दिया था?",
    "hinglish": "Aapne kis saal order diya tha?",
}


def material_questions(case: CaseFile, language: str) -> list[str]:
    if not any((case.issue_type, case.user_summary, case.product_or_service, case.timeline)):
        return []
    questions = [CLARIFY[language][field] for field in ("company_or_seller", "desired_resolution")
                 if getattr(case, field) is None]
    if case.purchase_date_text and not DATE_MENTION.search(case.purchase_date_text):
        questions.append(PURCHASE_YEAR_QUESTION[language])
    elif case.incident_date is None and not case.purchase_date_text:
        questions.append(CLARIFY[language]["incident_date"])
    return questions
