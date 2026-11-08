import json
from unittest.mock import Mock

import pytest

from nyaysaathi.intake import IntakeError, run_intake
from nyaysaathi.models import CaseFile


def response(changes=None, **overrides):
    return json.dumps({
        "scope": "in_scope", "reply_language": "en", "changes": changes or [],
        "next_question": "Which seller did you buy from?", **overrides,
    })


def change(field, value, quote, correction=False):
    return {"field": field, "value": value, "source_quote": quote, "is_correction": correction}


def run(case, text, output, previous=None):
    provider = Mock()
    provider.analyze.return_value = output
    messages = (previous or []) + [{"role": "user", "content": text}]
    result = run_intake(case, messages, "en", provider)
    provider.analyze.assert_called_once()
    return result


def test_partial_extraction_keeps_unknowns_and_original_case():
    original = CaseFile()
    updated, reply = run(original, "Refund of Rs 1200 is pending", response([
        change("issue_type", "refund", "Refund"),
        change("amount_inr", "1200", "Rs 1200"),
    ], evidence_missing=["Ask whether an invoice is available"]))
    assert updated.amount_inr == 1200
    assert updated.company_or_seller is None
    assert updated.incident_date is None
    assert updated.evidence_available == []
    assert updated.case_status == "in_progress"
    assert updated.unanswered_questions == [reply]
    assert original == CaseFile()


def test_new_details_preserve_old_facts_and_append_evidence():
    original = CaseFile(company_or_seller="Shop", amount_inr="1200", evidence_available=["invoice"])
    updated, _ = run(original, "I also have payment proof", response([
        change("evidence_available", ["payment proof"], "payment proof"),
    ]))
    assert updated.company_or_seller == "Shop"
    assert updated.amount_inr == 1200
    assert updated.evidence_available == ["invoice", "payment proof"]
    assert original.evidence_available == ["invoice"]


def test_explicit_correction_changes_amount_and_allows_retraction():
    original = CaseFile(amount_inr="1200", incident_date="2026-10-01")
    updated, _ = run(original, "Correction: amount was 1500; I do not know the date", response([
        change("amount_inr", "1500", "Correction: amount was 1500", True),
        change("incident_date", None, "I do not know the date", True),
    ]))
    assert updated.amount_inr == 1500
    assert updated.incident_date is None
    assert original.amount_inr == 1200


def test_explicit_evidence_correction_replaces_list():
    original = CaseFile(evidence_available=["invoice", "payment proof"])
    updated, _ = run(original, "Correction: only payment proof", response([
        change("evidence_available", ["payment proof"], "Correction: only payment proof", True),
    ]))
    assert updated.evidence_available == ["payment proof"]


@pytest.mark.parametrize("output", [
    "not JSON",
    response([change("amount_inr", "-1", "-1")]),
    response([change("amount_inr", "10", "invented quote")]),
    response([change("incident_date", "not-a-date", "not-a-date")]),
    response([change("case_status", "ready_for_review", "New shop")]),
    response(next_question="What date? Which seller?"),
    response(next_question=None),
    response([change("timeline", ["new event"], "new event"),
              change("amount_inr", "-1", "-1")]),
    response([change("amount_inr", "10", "10"), change("amount_inr", "20", "20")]),
])
def test_invalid_output_is_atomic(output):
    case = CaseFile(company_or_seller="Original shop", timeline=["original event"])
    before = case.model_dump()
    with pytest.raises(IntakeError, match="invalid_output"):
        run(case, "New shop, -1, not-a-date, new event, 10, 20", output)
    assert case.model_dump() == before


def test_assistant_words_cannot_support_facts():
    with pytest.raises(IntakeError, match="invalid_output"):
        run(CaseFile(), "No", response([change("amount_inr", "200", "200")]),
            previous=[{"role": "assistant", "content": "Was it 200?"}])


def test_old_user_quote_cannot_support_a_current_correction():
    with pytest.raises(IntakeError, match="invalid_output"):
        run(CaseFile(amount_inr="100"), "I have an invoice", response([
            change("amount_inr", "200", "Correction: 200", True),
        ]), previous=[{"role": "user", "content": "Correction: 200"}])


@pytest.mark.parametrize("scope", ["out_of_scope", "unclear"])
def test_out_of_scope_or_unclear_cannot_change_case(scope):
    original = CaseFile(company_or_seller="Original shop")
    updated, reply = run(original, "Help with my divorce", response([
        change("company_or_seller", "Invented", "not grounded"),
    ], scope=scope))
    assert updated == original
    assert reply
    if scope == "out_of_scope":
        assert "outside that scope" in reply


@pytest.mark.parametrize("language,question", [
    ("en", "When did you place the order?"),
    ("hi", "आपने ऑर्डर कब दिया था?"),
    ("hinglish", "Aapne order kab kiya tha?"),
])
def test_model_question_is_returned_in_its_language(language, question):
    _, reply = run(CaseFile(), "Refund pending", response(
        reply_language=language, next_question=question,
    ))
    assert reply == question


def test_provider_failure_does_not_mutate_case():
    case = CaseFile(timeline=["original"])
    provider = Mock()

    def fail(copy, messages, language):
        copy.timeline.append("should not leak")
        raise IntakeError("timeout")

    provider.analyze.side_effect = fail
    with pytest.raises(IntakeError, match="timeout"):
        run_intake(case, [{"role": "user", "content": "Refund pending"}], "en", provider)
    assert case.timeline == ["original"]
    provider.analyze.assert_called_once()


def test_readiness_does_not_imply_unknown_core_fields_are_complete():
    updated, _ = run(CaseFile(), "Refund pending", response(case_status="ready_for_review"))
    assert updated.case_status == "in_progress"
