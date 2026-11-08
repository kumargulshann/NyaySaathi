import json
from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from nyaysaathi.intake import IntakeError
from nyaysaathi.settings import Settings


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_success_failure_and_reruns_preserve_session(monkeypatch):
    monkeypatch.setattr("nyaysaathi.settings.get_settings", lambda _: Settings("placeholder", "mock-model"))
    analyze = Mock(side_effect=[json.dumps({
        "scope": "in_scope", "reply_language": "hinglish",
        "changes": [{"field": "amount_inr", "value": "1200", "source_quote": "1200"}],
        "next_question": "Aapne kis seller se khareeda tha?",
    }), IntakeError("timeout")])
    monkeypatch.setattr("nyaysaathi.gemini.GeminiProvider.analyze", analyze)
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    assert not app.exception
    app.chat_input[0].set_value("Mera 1200 ka refund nahi aaya").run()
    assert not app.exception
    assert len(app.chat_message) == 2
    assert app.session_state["case_file"].amount_inr == 1200
    app.sidebar.selectbox[0].select("हिन्दी").run()
    app.run()
    assert analyze.call_count == 1  # No call on language changes or ordinary reruns.
    before = app.session_state["case_file"].model_dump()
    app.chat_input[0].set_value("मैंने ऑनलाइन खरीदा था").run()
    assert not app.exception
    assert app.session_state["case_file"].model_dump() == before
    assert len(app.chat_message) == 3  # Failed user turn is kept; no fake reply.
    assert app.session_state["last_error"] == "timeout"
    assert len(app.error) == 1
    assert analyze.call_count == 2


def test_app_launches_and_keeps_messages_without_configuration(monkeypatch):
    monkeypatch.setattr("nyaysaathi.settings.get_settings", lambda _: Settings())
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    assert not app.exception
    app.chat_input[0].set_value("Refund pending").run()
    assert not app.exception
    assert len(app.chat_message) == 1
    assert app.session_state["case_file"].case_status == "not_started"
    assert app.session_state["last_error"] == "missing_configuration"


def test_grounded_options_display_and_failure_clears_old_guidance(monkeypatch):
    """Offline synthetic output; no live response or external API is used."""
    from nyaysaathi.knowledge import load_knowledge

    source = next(item for item in load_knowledge() if item.source_id == "CPA-DEFECT")
    monkeypatch.setattr("nyaysaathi.settings.get_settings", lambda _: Settings("placeholder", "mock-model"))
    analyze = Mock(side_effect=[json.dumps({
        "scope": "in_scope", "reply_language": "hi",
        "guidance": [{"source_id": source.source_id, "explanation": source.guidance["hi"]}],
        "next_question": "आपने ऑर्डर किस तारीख को दिया था?",
    }), IntakeError("timeout")])
    monkeypatch.setattr("nyaysaathi.gemini.GeminiProvider.analyze", analyze)
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    app.chat_input[0].set_value("My headphones arrived damaged").run()
    assert not app.exception
    assert app.session_state["legal_guidance"].status == "grounded"
    assert any(source.source_url in element.value for element in app.markdown)
    assert any(source.guidance["hi"] in element.value for element in app.markdown)
    before = app.session_state["case_file"].model_dump()
    app.chat_input[0].set_value("What can I do about the damage?").run()
    assert not app.exception
    assert app.session_state["legal_guidance"] is None
    assert app.session_state["case_file"].model_dump() == before
    assert not any(source.source_url in element.value for element in app.markdown)
    assert analyze.call_count == 2
