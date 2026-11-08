"""Offline, fictional consumer cases; document generation never calls a model."""

from unittest.mock import Mock
import json

import pytest

from nyaysaathi.action_package import (
    assess_readiness, case_fingerprint, download_bytes, evidence_checklist, generate_package,
)
from nyaysaathi.intake import run_intake
from nyaysaathi.models import CaseFile


@pytest.fixture
def complete_case():
    return CaseFile(
        issue_type="defective product", user_language="en",
        user_summary="The headphones arrived damaged and my refund request was declined.",
        company_or_seller="Example Shop", amount_inr="2999.50", incident_date="2026-11-01",
        timeline=["Emailed the seller on 2026-11-02; refund not received."],
        evidence_available=["invoice", "photos of damaged headphones"],
        desired_resolution="A refund of the purchase amount.",
    )


def test_complete_defective_case_is_ready_and_uses_only_supplied_facts(complete_case):
    original = complete_case.model_dump()
    package = generate_package(complete_case)
    assert package.readiness.status == "ready"
    for fact in ("Example Shop", "₹2,999.50", "2026-11-01", "2026-11-02", complete_case.user_summary):
        assert fact in package.complaint
    assert "Please review my concern and provide a written response" in package.complaint
    assert "[Order ID]" in package.complaint
    assert "[Your name]" in package.complaint
    assert "not officially validated" in package.summary
    assert "Evidence reported by user; not inspected" in package.summary
    assert complete_case.model_dump() == original


def test_non_delivery_collects_tracking_without_inventing_defect_photos():
    case = CaseFile(
        issue_type="non-delivery", user_summary="The ordered parcel has not arrived.",
        company_or_seller="Example Marketplace", desired_resolution="A refund.",
    )
    package = generate_package(case, provisional=True)
    assert "parcel has not arrived" in package.complaint
    assert "Delivery tracking" in package.checklist.collect
    assert "Photos/videos (if defects are involved)" in package.checklist.unknown
    assert package.checklist.reported == ()
    assert "[Amount in INR]" in package.complaint


def test_missing_seller_requires_explicit_provisional_choice(complete_case):
    case = CaseFile.model_validate({**complete_case.model_dump(), "company_or_seller": None})
    assert assess_readiness(case).status == "missing"
    with pytest.raises(ValueError, match="provisional"):
        generate_package(case)
    draft = generate_package(case, provisional=True)
    assert "To: [Seller/company]" in draft.complaint


def test_missing_date_and_generic_incident_date_are_not_invented_purchase_dates(complete_case):
    case = CaseFile.model_validate({**complete_case.model_dump(), "incident_date": None})
    draft = generate_package(case, provisional=True)
    assert "[Incident date]" in draft.complaint
    assert "Purchase/order date: [Purchase date]" in draft.complaint
    known = generate_package(complete_case)
    assert "Purchase/order date: [Purchase date]" in known.complaint
    assert "confirm what this date refers to): 2026-11-01" in known.complaint


def test_missing_evidence_is_never_described_as_available(complete_case):
    case = CaseFile.model_validate({**complete_case.model_dump(), "evidence_available": []})
    package = generate_package(case, provisional=True)
    assert package.checklist.reported == ()
    assert "[Evidence availability not confirmed]" in package.summary
    assert "Invoice or receipt" in package.checklist.collect
    assert "Photos/videos (if defects are involved)" in package.checklist.collect
    assert "attached" not in package.complaint.casefold()


def test_reported_evidence_wins_over_a_suggested_missing_item(complete_case):
    case = CaseFile.model_validate({**complete_case.model_dump(), "evidence_missing": ["invoice"]})
    checklist = evidence_checklist(case, "en")
    assert "invoice" in checklist.reported
    assert "Invoice or receipt" not in checklist.collect
    assert "Invoice or receipt" not in checklist.unknown
    assert "Payment proof" in checklist.collect


def test_explicit_user_correction_changes_only_a_newly_generated_package(complete_case):
    old = generate_package(complete_case)
    provider = Mock()
    provider.analyze.return_value = json.dumps({
        "scope": "in_scope", "reply_language": "en",
        "changes": [{"field": "amount_inr", "value": "2500", "is_correction": True,
                     "source_quote": "Correction: the amount is 2500"}],
        "next_question": "Do you want to correct another detail?",
    })
    updated, _ = run_intake(complete_case, [{"role": "user", "content": "Correction: the amount is 2500"}], "en", provider)
    assert old.fingerprint != case_fingerprint(updated)
    assert "₹2,999.50" in old.complaint
    assert "₹2,500" in generate_package(updated, provisional=True).complaint
    assert complete_case.amount_inr != updated.amount_inr


def test_hindi_complaint_uses_hindi_template_and_preserves_user_wording(complete_case):
    case = CaseFile.model_validate({**complete_case.model_dump(), "user_summary": "हेडफोन खराब मिले और रिफंड नहीं मिला।"})
    package = generate_package(case, "hi")
    assert "विषय: उपभोक्ता शिकायत" in package.complaint
    assert "हेडफोन खराब मिले और रिफंड नहीं मिला।" in package.complaint
    assert "लिखित उत्तर" in package.complaint
    assert "[ऑर्डर आईडी]" in package.complaint
    assert "आधिकारिक रूप से सत्यापित नहीं" in package.summary


@pytest.mark.parametrize("case", [
    CaseFile(issue_type="out_of_scope", user_summary="Unrelated issue"),
    CaseFile(issue_type="divorce", user_summary="I need help with divorce"),
])
def test_out_of_scope_generation_is_disabled(case):
    assert assess_readiness(case).status == "out_of_scope"
    with pytest.raises(ValueError, match="outside consumer scope"):
        generate_package(case, provisional=True)


def test_external_out_of_scope_signal_blocks_an_existing_consumer_case(complete_case):
    with pytest.raises(ValueError):
        generate_package(complete_case, out_of_scope=True)


def test_empty_case_has_no_usable_draft():
    assert assess_readiness(CaseFile()).status == "insufficient"
    assert not assess_readiness(CaseFile()).provisional_allowed
    with pytest.raises(ValueError, match="description or issue type"):
        generate_package(CaseFile(), provisional=True)


def test_issue_only_allows_a_clearly_provisional_placeholder_draft():
    case = CaseFile(issue_type="refund")
    assert assess_readiness(case).status == "insufficient"
    package = generate_package(case, provisional=True)
    assert "[Describe the consumer problem in neutral factual language]" in package.complaint
    assert "[Desired resolution]" in package.complaint


def test_no_fabricated_sections_deadlines_or_threats_are_copied(complete_case):
    case = CaseFile.model_validate({
        **complete_case.model_dump(),
        "user_summary": "Section 999 guarantees a refund within 24 hours.",
        "desired_resolution": "Refund me or else I will destroy your shop.",
    })
    package = generate_package(case, provisional=True)
    assert "Section 999" not in package.complaint + package.summary
    assert "24 hours" not in package.complaint + package.summary
    assert "destroy" not in package.complaint + package.summary
    assert "[Desired resolution]" in package.complaint
    assert package.readiness.review


def test_a_recorded_amount_does_not_claim_a_payment_was_made(complete_case):
    package = generate_package(complete_case)
    assert "I paid" not in package.complaint
    assert "confirm whether price, payment or refund" in package.complaint


def test_amount_is_not_silently_rounded_and_zero_is_not_unknown(complete_case):
    for amount, expected in (("1.005", "₹1.005"), ("0", "₹0")):
        case = CaseFile.model_validate({**complete_case.model_dump(), "amount_inr": amount})
        package = generate_package(case)
        assert expected in package.complaint
        assert "[Amount in INR]" not in package.complaint


def test_no_prior_contact_is_invented_and_negated_contact_is_not_a_confirmed_attempt(complete_case):
    case = CaseFile.model_validate({**complete_case.model_dump(), "timeline": ["I have not contacted the seller."]})
    package = generate_package(case)
    attempts_section = package.complaint.split("Previous communication reported by me:\n", 1)[1]
    assert attempts_section.startswith("[Add previous communication only if it happened")
    assert "I have not contacted the seller." in package.summary  # Original timeline remains visible.


def test_download_bytes_roundtrip_hindi_and_edited_text(complete_case):
    package = generate_package(complete_case, "hi")
    edited = package.complaint + "\nमेरा संपादन ₹2,999.50"
    assert download_bytes(edited).decode("utf-8-sig") == edited
    assert download_bytes(package.summary).decode("utf-8-sig") == package.summary


def test_hinglish_users_choose_a_formal_template_not_an_unsupported_language(complete_case):
    case = CaseFile.model_validate({**complete_case.model_dump(), "user_language": "hinglish"})
    assert generate_package(case, "en").language == "en"
    assert generate_package(case, "hi").language == "hi"
    with pytest.raises(ValueError, match="English or Hindi"):
        generate_package(case, "hinglish")
