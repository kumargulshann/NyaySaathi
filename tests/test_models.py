"""Defaults must preserve unknown facts instead of inventing case details."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from nyaysaathi.models import CaseFile


def test_empty_case_has_expected_unknown_fields():
    assert CaseFile().model_dump() == {
        "issue_type": None,
        "user_language": None,
        "user_summary": None,
        "company_or_seller": None,
        "amount_inr": None,
        "incident_date": None,
        "timeline": [],
        "evidence_available": [],
        "evidence_missing": [],
        "desired_resolution": None,
        "unanswered_questions": [],
        "confidence_or_uncertainty": None,
        "case_status": "not_started",
        "narrative_review_required": False,
        "uncertain_fields": {},
    }


def test_partial_case_does_not_infer_missing_details():
    case = CaseFile(user_summary="Refund nahi mila", user_language="hinglish")
    assert case.user_summary == "Refund nahi mila"
    assert case.user_language == "hinglish"
    assert case.company_or_seller is None
    assert case.amount_inr is None
    assert case.incident_date is None
    assert case.confidence_or_uncertainty is None
    assert case.evidence_missing == []
    assert case.case_status == "not_started"


def test_case_lists_are_not_shared():
    first = CaseFile()
    second = CaseFile()
    for field in (
        "timeline", "evidence_available", "evidence_missing", "unanswered_questions"
    ):
        getattr(first, field).append("User-supplied entry")
        assert getattr(second, field) == []


def test_explicit_amount_and_date_are_parsed():
    case = CaseFile(amount_inr="1299.50", incident_date="2026-10-01")
    assert case.amount_inr == Decimal("1299.50")
    assert case.incident_date == date(2026, 10, 1)


def test_missing_amount_is_distinct_from_zero():
    assert CaseFile().amount_inr is None
    assert CaseFile(amount_inr=0).amount_inr == Decimal("0")


def test_negative_amount_is_rejected():
    with pytest.raises(ValidationError):
        CaseFile(amount_inr="-1")
