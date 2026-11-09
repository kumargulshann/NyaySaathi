"""Transactional case intake, independent of the UI and model vendor."""

from dataclasses import dataclass
from decimal import Decimal
import logging
import re
from typing import Protocol

from pydantic import ValidationError

from nyaysaathi.case_facts import (
    PURCHASE_CONTEXT, PURCHASE_YEAR_QUESTION, REMEDY_SHIFT, direct_remedy_answer, is_purchase_date_proposal,
    material_questions, named_seller, record_purchase_date_reply, record_purchase_details, requested_remedy,
)
from nyaysaathi.conversation import (
    clarify_remedy, core_details_known, document_handoff, followup_intent, local_reply, localized,
    next_fact_question, record_remedy_reply,
)
from nyaysaathi.models import CaseFile, FactChange, IntakeResponse
from nyaysaathi.guidance import UNSUPPORTED_LEGAL_TEXT, ValidatedGuidance, notice, validate_guidance
from nyaysaathi.knowledge import RetrievalContext, detect_safety, retrieve
from nyaysaathi.consistency import CLARIFY, MONEY, SCALAR_FACTS, possible_stale_assertion, protect_narratives, unresolved_fields


logger = logging.getLogger(__name__)


def _diagnostic(stage: str, rule: str, field: str = "-") -> None:
    # Vercel associates this line with the request. Never log exception text,
    # rejected values, or free-form schema keys from the model.
    logger.warning("intake_validation stage=%s rule=%s field=%s", stage, rule, field)


class IntakeError(Exception):
    """Only a safe error code crosses the provider/UI boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _invalid(stage: str, rule: str, field: str = "-") -> IntakeError:
    _diagnostic(stage, rule, field)
    return IntakeError("invalid_output")


def _parse_response(response: str) -> IntakeResponse:
    try:
        return IntakeResponse.model_validate_json(response)
    except ValidationError as error:
        for item in error.errors(include_input=False, include_context=False, include_url=False):
            location = item["loc"]
            root = location[0] if location and location[0] in IntakeResponse.model_fields else "-"
            rule = {
                "json_invalid": "malformed_json",
                "json_type": "invalid_json_type",
                "missing_intake_question": "missing_question",
                "multiple_intake_questions": "multiple_questions",
            }.get(item["type"], "schema_mismatch")
            if root == "changes" and location[-1] == "source_quote" and item["type"] == "string_too_short":
                rule = "empty_source_quote"
            _diagnostic("response_schema", rule, root)
        raise IntakeError("invalid_output") from None


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


PARTIAL_MESSAGES = {
    "en": "I saved the details I could check against your message. Some details still need review.",
    "hi": "आपके संदेश से मिलान हुए विवरण दर्ज किए हैं। कुछ विवरणों की जाँच बाकी है।",
    "hinglish": "Aapke message se match hui details save ki hain. Kuch details abhi review karni hain.",
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
    return _apply_intake(case, messages, _parse_response(response))


def _require_user_turn(messages: list[dict[str, str]]) -> None:
    if not messages or messages[-1]["role"] != "user":
        raise _invalid("input", "missing_user_turn")


def _change_rule(change: FactChange, user_texts: list[str], unresolved: set[str]) -> str | None:
    quote = change.source_quote
    if not quote.strip() or not any(quote in content for content in user_texts):
        return "nonverbatim_quote"
    if change.is_correction and quote not in user_texts[-1]:
        return "correction_requires_current_quote"
    if change.value is None and not change.is_correction:
        return "null_without_retraction"

    value = change.value
    if value is None and change.field in ("timeline", "evidence_available"):
        value = []  # Explicit list retraction.
    try:
        normalized = CaseFile.model_validate({change.field: value})
    except ValidationError:
        return "invalid_date" if change.field == "incident_date" else "invalid_field_value"
    if change.field == "incident_date" and value is not None and change.field not in unresolved:
        if value != normalized.incident_date.isoformat():
            return "invalid_date"
        # A full year must appear in this field's own evidence. The current
        # calendar year, the assistant, or another fact cannot supply it.
        if not any(int(year) == normalized.incident_date.year for year in re.findall(r"(?<!\d)\d{4}(?!\d)", quote)):
            return "unquoted_date_year"
    return None


def _rupee_value(text: str) -> Decimal | None:
    # Accept a single decimal, optionally with a currency marker and Indian
    # or western comma grouping. Do not strip arbitrary non-numeric text.
    match = re.fullmatch(
        r"(?:₹|Rs\.?|INR)?\s*([0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|"
        r"[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3})(\.[0-9]+)?\s*",
        text, re.IGNORECASE,
    )
    if match:
        return Decimal(match[1].replace(",", "") + (match[2] or ""))
    return None


def _independent_value(change: FactChange, latest: str) -> Decimal | list[str] | None:
    """Recover a quoted price or an affirmative evidence list.

    Never copy model prose, conclusions, date/seller/remedy guesses, or metadata
    from a mixed response. Check provenance even for malformed proposals.
    """
    if not change.source_quote.strip() or change.source_quote not in latest:
        return None
    if change.field == "amount_inr" and isinstance(change.value, str):
        # Price must be in a positive purchase/payment statement in the latest
        # message, not merely a number mentioned by the user or assistant.
        prices = list(re.finditer(
            rf"(?:^|[.!?]\s+)I (?:paid\s+|(?:ordered|bought) [^.!?\n]+? worth\s+)"
            rf"(?P<price>{MONEY.pattern})(?![\d,]|\.\d)(?=\s+(?:from|for|on|to)\b|\s*(?:[.;!?]|$))",
            latest, re.IGNORECASE,
        ))
        if len(prices) == 1 and prices[0]["price"] in change.source_quote:
            amount = _rupee_value(prices[0]["price"])
            if amount is not None and amount == _rupee_value(change.value):
                return amount
    if change.field == "evidence_available" and change.value:
        # Restrict recovery to a simple, explicit inventory in a single clause.
        # Unknown phrasings remain eligible on ordinary, fully valid turns.
        clause = re.fullmatch(r"I have (?:the )?([^.;!?\n]+)[.]?", change.source_quote, re.IGNORECASE)
        if clause and change.source_quote.rstrip(".") in re.split(r"[.!?]\s+", latest.rstrip(".?!")):
            items = re.split(r",\s*(?:and\s+)?|\s+and\s+", clause[1])
            if items == change.value and all(item.casefold() in {
                "invoice", "receipt", "photographs", "photos", "customer support emails",
                "order confirmation", "payment proof", "delivery receipt",
            } for item in items):
                return change.value
    return None


def _quoted_statements(case: CaseFile, changes: list[FactChange], latest: str, field: str = "timeline") -> list[str]:
    # Recover complete user statements in the original order. Discard the
    # model's malformed values, paraphrases, and stitched or partial quotes.
    quotes = {change.source_quote for change in changes if change.field == field and change.value}
    events = []
    for sentence in re.split(r"(?<=[.!?।])\s+|\n+", latest):
        if (sentence in quotes or sentence.rstrip(".।") in quotes) and not (
            not sentence.strip() or "?" in sentence or "？" in sentence or
            UNSUPPORTED_LEGAL_TEXT.search(sentence) or possible_stale_assertion(case, sentence)
        ):
            events.append(sentence)
    return list(dict.fromkeys(events))


def _recover_intake(
    case: CaseFile, result: IntakeResponse, latest: str, unresolved: set[str],
    failed: list[FactChange],
) -> tuple[CaseFile, str]:
    # Corrections, contradictions, and writes to existing facts can affect
    # other fields. Keep them transactional even if new facts look safe.
    if unresolved or case.uncertain_fields or case.narrative_review_required or any(
        change.is_correction or getattr(case, change.field) not in (None, [])
        for change in result.changes
    ):
        raise _invalid("recovery", "inseparable_proposal")
    fields = {}
    for change in result.changes:
        value = _independent_value(change, latest)
        if value is not None:
            fields[change.field] = value
    updated = CaseFile.model_validate({**case.model_dump(), **fields, "case_status": "in_progress"})
    failed_fields = {change.field for change in failed}
    events = (_quoted_statements(updated, result.changes, latest)
              if "timeline" in failed_fields and "incident_date" not in failed_fields else [])
    if not fields and not events:
        raise _invalid("recovery", "no_independent_facts")
    if events:
        updated.timeline = events
    language = result.reply_language
    record_purchase_details(updated, latest)
    # Ask about a rejected structured detail if it remains unknown. For a
    # rejected narrative or a repaired price, prioritize a missing core fact.
    question = next((CLARIFY[language][change.field] for change in failed
                     if change.field in CLARIFY[language] and getattr(updated, change.field) is None), None)
    if not question:
        question = (CLARIFY[language]["company_or_seller"] if updated.company_or_seller is None
                    else next_fact_question(updated, language) or CLARIFY[language]["incident_date"])
    updated.unanswered_questions = list(dict.fromkeys([question, *material_questions(updated, language)]))
    # Old suggestions may no longer be missing after accepting evidence.
    if "evidence_available" in fields:
        updated.evidence_missing = []
    updated.confidence_or_uncertainty = PARTIAL_MESSAGES[language]
    _diagnostic("recovery", "partial_acceptance", failed[0].field)
    return updated, f"{PARTIAL_MESSAGES[language]} {question}"


def _pending_question(case: CaseFile, messages: list[dict[str, str]]) -> str:
    prior = next((item["content"] for item in reversed(messages[:-1]) if item["role"] == "assistant"), "")
    if case.unanswered_questions and prior.endswith(case.unanswered_questions[0]):
        return case.unanswered_questions[0]
    return ""


def _remedy_question_language(question: str) -> str | None:
    return next((lang for lang, questions in CLARIFY.items() if question == questions["desired_resolution"]), None)


def _apply_intake(
    case: CaseFile, messages: list[dict[str, str]], result: IntakeResponse, *, recover: bool = False,
) -> tuple[CaseFile, str]:
    try:
        if result.scope == "out_of_scope":
            return case.model_copy(deep=True), SCOPE_MESSAGES[result.reply_language]
        protected = protect_narratives(case)
        user_texts = [message["content"] for message in messages if message["role"] == "user"]
        unresolved = unresolved_fields(user_texts[-1])
        seen, failed, accepted = set(), [], []
        latest = user_texts[-1]
        prior_question = _pending_question(case, messages)
        answering_remedy = protected.desired_resolution is None and _remedy_question_language(prior_question) is not None
        purchase_updated = record_purchase_date_reply(protected, latest, prior_question)
        if result.scope == "unclear" and not purchase_updated:
            return case.model_copy(deep=True), result.next_question.strip()
        candidate = protected.model_dump()
        if protected.purchase_date_text and PURCHASE_CONTEXT.search(latest):
            # A purchase-year disagreement cannot invalidate a separate incident date.
            unresolved.discard("incident_date")
        rejected_meaning = False
        # Validate the full proposal before changing anything. Pre-marking accepted
        # correction turns makes invalidation independent of model change ordering.
        # A locally confirmed order-date reply changes only that field. Model
        # proposals on the same reply cannot rewrite the other signed facts.
        for change in (() if purchase_updated else result.changes):
            if change.field in seen:
                if not recover or change.field != "timeline":
                    raise _invalid("fact_proposal", "duplicate_field", change.field)
                # A repeated timeline can contain separate append-only events.
                # Consider it only in the verbatim recovery path.
                _diagnostic("fact_proposal", "duplicate_field", change.field)
                failed.append(change)
            seen.add(change.field)
            rule = _change_rule(change, user_texts, unresolved)
            if rule is not None:
                if not recover:
                    raise _invalid("fact_proposal", rule, change.field)
                _diagnostic("fact_proposal", rule, change.field)
                failed.append(change)
            elif change.field == "incident_date" and (change.value is not None or protected.purchase_date_text) and (
                is_purchase_date_proposal(protected, change.source_quote, change.value, user_texts, prior_question)
            ):
                _diagnostic("fact_proposal", "incident_date_not_established", change.field)
                rejected_meaning = True
                continue
            elif change.field == "company_or_seller" and change.value is not None and not named_seller(
                change.value, change.source_quote,
            ):
                _diagnostic("fact_proposal", "seller_name_unconfirmed", change.field)
                rejected_meaning = True
                continue
            elif change.field == "desired_resolution" and change.value is not None:
                if not requested_remedy(change.value, change.source_quote, latest,
                                        answering_remedy_question=answering_remedy):
                    _diagnostic("fact_proposal", "current_remedy_unconfirmed", change.field)
                    rejected_meaning = True
                    continue
                if candidate["desired_resolution"] is not None and REMEDY_SHIFT.search(latest):
                    change = change.model_copy(update={"is_correction": True})
            accepted.append(change)
        if failed:
            return _recover_intake(protected, result.model_copy(update={"changes": accepted}), latest, unresolved, failed)
        if any(change.is_correction and change.field != "user_language" for change in accepted):
            candidate["narrative_review_required"] = True
        for field in sorted(unresolved):
            candidate[field] = None
            candidate["uncertain_fields"][field] = "conflicting"
            candidate["narrative_review_required"] = True

        for change in accepted:
            if change.is_correction and change.field in ("user_summary", "timeline"):
                candidate["purchase_date_text"] = None
                candidate["product_or_service"] = None
            if (candidate["narrative_review_required"] or rejected_meaning) and change.field in ("user_summary", "timeline"):
                continue  # Never restore unproven derived prose from older messages.

            previous = candidate[change.field]
            value = change.value
            if isinstance(previous, list):
                if value is None and change.is_correction:
                    value = []
                if not isinstance(value, list):
                    raise _invalid("fact_merge", "invalid_list", change.field)
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
                        raise _invalid("fact_merge", "conflict_requires_current_quote", change.field)
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
                raise _invalid("fact_merge", "explicit_correction_required", change.field)
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
        updated = CaseFile.model_validate(candidate)
        if not purchase_updated:
            record_purchase_details(updated, latest)
        updated = protect_narratives(updated)
        if rejected_meaning and not updated.narrative_review_required:
            # A paraphrase may repeat the same rejected assertion. Use only
            # full user statements for this turn's narrative in that case.
            summaries = _quoted_statements(updated, accepted, latest, "user_summary")
            if not updated.user_summary and summaries:
                updated.user_summary = summaries[0]
            updated.timeline = list(dict.fromkeys([*updated.timeline, *_quoted_statements(updated, accepted, latest)]))
        language = result.reply_language
        gaps = material_questions(updated, language)
        if updated.narrative_review_required or purchase_updated or (
            core_details_known(updated) and PURCHASE_YEAR_QUESTION[language] in gaps
        ):
            if updated.narrative_review_required:
                _diagnostic("narrative", "review_required")
            question = next_fact_question(updated, language)
            if not question and core_details_known(updated):
                updated.case_status = "ready_for_review"
                updated.unanswered_questions = gaps
                return updated, document_handoff(language)
            updated.case_status = "in_progress"
            question = question or (gaps[0] if gaps else CLARIFY[language]["issue_type"])
            updated.unanswered_questions = list(dict.fromkeys([question, *gaps]))
        elif updated.case_status == "ready_for_review" and not core_details_known(updated):
            updated.case_status = "in_progress"
            if gaps and (question or rejected_meaning):
                question = gaps[0]
                updated.unanswered_questions = gaps
        elif gaps:
            updated.unanswered_questions = gaps
            if question or rejected_meaning:
                question = gaps[0]
        if not question:
            if updated.case_status != "ready_for_review":
                raise _invalid("completion", "incomplete_case_without_question")
            question = document_handoff(language)
        return updated, question
    except (ValidationError, ValueError, TypeError):
        raise _invalid("fact_merge", "case_validation_failed") from None


@dataclass(frozen=True)
class TurnResult:
    case: CaseFile
    reply: str
    guidance: ValidatedGuidance
    intake_error: str | None = None


def run_turn(
    case: CaseFile, messages: list[dict[str, str]], language: str, provider: ModelProvider,
) -> TurnResult:
    """Use one model request for intake or legal guidance and answer narrow case queries locally."""
    _require_user_turn(messages)
    latest = messages[-1]["content"]
    intent = followup_intent(latest)
    remedy_language = _remedy_question_language(_pending_question(case, messages))
    asked_remedy = remedy_language is not None and case.desired_resolution is None
    remedy = None
    if asked_remedy or (case.desired_resolution and (case.issue_type or case.product_or_service)):
        remedy = direct_remedy_answer(latest, asked=asked_remedy)
    if remedy or (intent and intent != "next"):
        # Use recent safety context for deterministic turns too.
        safety = detect_safety(" ".join(item["content"] for item in messages if item["role"] == "user"))
        if safety != "none":
            message = notice(safety, language)
            return TurnResult(case.model_copy(deep=True), message,
                              ValidatedGuidance(language=language, status=safety, message=message))
        updated = protect_narratives(case)
        prior = messages[-2]["content"] if len(messages) > 1 and messages[-2]["role"] == "assistant" else ""
        reply_language = case.user_language or language
        if remedy and remedy_language:
            reply_language = remedy_language
        elif re.search(r"[\u0900-\u097f]", latest):
            reply_language = "hi"
        elif re.search(r"\b(?:kya|maine|mere|mera|batao|haan|nahi|nahin|bana|galti)\b", latest, re.IGNORECASE):
            reply_language = "hinglish"
        message = localized(reply_language, "Ask about your legal options to see checked sources.",
                            "जाँचे गए स्रोतों के लिए अपने कानूनी विकल्प पूछें।",
                            "Checked sources ke liye apne legal options poochhein.")
        reply = (record_remedy_reply(updated, remedy, reply_language) if remedy
                 else local_reply(updated, intent, prior, reply_language))
        return TurnResult(protect_narratives(updated), reply,
                          ValidatedGuidance(language=reply_language, status="case_only", message=message))
    context = retrieve(latest, case)
    try:
        response = provider.analyze(case.model_copy(deep=True), messages, language, context)
    except IntakeError as error:
        if error.code == "invalid_output":
            _diagnostic("provider", "no_usable_output")
        raise
    result = _parse_response(response)

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
        _diagnostic("legal", "unsupported_intake_text")
        message = notice("invalid_citation", result.reply_language)
        return TurnResult(case.model_copy(deep=True), message, ValidatedGuidance(
            language=result.reply_language, status="invalid_citation", message=message,
        ))

    intake_error = None
    if intent == "next" and core_details_known(case):
        # A request for options can get newly checked guidance, but it is not
        # a statement of new facts or consent to restore any old narrative.
        updated = protect_narratives(case)
        reply = document_handoff(result.reply_language)
    else:
        try:
            updated, reply = _apply_intake(case, messages, result, recover=True)
        except IntakeError:
            # Source-checked general information does not require accepting an
            # ungrounded fact update. Preserve the ENTIRE case; report the failure.
            updated = case.model_copy(deep=True)
            reply = ""
            intake_error = "invalid_output"
    guidance = validate_guidance(result, context)
    if guidance.status == "invalid_citation":
        _diagnostic("legal", "invalid_citation")
    if guidance.status in ("urgent_notice", "threat_or_crime", "out_of_scope"):
        # Keep critical warnings visible in chat as well as the options panel.
        reply = guidance.message
        updated = case.model_copy(deep=True)
    elif asked_remedy and updated.desired_resolution is None and reply == CLARIFY[result.reply_language]["desired_resolution"]:
        reply = clarify_remedy(result.reply_language)
    return TurnResult(updated, reply, guidance, intake_error)
