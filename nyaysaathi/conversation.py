"""Answers that can be given from current case facts without model prose."""

from nyaysaathi.action_package import clean
from nyaysaathi.case_facts import PURCHASE_YEAR_QUESTION, material_questions
from nyaysaathi.consistency import CLARIFY, DATE_MENTION, consistency_question
from nyaysaathi.models import CaseFile


def localized(language: str, en: str, hi: str, hinglish: str) -> str:
    return (en, hi, hinglish)[{"en": 0, "hi": 1, "hinglish": 2}[language]]


INTENTS = {
    "summary": {
        "what happened", "summarize my case", "summarise my case", "show my case summary",
        "क्या हुआ", "मेरे केस का सारांश बताएं", "मेरे मामले का सारांश बताइए",
        "kya hua", "mera case summarize karo", "mere case ka summary batao",
    },
    "draft": {
        "can you prepare the complaint", "can you prepare a complaint", "prepare the complaint", "generate the complaint",
        "क्या आप शिकायत तैयार कर सकते हैं", "शिकायत तैयार करें", "complaint bana do", "kya aap complaint bana sakte hain",
    },
    "next": {
        "what should i do next", "what next", "what should i do", "how should i proceed",
        "अब क्या करूँ", "अब क्या करूं", "अब मुझे क्या करना चाहिए", "ab kya karu", "ab kya karoon", "ab kya karna chahiye",
    },
    "date_edit": {
        "i made a mistake in the date", "i got the date wrong", "the date is wrong", "i mistyped the date",
        "तारीख में गलती हुई", "तारीख गलत है", "maine date galat likhi", "date mein galti ho gayi",
    },
    "yes": {"yes", "yeah", "yep", "haan", "han", "ha", "हाँ", "हां"},
    "no": {"no", "nope", "nahi", "nahin", "नहीं", "नही"},
}


def followup_intent(text: str) -> str | None:
    wording = " ".join(text.casefold().strip(" .!?।？").split())
    return next((intent for intent, forms in INTENTS.items() if wording in forms), None)


def core_details_known(case: CaseFile) -> bool:
    return bool(case.issue_type and case.company_or_seller and case.desired_resolution and
                (case.user_summary or case.product_or_service or case.narrative_review_required))


def next_fact_question(case: CaseFile, language: str) -> str | None:
    if "purchase_date_text" in case.uncertain_fields and case.purchase_date_text:
        return PURCHASE_YEAR_QUESTION[language]
    question = consistency_question(case, language)
    if question:
        return question
    if case.purchase_date_text and not DATE_MENTION.search(case.purchase_date_text):
        return PURCHASE_YEAR_QUESTION[language]
    return None


def document_handoff(language: str) -> str:
    return localized(language,
        "Review the Case File and the Legal Information panel. Open Action Package and generate an editable complaint. "
        "Select the provisional option for missing details, then review the placeholders and add any fresh description before using the draft.",
        "केस फ़ाइल और कानूनी जानकारी देखें। संपादन योग्य शिकायत के लिए Action Package खोलें। "
        "जानकारी अधूरी हो तो अस्थायी मसौदे का विकल्प चुनें, खाली स्थान जाँचें और अपना नया विवरण जोड़ें।",
        "Case File aur Legal Information panel dekhein. Editable complaint ke liye Action Package kholein. "
        "Details missing hon to provisional option chunein, placeholders check karein aur apna fresh description add karein.")


def record_remedy_reply(case: CaseFile, remedy: str, language: str) -> str:
    if case.desired_resolution and case.desired_resolution != remedy:
        case.narrative_review_required = True
    case.desired_resolution = remedy
    case.uncertain_fields.pop("desired_resolution", None)
    question = next_fact_question(case, language)
    case.case_status = "ready_for_review" if not question and core_details_known(case) else "in_progress"
    case.unanswered_questions = list(dict.fromkeys(
        ([question] if question else []) + material_questions(case, language)
    ))
    remedy_hi = {"refund": "रिफंड", "replacement": "बदली", "repair": "मरम्मत", "return": "उत्पाद की वापसी"}[remedy]
    acknowledgment = localized(language, f"I’ve recorded that you’re asking for a {remedy}.",
                               f"मैंने दर्ज किया है कि आप {remedy_hi} चाहते हैं।",
                               f"Maine note kar liya hai ki aapko {remedy} chahiye.")
    return f"{acknowledgment} {question or document_handoff(language)}"


def clarify_remedy(language: str) -> str:
    examples = localized(language, "You can say what you'd like the seller to do, such as replace the item, accept a return, issue a refund, or repair it.",
                         "बताएँ कि विक्रेता क्या करे, जैसे सामान बदले, वापसी स्वीकार करे, पैसे लौटाए या मरम्मत करे।",
                         "Batayein seller kya kare, jaise item replace kare, return accept kare, refund de ya repair kare.")
    return f"{examples} {CLARIFY[language]['desired_resolution']}"


def case_preview(case: CaseFile, language: str) -> str:
    def t(en, hi, hinglish):
        return localized(language, en, hi, hinglish)

    fields = (
        (t("Issue", "समस्या", "Issue"), clean(case.issue_type)),
        (t("Product", "उत्पाद", "Product"), clean(case.product_or_service)),
        (t("Seller or platform", "विक्रेता या प्लेटफ़ॉर्म", "Seller ya platform"), clean(case.company_or_seller)),
        (t("Reported amount", "बताई गई राशि", "Batayi gayi amount"),
         f"₹{case.amount_inr:,f}" if case.amount_inr is not None else None),
        (t("Purchase date", "खरीद की तारीख", "Purchase date"), clean(case.purchase_date_text)),
        (t("Incident date", "घटना की तारीख", "Incident date"), case.incident_date.isoformat() if case.incident_date else None),
        (t("Requested remedy", "चाहा गया समाधान", "Chaha gaya solution"), clean(case.desired_resolution)),
        (t("Reported evidence", "बताए गए साक्ष्य", "Bataya gaya evidence"),
         ", ".join(filter(None, map(clean, case.evidence_available))) or None),
    )
    unknown = t("unknown", "अज्ञात", "abhi maloom nahi")
    lines = [t("Current case facts you reported:", "आपके बताए वर्तमान केस के तथ्य:", "Aapke bataye current case facts:")]
    lines.extend(f"• {label}: {value or unknown}" for label, value in fields)
    if case.narrative_review_required:
        lines.append(t("The earlier description and timeline were cleared after a correction or conflict. "
                       "You can add a fresh account in the draft editor.",
                       "सुधार या विरोधाभास के बाद पुराना विवरण और घटनाक्रम हटाया गया था। मसौदे में नया विवरण जोड़ सकते हैं।",
                       "Correction ya conflict ke baad purana description aur timeline hata di gayi thi. Draft editor mein fresh details add karein."))
    return "\n".join(lines)


def local_reply(case: CaseFile, intent: str, prior: str, language: str) -> str:
    question = next_fact_question(case, language)
    if intent == "summary":
        return case_preview(case, language)
    if intent == "draft":
        if case.issue_type or case.user_summary:
            return document_handoff(language)
        return CLARIFY[language]["issue_type"]
    if intent == "date_edit":
        if case.purchase_date_text and case.incident_date is None:
            case.purchase_date_text = None
            case.uncertain_fields["purchase_date_text"] = "withdrawn"
            case.narrative_review_required = True
            case.case_status = "in_progress"
            case.unanswered_questions = [CLARIFY[language]["purchase_date_text"]]
            return case.unanswered_questions[0]
        return localized(language, "Which date should I correct, the purchase date or the incident date?",
                         "कौन-सी तारीख सुधारनी है, खरीद की या घटना की?",
                         "Kaunsi date correct karni hai, purchase date ya incident date?")
    # A short reply can answer the app's earlier offer to correct a detail.
    if "do you want to correct" in prior.casefold() and intent == "yes":
        return localized(language, "Which case detail would you like to correct?",
                         "केस का कौन-सा विवरण सुधारना चाहते हैं?", "Case ki kaunsi detail correct karni hai?")
    if intent == "no" and core_details_known(case) and not case.uncertain_fields:
        return document_handoff(language)
    if question and case.case_status != "not_started":
        return localized(language, "Please confirm the specific detail so I can update the case.",
                         "केस बदलने के लिए कृपया सही विवरण बताएं।", "Case update karne ke liye specific detail batayein.") + " " + question
    return localized(language, "Tell me the specific fact you want to change, ask for a case summary, or open Action Package to prepare a draft.",
                     "जिस तथ्य को बदलना है उसे बताएं, केस का सारांश माँगें या मसौदे के लिए Action Package खोलें।",
                     "Jo fact change karna hai woh batayein, case summary maangein, ya draft ke liye Action Package kholein.")
