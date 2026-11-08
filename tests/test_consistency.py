"""Offline regressions using the ORIGINAL Phase 6 Gemini responses, never new calls."""

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from nyaysaathi.action_package import generate_package
from nyaysaathi.consistency import protect_narratives
from nyaysaathi.intake import IntakeError, run_intake, run_turn
from nyaysaathi.models import CaseFile


RAW = Path(__file__).resolve().parents[1] / "evaluation" / "raw_outputs" / "live-first-v1"


def replay_original(case_id):
    record = json.loads((RAW / f"{case_id}_turn02_record.json").read_text(encoding="utf-8"))
    original = CaseFile.model_validate(record["case_before"])
    provider = Mock()
    provider.analyze.return_value = (RAW / f"{case_id}_turn02_response.txt").read_text(encoding="utf-8")
    outcome = run_turn(original, record["input_messages"], record["interface_language"], provider)
    provider.analyze.assert_called_once()
    return original, outcome, record


def synthetic_turn(case, text, changes):
    provider = Mock()
    provider.analyze.return_value = json.dumps({
        "scope": "in_scope", "reply_language": "en", "changes": changes,
        "next_question": "Is the old information still correct?",
        "missing_details": ["Could the original amount be 2000?"],
    })
    return run_intake(case, [{"role": "user", "content": text}], "en", provider)


def test_original_t05_updates_current_amount_and_removes_all_stale_prose_and_documents():
    original, result, old_record = replay_original("T05")
    assert result.intake_error is None
    assert original.amount_inr == 2000
    assert result.case.amount_inr == 2500
    assert result.case.user_summary is None
    assert result.case.timeline == []
    assert result.case.narrative_review_required
    assert result.case.company_or_seller == original.company_or_seller
    assert result.case.incident_date == original.incident_date
    assert result.case.desired_resolution == original.desired_resolution
    assert result.case.evidence_available == original.evidence_available
    package = generate_package(result.case, provisional=True)
    assert "₹2,500" in package.complaint
    for output in (result.case.user_summary or "", result.reply, package.complaint, package.summary):
        assert "2000" not in output and "2,000" not in output
    assert "2000" in old_record["action_package"]["complaint"]  # Original failure stays intact.
    assert "narrative" in package.readiness.review


def test_original_t06_clears_date_without_choosing_an_alternative_and_removes_stale_documents():
    original, result, old_record = replay_original("T06")
    assert original.incident_date.isoformat() == "2026-10-03"
    assert result.case.incident_date is None
    assert result.case.uncertain_fields == {"incident_date": "withdrawn"}
    assert result.case.user_summary is None and result.case.timeline == []
    assert result.case.company_or_seller == original.company_or_seller
    assert result.case.amount_inr == original.amount_inr
    assert "date" in result.reply
    package = generate_package(result.case, provisional=True)
    for output in (package.complaint, package.summary, result.reply):
        for old in ("2026-10-03", "3 October 2026", "8 October 2026"):
            assert old not in output
    assert "[Incident date]" in package.complaint
    assert "3 October 2026" in old_record["action_package"]["complaint"]


@pytest.mark.parametrize("case_id", ["T05", "T06"])
def test_legacy_phase6_post_correction_records_are_guarded_even_without_new_flags(case_id):
    record = json.loads((RAW / f"{case_id}_turn02_record.json").read_text(encoding="utf-8"))
    legacy = CaseFile.model_validate(record["case_after"])
    assert not legacy.narrative_review_required
    before = legacy.model_dump()
    package = generate_package(legacy, provisional=True)
    assert "narrative" in package.readiness.review
    if case_id == "T05":
        assert "2000" not in package.complaint + package.summary
        assert "₹2,500" in package.complaint
    else:
        assert "2026-10-03" not in package.complaint + package.summary
        assert "3 October 2026" not in package.complaint + package.summary
    assert legacy.model_dump() == before  # Generator protects a copy, never edits the fixture.


def test_no_global_replacement_when_amount_also_appears_in_unrelated_seller_name():
    case = CaseFile(issue_type="refund", company_or_seller="Shop 2000", amount_inr="2000",
                    user_summary="I paid Rs 2000 and want a refund.", desired_resolution="refund")
    updated, _ = synthetic_turn(case, "Correction: amount 2500", [{
        "field": "amount_inr", "value": "2500", "source_quote": "amount 2500", "is_correction": True,
    }])
    assert updated.company_or_seller == "Shop 2000"
    assert updated.user_summary is None
    package = generate_package(updated, provisional=True)
    assert "To: Shop 2000" in package.complaint
    assert "₹2,500" in package.complaint
    assert "I paid Rs 2000" not in package.complaint


def test_unmarked_conflicting_amount_is_unknown_not_an_implicit_correction():
    case = CaseFile(issue_type="refund", company_or_seller="Shop", amount_inr="2000",
                    user_summary="The recorded purchase amount was Rs 2000.", desired_resolution="refund")
    updated, question = synthetic_turn(case, "Another record says 2500 but I am unsure", [{
        "field": "amount_inr", "value": "2500", "source_quote": "Another record says 2500 but I am unsure",
    }])
    assert updated.amount_inr is None
    assert updated.uncertain_fields == {"amount_inr": "conflicting"}
    assert updated.company_or_seller == "Shop"
    assert "amount" in question and "2500" not in question
    package = generate_package(updated, provisional=True)
    assert "[Amount in INR]" in package.complaint
    assert "2000" not in package.complaint + package.summary
    assert "2500" not in package.complaint + package.summary


def test_conflicting_dates_remain_unknown_until_explicit_current_confirmation():
    case = CaseFile(issue_type="non-delivery", company_or_seller="Shop", amount_inr="1500",
                    incident_date="2026-10-03", user_summary="Order placed on 3 October 2026.", desired_resolution="refund")
    uncertain, _ = synthetic_turn(case, "My other note says 8 October 2026; I am unsure", [{
        "field": "incident_date", "value": "2026-10-08", "source_quote": "My other note says 8 October 2026; I am unsure",
    }])
    assert uncertain.incident_date is None
    assert uncertain.uncertain_fields == {"incident_date": "conflicting"}
    still_unknown, _ = synthetic_turn(uncertain, "8 October 2026 appears on one note", [{
        "field": "incident_date", "value": "2026-10-08", "source_quote": "8 October 2026 appears on one note",
    }])
    assert still_unknown.incident_date is None
    unknown_draft = generate_package(still_unknown, provisional=True)
    assert "2026-10-08" not in unknown_draft.complaint
    confirmed, _ = synthetic_turn(still_unknown, "I confirm the correct date is 8 October 2026", [{
        "field": "incident_date", "value": "2026-10-08", "is_correction": True,
        "source_quote": "I confirm the correct date is 8 October 2026",
    }])
    assert confirmed.incident_date.isoformat() == "2026-10-08"
    assert confirmed.uncertain_fields == {}
    package = generate_package(confirmed, provisional=True)
    assert "2026-10-08" in package.complaint
    assert "2026-10-03" not in package.complaint + package.summary


@pytest.mark.parametrize("model_changes", [[], [{
    "field": "incident_date", "value": "2026-10-08", "is_correction": True,
    "source_quote": "The dates are conflicting; I cannot confirm the correct date",
}]])
def test_user_uncertainty_is_retained_even_when_model_omits_or_mislabels_the_update(model_changes):
    case = CaseFile(issue_type="non-delivery", amount_inr="1500", company_or_seller="Shop",
                    incident_date="2026-10-03", user_summary="Order placed on 3 October 2026.")
    updated, question = synthetic_turn(case, "The dates are conflicting; I cannot confirm the correct date", model_changes)
    assert updated.incident_date is None
    assert updated.uncertain_fields == {"incident_date": "conflicting"}
    assert updated.amount_inr == 1500
    assert "date" in question
    package = generate_package(updated, provisional=True)
    assert "2026-10-03" not in package.complaint + package.summary
    assert "2026-10-08" not in package.complaint + package.summary


def test_narrative_invalidation_does_not_bypass_existing_document_safety_gate():
    case = CaseFile(issue_type="refund", user_summary="I received a court notice on 3 October 2026.")
    with pytest.raises(ValueError, match="outside consumer scope"):
        generate_package(case, provisional=True)


def test_later_model_turn_cannot_resurrect_earlier_summary_timeline_or_metadata():
    _, corrected, _ = replay_original("T05")
    historical = "User ordered a kettle for Rs 2000."
    updated, question = synthetic_turn(corrected.case, historical, [
        {"field": "user_summary", "value": historical, "source_quote": historical},
        {"field": "timeline", "value": [historical], "source_quote": historical},
    ])
    assert updated.user_summary is None and updated.timeline == []
    assert updated.amount_inr == 2500
    assert "2000" not in question
    package = generate_package(updated, provisional=True)
    assert "2000" not in package.complaint + package.summary


@pytest.mark.parametrize("narrative_first", [True, False])
def test_correction_is_safe_regardless_of_model_change_order(narrative_first):
    case = CaseFile(issue_type="refund", amount_inr="2000", user_summary="Paid Rs 2000.", desired_resolution="refund")
    text = "Correction: paid Rs 2500."
    correction = {"field": "amount_inr", "value": "2500", "source_quote": text, "is_correction": True}
    narrative = {"field": "user_summary", "value": text, "source_quote": text}
    updated, _ = synthetic_turn(case, text, [narrative, correction] if narrative_first else [correction, narrative])
    assert updated.amount_inr == 2500
    assert updated.user_summary is None
    assert "2000" not in generate_package(updated, provisional=True).complaint


def test_unproven_old_quote_cannot_create_a_new_conflict_or_override_current_fact():
    case = CaseFile(issue_type="refund", amount_inr="2500", narrative_review_required=True)
    provider = Mock()
    provider.analyze.return_value = json.dumps({
        "scope": "in_scope", "reply_language": "en", "next_question": "What is the seller?",
        "changes": [{"field": "amount_inr", "value": "2000", "source_quote": "Paid 2000"}],
    })
    with pytest.raises(IntakeError, match="invalid_output"):
        run_intake(case, [{"role": "user", "content": "Paid 2000"},
                          {"role": "user", "content": "I have the invoice"}], "en", provider)
    assert case.amount_inr == 2500


def test_dependent_quantified_resolution_is_invalidated_without_inventing_a_replacement():
    case = CaseFile(issue_type="refund", amount_inr="2000", company_or_seller="Shop",
                    desired_resolution="Refund Rs 2000", evidence_available=["invoice", "receipt for Rs 2000"])
    updated, _ = synthetic_turn(case, "Correction: amount 2500", [{
        "field": "amount_inr", "value": "2500", "source_quote": "amount 2500", "is_correction": True,
    }])
    assert updated.desired_resolution is None
    assert updated.evidence_available == ["invoice"]
    assert updated.company_or_seller == "Shop"
    package = generate_package(updated, provisional=True)
    assert "[Desired resolution]" in package.complaint
    assert "2000" not in package.complaint + package.summary


def test_metadata_defaults_are_not_shared_and_protection_is_idempotent():
    first, second = CaseFile(), CaseFile()
    first.uncertain_fields["amount_inr"] = "conflicting"
    assert second.uncertain_fields == {}
    assert protect_narratives(protect_narratives(first)) == protect_narratives(first)


def test_original_raw_evidence_hashes_are_unchanged():
    manifest = json.loads((RAW / "manifest_final.json").read_text(encoding="utf-8"))
    for name, expected in manifest["raw_file_sha256"].items():
        assert hashlib.sha256((RAW / name).read_bytes()).hexdigest() == expected
