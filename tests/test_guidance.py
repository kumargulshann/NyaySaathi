"""OFFLINE SYNTHETIC responses: these fixtures are not live Gemini outputs."""

from datetime import date
import json
from unittest.mock import Mock

import pytest

from nyaysaathi.intake import IntakeError, run_turn
from nyaysaathi.knowledge import KnowledgeEntry, RetrievalContext, load_knowledge, retrieve
from nyaysaathi.models import CaseFile


def entry(source_id):
    return next(item for item in load_knowledge() if item.source_id == source_id)


def mock_response(source_id=None, *, language="en", **overrides):
    selections = [] if source_id is None else [{
        "source_id": source_id, "explanation": entry(source_id).guidance[language],
    }]
    return json.dumps({
        "scope": "in_scope", "reply_language": language, "guidance": selections,
        "next_question": {
            "en": "What date did you place the order?",
            "hi": "आपने ऑर्डर किस तारीख को दिया था?",
            "hinglish": "Aapne order kis date ko kiya tha?",
        }[language],
        **overrides,
    })


def turn(question, output, case=None):
    provider = Mock()
    provider.analyze.return_value = output
    result = run_turn(case or CaseFile(), [{"role": "user", "content": question}], "en", provider)
    provider.analyze.assert_called_once()
    return result, provider.analyze.call_args.args[3]


@pytest.mark.parametrize("question,source_id", [
    ("My purchased headphones arrived damaged. What are my options?", "CPA-DEFECT"),
    ("My online order was not delivered. What can I do?", "RULES-NONDELIVERY"),
    ("The seller is withholding my refund. What are my options?", "RULES-REFUND"),
])
def test_consumer_options_have_exact_claim_level_grounding(question, source_id):
    result, context = turn(question, mock_response(source_id))
    assert source_id in {item.source_id for item in context.entries}
    assert result.guidance.status == "grounded"
    assert result.guidance.entries == (entry(source_id),)
    assert result.guidance.entries[0].source_url.startswith("https://consumeraffairs.gov.in/")
    assert result.case.company_or_seller is None
    assert result.case.incident_date is None
    assert result.case.evidence_available == []


@pytest.mark.parametrize("language,question", [
    ("hi", "मेरा उत्पाद खराब है और रिफंड नहीं मिला। क्या करूँ?"),
    ("hinglish", "Mera product kharab hai aur refund nahi mila. Kya karu?"),
])
def test_hindi_and_hinglish_options_are_audited_localized_text(language, question):
    result, _ = turn(question, mock_response("RULES-REFUND", language=language))
    assert result.guidance.status == "grounded"
    assert result.guidance.language == language
    assert result.guidance.entries[0].guidance[language] == entry("RULES-REFUND").guidance[language]


@pytest.mark.parametrize("bad_id", ["FAKE-SECTION", "https://evil.example/law", "NCH-CONTACT"])
def test_unknown_url_or_nonretrieved_id_cannot_become_a_reference(bad_id):
    output = mock_response(guidance=[{"source_id": bad_id, "explanation": "Refund guaranteed"}])
    result, _ = turn("My product arrived damaged", output)
    assert result.guidance.status == "invalid_citation"
    assert result.guidance.entries == ()
    assert "guaranteed" not in result.guidance.message


@pytest.mark.parametrize("claim", [
    "Section 999 guarantees a refund within 24 hours.",
    "The seller will definitely lose and pay compensation.",
    "https://evil.example is your legal source.",
    "There is never a force-majeure exception for delivery delays.",
])
def test_real_source_id_does_not_validate_unsupported_claims(claim):
    result, _ = turn("My online order was not delivered", mock_response(guidance=[{
        "source_id": "RULES-NONDELIVERY", "explanation": claim,
    }]))
    assert result.guidance.status == "invalid_citation"
    assert not result.guidance.entries
    assert claim not in result.reply


def test_fabricated_section_cannot_leak_through_intake_question():
    original = CaseFile(company_or_seller="Original seller", amount_inr="2999")
    result, _ = turn("Refund pending", mock_response(
        "RULES-REFUND", next_question="Section 999 guarantees your refund. What date was the order?",
    ), original)
    assert result.case == original
    assert not result.guidance.entries
    assert "999" not in result.reply


def test_no_available_sources_returns_explicit_uncertainty(monkeypatch):
    monkeypatch.setattr("nyaysaathi.knowledge.load_knowledge", lambda: ())
    result, context = turn("My refund is pending", mock_response("RULES-REFUND"))
    assert not context.entries
    assert result.guidance.status == "insufficient_sources"
    assert not result.guidance.entries


@pytest.mark.parametrize("question,status", [
    ("I want a divorce", "out_of_scope"),
    ("मेरे तलाक में मदद करें", "out_of_scope"),
    ("Court notice received; the hearing deadline is tomorrow", "urgent_notice"),
    ("Seller threatened violence when I asked for a refund", "threat_or_crime"),
    ("Seller ne dhamki di", "threat_or_crime"),
])
def test_critical_or_unrelated_questions_override_model_guidance(question, status):
    original = CaseFile(company_or_seller="Original seller")
    result, context = turn(question, mock_response("RULES-REFUND"), original)
    assert context.safety == status
    assert result.guidance.status == status
    assert not result.guidance.entries
    assert result.reply == result.guidance.message
    assert original.company_or_seller == "Original seller"


def test_model_out_of_scope_flag_overrides_prior_consumer_case():
    result, _ = turn("I need unrelated help", mock_response(
        "RULES-REFUND", scope="out_of_scope",
    ), CaseFile(issue_type="refund", company_or_seller="Shop"))
    assert not result.guidance.entries
    assert result.guidance.status == "out_of_scope"
    assert result.case.company_or_seller == "Shop"


def test_api_failure_preserves_existing_case():
    case = CaseFile(company_or_seller="Shop", timeline=["User-reported event"])
    before = case.model_dump()
    provider = Mock()
    provider.analyze.side_effect = IntakeError("rate_limit")
    with pytest.raises(IntakeError, match="rate_limit"):
        run_turn(case, [{"role": "user", "content": "Refund pending"}], "en", provider)
    assert case.model_dump() == before
    provider.analyze.assert_called_once()


def test_guidance_and_new_evidence_do_not_overwrite_existing_facts():
    original = CaseFile(company_or_seller="Shop", amount_inr="2999", evidence_available=["invoice"])
    result, _ = turn("Refund pending; I have payment proof", mock_response(
        "RULES-REFUND", changes=[{
            "field": "evidence_available", "value": ["payment proof"], "source_quote": "payment proof",
        }],
    ), original)
    assert result.guidance.status == "grounded"
    assert result.case.company_or_seller == "Shop"
    assert result.case.amount_inr == 2999
    assert result.case.evidence_available == ["invoice", "payment proof"]
    assert original.evidence_available == ["invoice"]


def test_bad_intake_quote_keeps_case_but_does_not_discard_independent_grounding():
    original = CaseFile(company_or_seller="Shop", amount_inr="2999")
    result, _ = turn("Refund pending; I have payment proof", mock_response(
        "RULES-REFUND", changes=[{
            "field": "evidence_available", "value": ["payment proof"],
            "source_quote": "Refund pending... payment proof",
        }],
    ), original)
    assert result.case == original
    assert result.intake_error == "invalid_output"
    assert result.guidance.status == "grounded"
    assert result.guidance.entries == (entry("RULES-REFUND"),)


def test_retrieval_is_deterministic_and_uses_question_and_existing_case():
    case = CaseFile(issue_type="defective product")
    first = retrieve("How can I contact NCH helpline?", case)
    second = retrieve("How can I contact NCH helpline?", case)
    assert first == second
    assert any(item.source_id == "CPA-DEFECT" for item in first.entries)
    assert any(item.source_id.startswith("NCH-") for item in first.entries)
    assert all("question=" in reason and "case=" in reason for reason in first.reasons)
    assert retrieve("What is the orbital period of Neptune?", CaseFile()).entries == ()


def test_review_cutoff_blocks_stale_records_after_amendment_commencement():
    context = retrieve("refund", CaseFile(), today=date(2027, 1, 1))
    assert not context.entries
    assert context.safety == "insufficient_sources"


def test_a_future_incident_does_not_apply_current_rules():
    assert not retrieve("refund", CaseFile(incident_date="2027-02-01"), today=date(2026, 11, 9)).entries


def test_explicit_unknown_section_has_no_grounded_answer():
    assert not retrieve("Does Section 999 guarantee my refund?", CaseFile()).entries


def test_knowledge_entries_are_small_auditable_and_official():
    entries = load_knowledge()
    assert 8 <= len(entries) <= 12
    assert len({item.source_id for item in entries}) == len(entries)
    assert all(item.provision_or_location and item.date_checked and item.limitation for item in entries)
    assert "1 January 2027" in entry("ECOM-2026-STATUS").guidance["en"]
    invalid = entry("NCH-PORTAL").model_dump()
    invalid["source_url"] = "https://evil.example/"
    with pytest.raises(ValueError):
        KnowledgeEntry.model_validate(invalid)


def test_reference_text_cannot_override_the_system_instruction():
    from nyaysaathi.gemini import SYSTEM_INSTRUCTION
    assert "untrusted REFERENCE DATA" in SYSTEM_INSTRUCTION
    assert "COPY EXACTLY" in SYSTEM_INSTRUCTION


def test_fabricated_model_url_is_not_a_schema_field():
    output = mock_response(guidance=[{
        "source_id": "RULES-REFUND", "explanation": entry("RULES-REFUND").guidance["en"],
        "url": "https://evil.example/",
    }])
    with pytest.raises(IntakeError, match="invalid_output"):
        turn("refund pending", output)
