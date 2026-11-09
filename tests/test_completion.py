"""Reproduce the screenshot's terminal-intake 502 without paid model requests."""
import json
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from backend.main import app, server_settings, sign_case
from nyaysaathi.consistency import CLARIFY
from nyaysaathi.intake import IntakeError, run_turn
from nyaysaathi.knowledge import load_knowledge
from nyaysaathi.models import CaseFile
from nyaysaathi.settings import Settings


def reviewed_case():
    return CaseFile(issue_type="wrong product received", user_summary="User received the wrong ordered item.",
                    company_or_seller="Example Marketplace", amount_inr="1000", desired_resolution="refund")


def completion(language="en", **overrides):
    entry = next(item for item in load_knowledge() if item.source_id == "RULES-REFUND")
    return json.dumps({"scope":"in_scope", "reply_language":language, "case_status":"ready_for_review",
                       "next_question":None, "guidance":[{"source_id":entry.source_id,"explanation":entry.guidance[language]}], **overrides},ensure_ascii=False)


@pytest.mark.parametrize("language",["en","hi","hinglish"])
def test_completed_intake_hands_off_without_inventing_a_new_question_or_facts(language):
    original = reviewed_case()
    provider = Mock()
    provider.analyze.return_value = completion(language)
    result = run_turn(original,[{"role":"user","content":"No, now what should I do to proceed?"}],language,provider)
    provider.analyze.assert_called_once()
    assert result.intake_error is None
    assert "Action Package" in result.reply
    assert "?" not in result.reply
    assert result.case.amount_inr == original.amount_inr
    assert result.case.incident_date is None and result.case.evidence_available == []
    assert result.case.unanswered_questions == [CLARIFY[language]["incident_date"]]
    assert result.guidance.status == "grounded" and result.guidance.entries


def test_terminal_response_does_not_bypass_missing_core_case_facts():
    provider = Mock()
    provider.analyze.return_value = completion()
    result = run_turn(CaseFile(),[{"role":"user","content":"What next?"}],"en",provider)
    assert result.intake_error == "invalid_output"
    assert result.case == CaseFile()


def test_incomplete_intake_without_question_still_fails_validation():
    provider = Mock()
    provider.analyze.return_value = completion(case_status="in_progress")
    with pytest.raises(IntakeError,match="invalid_output"):
        run_turn(reviewed_case(),[{"role":"user","content":"What next?"}],"en",provider)


def test_screenshot_followup_returns_200_reply_and_validated_sources(monkeypatch):
    provider = Mock(return_value=completion())
    monkeypatch.setattr("nyaysaathi.gemini.GeminiProvider.analyze",provider)
    app.dependency_overrides[server_settings] = lambda: Settings("offline-key","mock-model")
    try:
        with TestClient(app) as client:
            response=client.post("/api/chat",json={"case":reviewed_case().model_dump(mode="json"),
                "case_signature":sign_case(reviewed_case(), "offline-key"),
                "history":[{"role":"assistant","content":"Do you want to correct any recorded detail before we conclude?"}],
                "message":"No, now what should I do to proceed?"})
        assert response.status_code == 200
        result=response.json()
        assert result["reply"] and "Action Package" in result["reply"]
        assert result["guidance"]["status"] == "grounded"
        assert result["guidance"]["citations"][0]["url"].startswith("https://consumeraffairs.gov.in/")
        assert result["error"] is None
        assert result["case"]["incident_date"] is None
        provider.assert_called_once()
    finally:
        app.dependency_overrides.clear()
