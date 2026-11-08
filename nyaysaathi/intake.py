"""Transactional case intake, independent of the UI and model vendor."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from nyaysaathi.models import CaseFile, IntakeResponse
from nyaysaathi.guidance import UNSUPPORTED_LEGAL_TEXT, ValidatedGuidance, notice, validate_guidance
from nyaysaathi.knowledge import RetrievalContext, retrieve
from nyaysaathi.consistency import SCALAR_FACTS, consistency_question, protect_narratives, unresolved_fields


class IntakeError(Exception):
    """Only a safe error code crosses the provider/UI boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ModelProvider(Protocol):
    def analyze(
        self, case: CaseFile, messages: list[dict[str, str]], language: str,
        context: RetrievalContext | None = None,
    ) -> str: ...


SCOPE_MESSAGES = {
    "en": "I can only collect details about consumer refunds, defective products, "
          "non-delivery, and related service complaints in India. This topic is outside that scope.",
    "hi": "मैं केवल भारत में उपभोक्ता रिफंड, खराब उत्पाद, सामान न मिलने और संबंधित "
          "सेवाओं की शिकायतों का विवरण जुटा सकता हूँ। यह विषय इस दायरे से बाहर है।",
    "hinglish": "Main sirf India mein consumer refunds, defective products, non-delivery "
                "aur related service complaints ki details le sakta hoon. Yeh topic is scope se bahar hai.",
}


COMPLETION_MESSAGES = {
    "en": "Review your Case File and the checked legal information below. Then generate an Action Package; "
          "select the provisional option if details are missing. Review and complete the draft before using it.",
    "hi": "अपनी केस फ़ाइल और नीचे जाँची गई कानूनी जानकारी देखें। फिर Action Package बनाएँ; "
          "विवरण अधूरे हों तो अस्थायी मसौदे का विकल्प चुनें। उपयोग से पहले मसौदा जाँचें और पूरा करें।",
    "hinglish": "Apni Case File aur neeche checked legal information review karein. Phir Action Package banayein; "
                "details missing hon to provisional option chunein. Use karne se pehle draft review aur complete karein.",
}


def run_intake(
    case: CaseFile,
    messages: list[dict[str, str]],
    language: str,
    provider: ModelProvider,
) -> tuple[CaseFile, str]:
    """Make one call, validate a fresh candidate, then return it for UI commit.

    Failures cannot mutate the original case, including nested lists.
    """
    _require_user_turn(messages)
    response = provider.analyze(case.model_copy(deep=True), messages, language)
    try:
        result = IntakeResponse.model_validate_json(response)
        return _apply_intake(case, messages, result)
    except (ValidationError, ValueError, TypeError):
        raise IntakeError("invalid_output") from None


def _require_user_turn(messages: list[dict[str, str]]) -> None:
    if not messages or messages[-1]["role"] != "user":
        raise IntakeError("invalid_output")


def _apply_intake(
    case: CaseFile, messages: list[dict[str, str]], result: IntakeResponse,
) -> tuple[CaseFile, str]:
    try:
        if result.scope == "out_of_scope":
            return case.model_copy(deep=True), SCOPE_MESSAGES[result.reply_language]
        if result.scope == "unclear":
            return case.model_copy(deep=True), result.next_question.strip()

        candidate = protect_narratives(case).model_dump()
        user_texts = [message["content"] for message in messages if message["role"] == "user"]
        seen = set()
        # Validate the full proposal before changing anything. Pre-marking accepted
        # correction turns makes invalidation independent of model change ordering.
        for change in result.changes:
            if change.field in seen:
                raise ValueError("Conflicting field changes")
            seen.add(change.field)
            if not change.source_quote.strip() or not any(
                change.source_quote in content for content in user_texts
            ):
                raise ValueError("Fact changes require a verbatim user quote")
            if change.is_correction and change.source_quote not in messages[-1]["content"]:
                raise ValueError("Corrections must come from the current user turn")
        if any(change.is_correction and change.field != "user_language" for change in result.changes):
            candidate["narrative_review_required"] = True
        unresolved = unresolved_fields(messages[-1]["content"])
        for field in sorted(unresolved):
            candidate[field] = None
            candidate["uncertain_fields"][field] = "conflicting"
            candidate["narrative_review_required"] = True

        for change in result.changes:
            if candidate["narrative_review_required"] and change.field in ("user_summary", "timeline"):
                continue  # Never restore unproven derived prose from older messages.

            previous = candidate[change.field]
            value = change.value
            if isinstance(previous, list):
                if value is None and change.is_correction:
                    value = []
                if not isinstance(value, list):
                    raise ValueError("List fields require lists")
                if not change.is_correction:
                    value = list(dict.fromkeys(previous + value))
            proposed = {**candidate, change.field: value}
            normalized = CaseFile.model_validate(proposed).model_dump()
            uncertain = candidate["uncertain_fields"]
            if change.field in SCALAR_FACTS:
                if change.field in unresolved and value is not None:
                    # Even a mistaken model correction marker cannot pick a value
                    # while the current user explicitly says it is unresolved.
                    normalized[change.field] = None
                elif change.is_correction:
                    candidate["narrative_review_required"] = True
                    if value is None:
                        uncertain[change.field] = "withdrawn"
                    else:
                        uncertain.pop(change.field, None)
                elif change.field in uncertain:
                    normalized[change.field] = None
                elif previous is not None and normalized[change.field] != previous:
                    if change.source_quote not in messages[-1]["content"]:
                        raise ValueError("An apparent conflict must be supported by the current user turn")
                    # A new conflicting value is not automatically a correction.
                    # Confirm neither alternative until the user resolves it.
                    normalized[change.field] = None
                    uncertain[change.field] = "conflicting"
                    candidate["narrative_review_required"] = True
            if (
                not isinstance(previous, list)
                and previous is not None
                and normalized[change.field] != previous
                and not change.is_correction
                and change.field not in SCALAR_FACTS
            ):
                raise ValueError("Existing facts require an explicit correction")
            normalized["narrative_review_required"] = candidate["narrative_review_required"]
            normalized["uncertain_fields"] = uncertain
            candidate = normalized

        question = (result.next_question or "").strip()
        candidate.update(
            evidence_missing=result.evidence_missing,
            unanswered_questions=list(dict.fromkeys(([question] if question else []) + result.missing_details)),
            confidence_or_uncertainty=result.uncertainty,
            case_status=result.case_status,
        )
        # Readiness is intake review only, never legal verification or an outcome.
        if candidate["case_status"] == "ready_for_review" and not all(
            candidate[name] is not None and candidate[name] != ""
            for name in ("issue_type", "user_summary", "company_or_seller", "desired_resolution")
        ):
            candidate["case_status"] = "in_progress"
        updated = protect_narratives(CaseFile.model_validate(candidate))
        if updated.narrative_review_required:
            question = consistency_question(updated, result.reply_language)
            updated.unanswered_questions = [question]
        if not question:
            if updated.case_status != "ready_for_review":
                raise ValueError("Incomplete intake still needs a relevant question")
            question = COMPLETION_MESSAGES[result.reply_language]
        return updated, question
    except (ValidationError, ValueError, TypeError):
        raise IntakeError("invalid_output") from None


@dataclass(frozen=True)
class TurnResult:
    case: CaseFile
    reply: str
    guidance: ValidatedGuidance
    intake_error: str | None = None


def run_turn(
    case: CaseFile, messages: list[dict[str, str]], language: str, provider: ModelProvider,
) -> TurnResult:
    """Retrieve once, make one request, and keep legal validation separate from facts."""
    _require_user_turn(messages)
    context = retrieve(messages[-1]["content"], case)
    response = provider.analyze(case.model_copy(deep=True), messages, language, context)
    try:
        result = IntakeResponse.model_validate_json(response)
    except (ValidationError, ValueError, TypeError):
        raise IntakeError("invalid_output") from None

    # Generated intake fields cannot become an alternative channel for legal
    # assertions, made-up sections, URLs, or guaranteed outcomes.
    intake_text = " ".join(filter(None, [
        result.next_question, result.uncertainty, *result.evidence_missing, *result.missing_details,
    ]))
    for change in result.changes:
        values = change.value if isinstance(change.value, list) else [change.value]
        intake_text += " " + " ".join(
            value for value in values
            if isinstance(value, str) and value not in change.source_quote
        )
    if UNSUPPORTED_LEGAL_TEXT.search(intake_text):
        message = notice("invalid_citation", result.reply_language)
        return TurnResult(case.model_copy(deep=True), message, ValidatedGuidance(
            language=result.reply_language, status="invalid_citation", message=message,
        ))

    intake_error = None
    try:
        updated, reply = _apply_intake(case, messages, result)
    except IntakeError:
        # Source-checked general information does not require accepting an
        # ungrounded fact update. Preserve the ENTIRE case; report the failure.
        updated = case.model_copy(deep=True)
        reply = result.next_question.strip() if result.next_question else ""
        intake_error = "invalid_output"
    guidance = validate_guidance(result, context)
    if guidance.status in ("urgent_notice", "threat_or_crime", "out_of_scope"):
        # Keep critical warnings visible in chat as well as the options panel.
        reply = guidance.message
        updated = case.model_copy(deep=True)
    return TurnResult(updated, reply, guidance, intake_error)
