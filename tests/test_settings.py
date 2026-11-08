from nyaysaathi.settings import get_settings


def test_transcription_configuration_precedence_and_default(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_TRANSCRIPTION_MODEL", raising=False)
    path = tmp_path / ".env"
    assert get_settings(env_file=path).gemini_transcription_model == "gemini-3.5-transcribe"
    path.write_text("GEMINI_TRANSCRIPTION_MODEL=file-asr\n", encoding="utf-8")
    assert get_settings(env_file=path).gemini_transcription_model == "file-asr"
    monkeypatch.setenv("GEMINI_TRANSCRIPTION_MODEL", "env-asr")
    assert get_settings(env_file=path).gemini_transcription_model == "env-asr"
    assert get_settings({"GEMINI_TRANSCRIPTION_MODEL": "secret-asr"}, path).gemini_transcription_model == "secret-asr"
    assert get_settings({"GEMINI_TRANSCRIPTION_MODEL": " "}, path).gemini_transcription_model == "env-asr"


def test_absent_configuration_is_safe(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    settings = get_settings(env_file=tmp_path / "missing.env")
    assert settings.gemini_api_key is None
    assert settings.gemini_model is None


def test_env_file_is_loaded_without_exporting_secrets(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    path = tmp_path / ".env"
    path.write_text("GEMINI_API_KEY=file-placeholder\nGEMINI_MODEL=file-model\n", encoding="utf-8")
    settings = get_settings(env_file=path)
    assert settings.gemini_api_key == "file-placeholder"
    assert settings.gemini_model == "file-model"
    assert "file-placeholder" not in repr(settings)
    import os
    assert "GEMINI_API_KEY" not in os.environ


def test_configuration_precedence_and_blank_fallback(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    path.write_text("GEMINI_API_KEY=file-placeholder\nGEMINI_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "environment-placeholder")
    monkeypatch.setenv("GEMINI_MODEL", "environment-model")
    settings = get_settings({"GEMINI_API_KEY": "secrets-placeholder", "GEMINI_MODEL": " "}, path)
    assert settings.gemini_api_key == "secrets-placeholder"
    assert settings.gemini_model == "environment-model"
    monkeypatch.setenv("GEMINI_MODEL", "")
    assert get_settings(env_file=path).gemini_model == "file-model"
