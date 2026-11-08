"""Offline UI checks using seeded fictional cases; no model is needed."""

from pathlib import Path
import json
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest
import streamlit as st

from nyaysaathi.action_package import generate_package
from nyaysaathi.guidance import ValidatedGuidance
from nyaysaathi.models import CaseFile
from nyaysaathi.settings import Settings


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def complete_case(amount="2999"):
    return CaseFile(
        issue_type="defective product", user_summary="The purchased headphones arrived damaged.",
        company_or_seller="Example Shop", amount_inr=amount, incident_date="2026-11-01",
        evidence_available=["invoice"], desired_resolution="A refund.",
    )


def prepare(monkeypatch, case):
    monkeypatch.setattr("nyaysaathi.settings.get_settings", lambda _: Settings())
    model = Mock(side_effect=AssertionError("Document actions must not call Gemini"))
    monkeypatch.setattr("nyaysaathi.gemini.GeminiProvider.analyze", model)
    generator = Mock(wraps=generate_package)
    monkeypatch.setattr("nyaysaathi.action_package.generate_package", generator)
    app = AppTest.from_file(APP_PATH, default_timeout=20)
    app.session_state["case_file"] = case
    app.run()
    assert not app.exception
    return app, model, generator


def test_no_package_generation_without_button_and_edits_survive_reruns(monkeypatch):
    app, model, generator = prepare(monkeypatch, complete_case())
    assert app.session_state["action_package"] is None
    app.run()
    generator.assert_not_called()
    app.button(key="generate_action_package").click().run()
    assert not app.exception
    generator.assert_called_once()
    app.text_area(key="action_complaint_text").set_value("My reviewed complaint — preserve this edit.").run()
    app.text_area(key="action_summary_text").set_value("My reviewed NCH summary.").run()
    app.sidebar.selectbox[0].select("हिन्दी").run()
    app.run()
    assert not app.exception
    assert app.text_area(key="action_complaint_text").value == "My reviewed complaint — preserve this edit."
    assert app.text_area(key="action_summary_text").value == "My reviewed NCH summary."
    assert generator.call_count == 1
    model.assert_not_called()


def test_case_correction_warns_but_only_explicit_regeneration_replaces_edits(monkeypatch):
    app, model, generator = prepare(monkeypatch, complete_case())
    app.button(key="generate_action_package").click().run()
    app.text_area(key="action_complaint_text").set_value("User's manual edits.").run()
    old_summary = app.text_area(key="action_summary_text").value
    app.session_state["case_file"] = complete_case("2500")
    app.run()
    assert app.text_area(key="action_complaint_text").value == "User's manual edits."
    assert app.text_area(key="action_summary_text").value == old_summary
    assert any("outdated" in alert.value for alert in app.warning)
    assert generator.call_count == 1
    app.button(key="generate_action_package").click().run()
    assert not app.exception
    assert "₹2,500" in app.text_area(key="action_complaint_text").value
    assert "manual edits" not in app.text_area(key="action_complaint_text").value
    assert generator.call_count == 2
    model.assert_not_called()


def test_changing_document_language_requires_explicit_regeneration(monkeypatch):
    app, model, generator = prepare(monkeypatch, complete_case())
    app.button(key="generate_action_package").click().run()
    original = app.text_area(key="action_complaint_text").value
    app.selectbox(key="action_language").select("हिन्दी").run()
    assert app.text_area(key="action_complaint_text").value == original
    assert any("outdated" in alert.value for alert in app.warning)
    assert generator.call_count == 1
    app.button(key="generate_action_package").click().run()
    assert "विषय: उपभोक्ता शिकायत" in app.text_area(key="action_complaint_text").value
    assert generator.call_count == 2
    model.assert_not_called()


def test_partial_case_requires_explicit_provisional_choice(monkeypatch):
    app, model, generator = prepare(monkeypatch, CaseFile(
        issue_type="refund", user_summary="Refund for the purchased item has not arrived.",
    ))
    assert app.button(key="generate_action_package").disabled
    app.checkbox(key="action_provisional").check().run()
    assert not app.button(key="generate_action_package").disabled
    app.button(key="generate_action_package").click().run()
    assert not app.exception
    assert "[Seller/company]" in app.text_area(key="action_complaint_text").value
    assert "[Incident date]" in app.text_area(key="action_complaint_text").value
    generator.assert_called_once()
    model.assert_not_called()


def test_out_of_scope_blocks_generation_and_downloads_without_erasing_old_edits(monkeypatch):
    downloads = Mock(wraps=st.download_button)
    monkeypatch.setattr(st, "download_button", downloads)
    app, model, generator = prepare(monkeypatch, complete_case())
    app.button(key="generate_action_package").click().run()
    app.text_area(key="action_complaint_text").set_value("Keep my earlier edit.").run()
    app.session_state["legal_guidance"] = ValidatedGuidance(status="out_of_scope", message="Outside consumer scope.")
    app.run()
    assert not app.exception
    assert app.button(key="generate_action_package").disabled
    assert app.text_area(key="action_complaint_text").value == "Keep my earlier edit."
    assert all(call.kwargs["disabled"] for call in downloads.call_args_list[-2:])
    assert generator.call_count == 1
    model.assert_not_called()


def test_download_buttons_receive_current_edited_utf8_text(monkeypatch):
    downloads = Mock(wraps=st.download_button)
    monkeypatch.setattr(st, "download_button", downloads)
    app, model, _ = prepare(monkeypatch, complete_case())
    app.button(key="generate_action_package").click().run()
    edited = "Reviewed complaint — मेरा संपादन ₹2,999"
    app.text_area(key="action_complaint_text").set_value(edited).run()
    current = {call.kwargs["key"]: call.kwargs for call in downloads.call_args_list[-2:]}
    complaint = current["download_action_complaint"]
    summary = current["download_action_summary"]
    assert complaint["data"].decode("utf-8-sig") == edited
    assert complaint["file_name"].endswith("_en.txt")
    assert summary["data"].decode("utf-8-sig") == app.text_area(key="action_summary_text").value
    assert summary["mime"] == "text/plain; charset=utf-8"
    assert not app.exception
    model.assert_not_called()


def test_original_t05_correction_preserves_edits_until_explicit_provisional_regeneration(monkeypatch):
    from nyaysaathi.intake import run_turn

    raw = APP_PATH.parent / "evaluation" / "raw_outputs" / "live-first-v1"
    record = json.loads((raw / "T05_turn02_record.json").read_text(encoding="utf-8"))
    original = CaseFile.model_validate(record["case_before"])
    app, model, generator = prepare(monkeypatch, original)
    app.button(key="generate_action_package").click().run()
    app.text_area(key="action_complaint_text").set_value("My preserved manual complaint.").run()
    app.text_area(key="action_summary_text").set_value("My preserved manual summary.").run()
    fixture_provider = Mock()
    fixture_provider.analyze.return_value = (raw / "T05_turn02_response.txt").read_text(encoding="utf-8")
    corrected = run_turn(original, record["input_messages"], record["interface_language"], fixture_provider)
    app.session_state["case_file"] = corrected.case
    app.run()
    assert not app.exception
    assert app.session_state["case_file"].amount_inr == 2500
    assert app.session_state["case_file"].user_summary is None
    assert app.text_area(key="action_complaint_text").value == "My preserved manual complaint."
    assert app.text_area(key="action_summary_text").value == "My preserved manual summary."
    assert any("outdated" in item.value for item in app.warning)
    assert generator.call_count == 1
    app.checkbox(key="action_provisional").check().run()
    app.button(key="generate_action_package").click().run()
    assert not app.exception
    for key in ("action_complaint_text", "action_summary_text"):
        assert "2000" not in app.text_area(key=key).value
        assert "2,000" not in app.text_area(key=key).value
        assert "₹2,500" in app.text_area(key=key).value
    assert generator.call_count == 2
    model.assert_not_called()
