"""Claim-level validation: citations alone never authorize arbitrary model prose."""

import re
from dataclasses import dataclass

from nyaysaathi.knowledge import KnowledgeEntry, RetrievalContext
from nyaysaathi.models import IntakeResponse


# These fields are intake text, not a channel for legal advice or new citations.
UNSUPPORTED_LEGAL_TEXT = re.compile(
    r"https?://|www\.|§|\b(?:section|rule|article)\s*\d|धारा\s*[\d०-९]|"
    r"\b(?:guaranteed|guarantee|definitely|certainly)\b.*\b(?:refund|win|compensation)\b|"
    r"\b(?:must|shall|legally entitled)\b|गारंटी|निश्चित.*(?:रिफंड|जीत)",
    re.IGNORECASE,
)

NOTICES = {
    "invalid_citation": (
        "I could not verify the proposed legal explanation against the supplied sources. "
        "It has been withheld; no legal conclusion is confirmed.",
        "प्रस्तावित कानूनी व्याख्या दिए गए स्रोतों से सत्यापित नहीं हो सकी। "
        "इसे नहीं दिखाया गया है; किसी कानूनी निष्कर्ष की पुष्टि नहीं हुई है।",
        "Diye gaye sources se proposed explanation verify nahi hui. Use nahi dikhaya gaya; "
        "koi legal conclusion confirm nahi hai.",
    ),
    "insufficient_sources": (
        "The checked sources are insufficient for this question. I cannot confirm a legal answer. "
        "Check the current official guidance or consult a qualified lawyer.",
        "इस प्रश्न के लिए जाँचे गए स्रोत पर्याप्त नहीं हैं। कानूनी उत्तर की पुष्टि नहीं कर सकता। "
        "वर्तमान आधिकारिक मार्गदर्शन देखें या योग्य वकील से सलाह लें।",
        "Is sawal ke liye checked sources kaafi nahi hain. Legal answer confirm nahi kar sakta. "
        "Current official guidance dekhein ya qualified lawyer se salah lein.",
    ),
    "out_of_scope": (
        "This topic is outside consumer refunds, defective products, non-delivery, and related "
        "service complaints. Please consult a qualified professional for this issue.",
        "यह विषय उपभोक्ता रिफंड, खराब उत्पाद, सामान न मिलने और संबंधित सेवा शिकायतों के "
        "दायरे से बाहर है। इस विषय के योग्य विशेषज्ञ से सलाह लें।",
        "Yeh topic consumer refunds, defective products, non-delivery aur related service complaints "
        "ke scope se bahar hai. Is issue ke qualified professional se salah lein.",
    ),
    "urgent_notice": (
        "A notice, hearing, appeal, or deadline may need prompt professional review. Do not rely "
        "on this app to calculate time limits. Keep the document and contact a qualified lawyer promptly.",
        "नोटिस, सुनवाई, अपील या समय सीमा की शीघ्र पेशेवर जाँच आवश्यक हो सकती है। "
        "समय सीमा की गणना के लिए इस ऐप पर भरोसा न करें। दस्तावेज़ सँभालें और जल्द योग्य वकील से संपर्क करें।",
        "Notice, hearing, appeal ya deadline ko jaldi professional review ki zaroorat ho sakti hai. "
        "Time limit calculate karne ke liye app par bharosa na karein. Document rakhein aur qualified lawyer se jaldi baat karein.",
    ),
    "threat_or_crime": (
        "Threats, violence, injury, or criminal allegations need help beyond this consumer-information "
        "app. Prioritize immediate safety and contact appropriate local emergency services if in danger; "
        "seek qualified legal assistance. No criminal-law conclusion is being made.",
        "धमकी, हिंसा, चोट या आपराधिक आरोप इस उपभोक्ता जानकारी ऐप से बाहर की सहायता माँगते हैं। "
        "सुरक्षा को प्राथमिकता दें; खतरा हो तो स्थानीय आपातकालीन सेवाओं से संपर्क करें और योग्य कानूनी सहायता लें। "
        "कोई आपराधिक कानूनी निष्कर्ष नहीं दिया जा रहा है।",
        "Dhamki, violence, injury ya criminal allegations ke liye is consumer app se aage ki madad chahiye. "
        "Safety ko priority dein; khatre mein local emergency services se contact karein aur qualified legal help lein. "
        "Koi criminal-law conclusion nahi diya ja raha.",
    ),
}


def notice(code: str, language: str) -> str:
    return NOTICES[code][{"en": 0, "hi": 1, "hinglish": 2}.get(language, 0)]


@dataclass(frozen=True)
class ValidatedGuidance:
    entries: tuple[KnowledgeEntry, ...] = ()
    language: str = "en"
    status: str = "insufficient_sources"
    message: str = ""


def validate_guidance(result: IntakeResponse, context: RetrievalContext) -> ValidatedGuidance:
    language = result.reply_language
    status = context.safety
    if status not in ("urgent_notice", "threat_or_crime", "out_of_scope") and (
        result.scope == "out_of_scope" or result.safety_flag == "out_of_scope"
    ):
        status = "out_of_scope"
    if status == "none" and result.scope == "unclear":
        status = "insufficient_sources"
    if status == "none":
        status = result.safety_flag
    if status != "none":
        return ValidatedGuidance(language=language, status=status, message=notice(status, language))

    allowed = {entry.source_id: entry for entry in context.entries}
    validated = []
    for item in result.guidance:
        entry = allowed.get(item.source_id)
        # A real ID does NOT prove the model's claim. Only the audited statement
        # in the chosen language is admitted. URLs/actions/limitations come from code/data.
        if entry is None or item.explanation.strip() != entry.guidance[language]:
            return ValidatedGuidance(
                language=language, status="invalid_citation", message=notice("invalid_citation", language),
            )
        if entry not in validated:
            validated.append(entry)
    if not validated:
        return ValidatedGuidance(language=language, message=notice("insufficient_sources", language))
    return ValidatedGuidance(entries=tuple(validated), language=language, status="grounded")
