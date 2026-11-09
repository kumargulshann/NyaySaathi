"""Conservative checks for facts whose meaning matters in complaint drafts."""

import re
from datetime import date

from nyaysaathi.consistency import AMBIGUITY, CLARIFY, DATE_MENTION, PURCHASE_DATE_VALUE, possible_stale_assertion
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
PURCHASE_DATE = re.compile(rf"\bon\s+({PURCHASE_DATE_VALUE.pattern})(?!\w)", re.IGNORECASE)
PURCHASE_CONTEXT = re.compile(r"\b(?:order(?:ed|ing)?|bought|purchas(?:e|ed)|kharid[ai]?)\b|ऑर्डर|खरीद", re.IGNORECASE)
INCIDENT_CONTEXT = re.compile(
    r"\b(?:arrived|received|deliver(?:ed|y)|refused|denied|emailed|contacted|reported|damaged|complained|incident date)\b|"
    r"डिलीवरी|पहुंचा|पहुँचा|मिला|मिली|मना किया|शिकायत की|\bmila\b|\bpahuncha\b", re.IGNORECASE,
)
DATE_CORRECTION = re.compile(
    r"\b(?:mistyped|mistake|correction|wrong|actually|meant|confirm|galti|galat|asal mein|sahi)\b|"
    r"गलती|गलत|सही|असल में|दरअसल|सुधार", re.IGNORECASE,
)
YEAR = re.compile(r"(?<!\d)\d{4}(?!\d)")
ORDER_YEAR = re.compile(
    r"\b(?:in|year(?:\s+(?:was|is))?)\s+\d{4}(?!\d)|(?<!\d)\d{4}\s*(?:mein\b|me\b|में)|"
    r"(?:साल|वर्ष)\s*\d{4}(?!\d)", re.IGNORECASE,
)


MONTH_NUMBER = {
    name: index for index, names in enumerate((
        "jan january जनवरी", "feb february फरवरी", "mar march मार्च", "apr april अप्रैल", "may मई", "jun june जून",
        "jul july जुलाई", "aug august अगस्त", "sep sept september सितंबर", "oct october अक्टूबर",
        "nov november नवंबर", "dec december दिसंबर",
    ), 1) for name in names.split()
}


def _reported_date(day_month: str, year: int) -> date:
    a, b = day_month.casefold().split()
    day, month = (a, b) if a.isdigit() else (b, a)
    return date(year, MONTH_NUMBER[month], int(day))


def _supports_event_date(text: str, value: str) -> bool:
    if re.search(rf"(?<!\d){re.escape(value)}(?!\d)", text):
        return True
    for match in PURCHASE_DATE_VALUE.finditer(text):
        if match["year"]:
            try:
                if _reported_date(match["day_month"], int(match["year"])).isoformat() == value:
                    return True
            except ValueError:
                continue
    return False


def is_purchase_date_proposal(case: CaseFile, quote: str, value: str | None, user_texts: list[str], prior_question: str) -> bool:
    """Do not let an order date be assigned to an incident by the model."""
    if prior_question in (*PURCHASE_YEAR_QUESTION.values(), *(q["purchase_date_text"] for q in CLARIFY.values())):
        if YEAR.fullmatch(quote.strip(" .!।")):
            return True
    spans = [sentence for text in user_texts if quote in text
             for sentence in re.split(r"(?<=[.!?।])\s+|\n+", text)
             if quote in sentence or (sentence and sentence in quote)]
    # An explicitly reported incident can have its own date, even in a case
    # with an order date. Use the event-bearing quote, not a nearby year.
    asked_incident = prior_question in (questions["incident_date"] for questions in CLARIFY.values())
    if any((INCIDENT_CONTEXT.search(sentence) or asked_incident) and not PURCHASE_CONTEXT.search(sentence) and
           (value is None or _supports_event_date(sentence, value)) for sentence in spans):
        return False
    if any(PURCHASE_CONTEXT.search(sentence) and (PURCHASE_DATE.search(sentence) or ORDER_YEAR.search(sentence))
           for sentence in spans):
        return True
    return bool(case.purchase_date_text or "purchase_date_text" in case.uncertain_fields)


def record_purchase_details(case: CaseFile, latest: str) -> None:
    """Keep literal details from an unambiguous purchase statement."""
    if case.narrative_review_required:
        return
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


def record_purchase_date_reply(case: CaseFile, latest: str, prior_question: str) -> bool:
    """Apply a user-confirmed purchase year or explicit correction; never an incident date."""
    current = PURCHASE_DATE_VALUE.fullmatch(case.purchase_date_text or "")
    asked_year = prior_question in PURCHASE_YEAR_QUESTION.values()
    asked_date = prior_question in (entry["purchase_date_text"] for entry in CLARIFY.values())
    order_spans = [part for part in re.split(r"[.!?।;\n]+", latest)
                   if PURCHASE_CONTEXT.search(part) and not INCIDENT_CONTEXT.search(part)]
    explicit = bool(DATE_CORRECTION.search(latest))
    clean_reply = latest.strip().rstrip(".!।")
    full_answer = PURCHASE_DATE_VALUE.fullmatch(clean_reply) if asked_date else None
    linked_dates = [match for part in order_spans if (start := PURCHASE_DATE.search(part))
                    for match in PURCHASE_DATE_VALUE.finditer(part, start.start(1))]
    new_date = full_answer or (linked_dates[0] if linked_dates else None)
    # Anchor a standalone year to the server's preceding year question or to a
    # current statement about the order. Unrelated amounts are not years.
    bare_years = re.fullmatch(r"(?:in\s+)?\d{4}(?:\s*(?:or|ya|या|/)\s*\d{4})?", clean_reply, re.IGNORECASE)
    linked_years = [(part, match) for part in order_spans for match in ORDER_YEAR.finditer(part)]
    if not new_date and not (current and ((asked_year and bare_years) or linked_years)):
        if current and order_spans and AMBIGUITY.search(latest):
            if re.search(r"\b(?:year|saal)\b|साल|वर्ष", latest, re.IGNORECASE):
                case.purchase_date_text = current["day_month"]
            else:
                case.purchase_date_text = None
            case.uncertain_fields["purchase_date_text"] = "conflicting"
            case.narrative_review_required = True
            return True
        return False
    if not current and not asked_date and not case.purchase_date_text:
        return False  # The initial purchase extractor handles new order dates.

    years = {int(value) for value in YEAR.findall(clean_reply)} if asked_year and bare_years else set()
    if new_date and new_date["year"]:
        years.add(int(new_date["year"]))
    years.update(int(match["year"]) for match in linked_dates if match["year"])
    for part, match in linked_years:
        years.update(map(int, YEAR.findall(match[0])))
        alternative = re.match(r"\s*(?:or|ya|या|/)\s*(\d{4})(?!\d)", part[match.end():], re.IGNORECASE)
        if alternative:
            years.add(int(alternative[1]))
    old_year = int(current["year"]) if current and current["year"] else None
    day_month = new_date["day_month"] if new_date else current["day_month"]
    old_day_month = current["day_month"] if current else None
    distinct_days = {match["day_month"].casefold() for match in linked_dates}
    ambiguous = len(years) > 1 or len(distinct_days) > 1 or bool(AMBIGUITY.search(latest))
    different_day = len(distinct_days) > 1 or bool(old_day_month and day_month.casefold() != old_day_month.casefold())
    confirmed = explicit or asked_date or asked_year
    year = next(iter(years)) if len(years) == 1 else None
    if year is None and not ambiguous and not different_day and old_year is not None:
        return False  # Repeating only the day/month is not a year withdrawal.
    if ambiguous or (not confirmed and (different_day or (old_year is not None and year != old_year))):
        case.purchase_date_text = None if different_day else old_day_month
        case.uncertain_fields["purchase_date_text"] = "conflicting"
        case.narrative_review_required = True
        return True
    if "purchase_date_text" in case.uncertain_fields and not confirmed:
        return False
    if year is None and not new_date:
        return False
    try:
        _reported_date(day_month, year if year is not None else 2000)
    except ValueError:
        return False
    separator = " " if day_month[0].isdigit() else ", "
    updated = day_month + (separator + str(year) if year is not None else "")
    if updated == case.purchase_date_text:
        return False
    if old_year is not None or different_day:
        case.narrative_review_required = True
    case.purchase_date_text = updated
    case.uncertain_fields.pop("purchase_date_text", None)
    return True


def material_questions(case: CaseFile, language: str) -> list[str]:
    if not any((case.issue_type, case.user_summary, case.product_or_service, case.timeline)):
        return []
    questions = [CLARIFY[language][field] for field in ("company_or_seller", "desired_resolution")
                 if getattr(case, field) is None]
    if case.purchase_date_text and not DATE_MENTION.search(case.purchase_date_text):
        questions.append(PURCHASE_YEAR_QUESTION[language])
    elif "purchase_date_text" in case.uncertain_fields:
        questions.append(CLARIFY[language]["purchase_date_text"])
    elif case.incident_date is None and not case.purchase_date_text:
        questions.append(CLARIFY[language]["incident_date"])
    return questions
