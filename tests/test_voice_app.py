"""Offline voice workflow tests; synthetic PCM and mocked transcription/intake."""

from io import BytesIO
import json
from pathlib import Path
from unittest.mock import Mock

import streamlit as st
from streamlit.testing.v1 import AppTest

from nyaysaathi.intake import IntakeError
from nyaysaathi.models import CaseFile
from nyaysaathi.settings import Settings
from nyaysaathi.transcription import TranscriptionError, TranscriptionResult, validate_audio
from test_transcription import wav_bytes


APP = Path(__file__).resolve().parents[1] / "app.py"


def recording(data=None):
    uploaded = BytesIO(data if data is not None else wav_bytes())
    uploaded.type = "audio/wav"
    return uploaded


def prepare(monkeypatch, transcript="Mera 2000 ka refund pending hai", intake_error=None):
    audio = [recording()]
    monkeypatch.setattr(st, "audio_input", lambda *args, **kwargs: audio[0])
    monkeypatch.setattr("nyaysaathi.settings.get_settings", lambda _: Settings("test-key", "test-intake"))
    transcribe = Mock(return_value=TranscriptionResult(
        transcript=transcript, model="mock-asr", audio=validate_audio(audio[0].getvalue(), "audio/wav"),
    ))
    monkeypatch.setattr("nyaysaathi.transcription.transcribe_audio", transcribe)
    model = Mock(return_value=json.dumps({
        "scope": "in_scope", "reply_language": "hinglish",
        "changes": [{"field": "amount_inr", "value": "2500", "source_quote": "2500", "is_correction": True}],
        "next_question": "Seller ka naam kya hai?",
    }), side_effect=intake_error)
    monkeypatch.setattr("nyaysaathi.gemini.GeminiProvider.analyze", model)
    app = AppTest.from_file(APP, default_timeout=20)
    app.session_state["case_file"] = CaseFile(
        issue_type="refund", amount_inr="2000", company_or_seller="Example Shop",
        user_summary="Refund of Rs 2000 is pending.", desired_resolution="refund",
    )
    app.session_state["messages"] = [{"role": "user", "content": "My earlier refund of 2000"}]
    app.run()
    assert not app.exception
    return app, audio, transcribe, model


def test_recording_and_reruns_do_not_transcribe_or_mutate_existing_case(monkeypatch):
    app, _, transcribe, model = prepare(monkeypatch)
    before = app.session_state["case_file"].model_dump()
    app.run()
    app.sidebar.selectbox[0].select("हिन्दी").run()
    assert not app.exception
    assert app.session_state["case_file"].model_dump() == before
    assert len(app.chat_message) == 1
    transcribe.assert_not_called()
    model.assert_not_called()


def test_edited_transcript_uses_existing_intake_and_correction_safeguards_once(monkeypatch):
    app, audio, transcribe, model = prepare(monkeypatch)
    before = app.session_state["case_file"].model_dump()
    app.button(key="transcribe_audio").click().run()
    assert not app.exception
    assert app.session_state["case_file"].model_dump() == before
    assert len(app.chat_message) == 1  # Transcribing does not submit anything.
    model.assert_not_called()
    approved = "Correction: amount 2500; refund chahiye"
    app.text_area(key="voice_transcript").set_value(approved).run()
    app.run()
    assert transcribe.call_count == 1
    app.button(key="send_voice").click().run()
    assert not app.exception
    assert model.call_count == 1
    assert next(item for item in reversed(model.call_args.args[1]) if item["role"] == "user") == {
        "role": "user", "content": approved,
    }
    assert app.session_state["case_file"].amount_inr == 2500
    assert app.session_state["case_file"].company_or_seller == "Example Shop"
    assert app.session_state["case_file"].user_summary is None
    assert app.session_state["case_file"].narrative_review_required
    assert app.session_state["messages"][0]["content"] == "My earlier refund of 2000"
    app.run()
    assert app.button(key="send_voice").disabled
    assert app.button(key="transcribe_audio").disabled
    # Removing/reselecting the exact same audio also cannot submit it twice.
    audio[0] = None
    app.run()
    audio[0] = recording()
    app.run()
    assert app.button(key="transcribe_audio").disabled
    assert model.call_count == 1 and transcribe.call_count == 1


def test_failed_transcription_is_safe_and_only_retries_on_explicit_click(monkeypatch):
    app, _, transcribe, model = prepare(monkeypatch)
    transcribe.side_effect = TranscriptionError("timeout")
    before = app.session_state["case_file"].model_dump()
    app.button(key="transcribe_audio").click().run()
    assert not app.exception
    assert app.session_state["case_file"].model_dump() == before
    assert len(app.chat_message) == 1
    assert any("timed out" in item.value for item in app.error)
    app.run()
    assert transcribe.call_count == 1
    model.assert_not_called()
    app.button(key="transcribe_audio").click().run()
    assert transcribe.call_count == 2


def test_failed_intake_keeps_approved_text_without_automatic_resubmission(monkeypatch):
    app, _, transcribe, model = prepare(monkeypatch, transcript="Correction: 2500", intake_error=IntakeError("timeout"))
    before = app.session_state["case_file"].model_dump()
    app.button(key="transcribe_audio").click().run()
    app.button(key="send_voice").click().run()
    app.run()
    assert not app.exception
    assert app.session_state["case_file"].model_dump() == before
    assert len(app.session_state["messages"]) == 2
    assert app.session_state["messages"][-1]["content"] == "Correction: 2500"
    assert model.call_count == 1 and transcribe.call_count == 1
    assert app.button(key="send_voice").disabled


def test_blank_transcript_cannot_be_sent_and_new_recording_clears_old_text(monkeypatch):
    app, audio, transcribe, model = prepare(monkeypatch)
    app.button(key="transcribe_audio").click().run()
    app.text_area(key="voice_transcript").set_value("  ").run()
    assert app.button(key="send_voice").disabled
    audio[0] = recording(wav_bytes(seconds=0.2))
    app.run()
    assert not app.text_area
    assert not app.button(key="transcribe_audio").disabled
    assert transcribe.call_count == 1
    model.assert_not_called()


def test_invalid_audio_does_not_block_text_chat(monkeypatch):
    app, audio, transcribe, model = prepare(monkeypatch)
    audio[0] = recording(b"invalid WAV")
    app.run()
    assert any("Invalid" in item.value for item in app.error)
    app.chat_input[0].set_value("Correction: amount 2500").run()
    assert not app.exception
    assert model.call_count == 1
    assert app.session_state["case_file"].amount_inr == 2500
    transcribe.assert_not_called()


def test_new_case_clears_voice_case_messages_and_drafts(monkeypatch):
    app, audio, transcribe, model = prepare(monkeypatch)
    app.button(key="transcribe_audio").click().run()
    old_id = app.session_state["voice_recording_id"]
    app.session_state["voice_submitted_ids"].add(old_id)
    app.session_state["action_complaint_text"] = "Earlier manual draft"
    # The real audio widget gets a new identity and returns no old recording.
    audio[0] = None
    app.button(key="new_case").click().run()
    assert not app.exception
    assert app.session_state["case_generation"] == 1
    assert app.session_state["messages"] == []
    assert app.session_state["case_file"] == CaseFile()
    assert app.session_state["action_package"] is None
    assert app.session_state["legal_guidance"] is None
    assert app.session_state["voice_submitted_ids"] == set()
    assert "voice_transcript" not in app.session_state
    assert "action_complaint_text" not in app.session_state
    model.assert_not_called()
    assert transcribe.call_count == 1
