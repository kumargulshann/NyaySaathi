"""Synthetic WAV containers and mocked ASR outputs; NOT speech-recognition evidence."""

from io import BytesIO
from unittest.mock import Mock
import struct
import wave

from google.genai import errors, types
from httpx import ReadTimeout
import pytest

from nyaysaathi.settings import Settings
from nyaysaathi.transcription import (
    MAX_AUDIO_BYTES, TranscriptionError, extract_transcript, transcribe_audio, validate_audio,
)


def wav_bytes(seconds=0.1, rate=16000, silent=False):
    stream = BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        # Alternating non-speech PCM values exercise validation only.
        sample = b"\x00\x00" if silent else b"\x10\x00"
        audio.writeframes(sample * int(seconds * rate))
    return stream.getvalue()


def response(text="My refund is pending.", finish="STOP"):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(parts=[types.Part(text=text)]), finish_reason=finish,
    )])


def mock_client(monkeypatch, *, output=None, error=None):
    client = Mock()
    client.models.generate_content.return_value = output or response()
    client.models.generate_content.side_effect = error
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=client)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("google.genai.Client", factory)
    return factory, client


def test_valid_wav_and_normalized_mime():
    audio = wav_bytes()
    info = validate_audio(audio, "audio/x-wav")
    assert info.mime_type == "audio/wav"
    assert info.duration_seconds == 0.1
    assert info == validate_audio(audio, "audio/wav")
    assert len(info.recording_id) == 64
    assert info.rms_level == pytest.approx(16 / 32768)
    assert info.peak_level == pytest.approx(16 / 32768)


@pytest.mark.parametrize("text", [
    "My headphones cost 2999 rupees and arrived damaged.",
    "मैंने फ्लिपकार्ट से 4500 रुपये का सामान खरीदा था।",
    "Maine Flipkart se 4500 ka product liya, delivery nahi hui.",
])
def test_language_is_preserved_and_one_documented_sdk_call_is_used(monkeypatch, text):
    factory, client = mock_client(monkeypatch, output=response(text))
    data = wav_bytes()
    result = transcribe_audio(data, "audio/wav", Settings("test-key", "intake-model", "asr-model"))
    assert result.transcript == text
    assert result.model == "asr-model" and result.review_required
    assert text not in repr(result)
    client.models.generate_content.assert_called_once()
    arguments = client.models.generate_content.call_args.kwargs
    assert arguments["model"] == "asr-model"
    assert arguments["contents"][0].inline_data.data == data
    assert arguments["contents"][0].inline_data.mime_type == "audio/wav"
    config = arguments["config"]
    assert config.audio_transcription_config.mode == "VERBATIM"
    assert config.audio_transcription_config.language_codes == []
    assert config.system_instruction is None
    assert config.automatic_function_calling.disable is True
    assert factory.call_args.kwargs["http_options"].timeout == 45000
    assert factory.call_args.kwargs["http_options"].retry_options.attempts == 1
    client.files.upload.assert_not_called()
    client.files.delete.assert_not_called()  # Inline bytes create no provider File resources.
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("data,mime,code", [
    (b"", "audio/wav", "empty_audio"),
    (b"x" * (MAX_AUDIO_BYTES + 1), "audio/wav", "audio_too_large"),
    (wav_bytes(), "audio/mp3", "unsupported_audio"),
    (b"this is not audio", "audio/wav", "invalid_audio"),
    (wav_bytes()[:-2], "audio/wav", "invalid_audio"),
    (wav_bytes() + b"extra payload", "audio/wav", "invalid_audio"),
    (wav_bytes(seconds=61, rate=8000), "audio/wav", "audio_too_long"),
    (wav_bytes(silent=True), "audio/wav", "silent_audio"),
])
def test_invalid_audio_never_constructs_a_client(monkeypatch, data, mime, code):
    client = Mock()
    monkeypatch.setattr("google.genai.Client", client)
    with pytest.raises(TranscriptionError) as caught:
        transcribe_audio(data, mime, Settings("test-key"))
    assert caught.value.code == code
    client.assert_not_called()


def test_sixty_second_boundary_is_accepted():
    assert validate_audio(wav_bytes(seconds=60), "audio/wav").duration_seconds == 60


def test_partial_pcm_frame_is_rejected_even_with_matching_container_lengths():
    data = bytearray(wav_bytes()[:-1])
    struct.pack_into("<I", data, 4, len(data) - 8)
    struct.pack_into("<I", data, 40, len(data) - 44)
    with pytest.raises(TranscriptionError, match="invalid_audio"):
        validate_audio(bytes(data), "audio/wav")


def test_pcm_amplitude_is_measured_from_signed_samples_not_header_bytes():
    stream=BytesIO()
    with wave.open(stream,"wb") as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes(struct.pack("<5h",0,8192,-8192,16384,-16384)*320)
    info=validate_audio(stream.getvalue(),"audio/wav")
    assert info.duration_seconds==0.1
    assert info.peak_level==pytest.approx(0.5)
    assert info.rms_level==pytest.approx(0.125**0.5)


def test_missing_key_never_constructs_client(monkeypatch):
    client = Mock()
    monkeypatch.setattr("google.genai.Client", client)
    with pytest.raises(TranscriptionError, match="missing_configuration"):
        transcribe_audio(wav_bytes(), "audio/wav", Settings())
    client.assert_not_called()


@pytest.mark.parametrize("error,code", [
    (TimeoutError("private payload"), "timeout"),
    (ReadTimeout("private payload"), "timeout"),
    (errors.APIError(429, {"message": "private payload"}), "rate_limit"),
    (errors.APIError(504, {"message": "private payload"}), "timeout"),
    (errors.APIError(404, {"message": "private payload"}), "model_error"),
    (RuntimeError("private payload"), "model_error"),
])
def test_provider_failures_are_redacted_and_not_retried(monkeypatch, error, code):
    _, client = mock_client(monkeypatch, error=error)
    with pytest.raises(TranscriptionError) as caught:
        transcribe_audio(wav_bytes(), "audio/wav", Settings("test-key"))
    assert str(caught.value) == code
    assert "private" not in str(caught.value)
    client.models.generate_content.assert_called_once()


@pytest.mark.parametrize("text", ["[inaudible]", "[अस्पष्ट]", "No speech detected."])
def test_unusable_transcript_is_an_explicit_error(monkeypatch, text):
    mock_client(monkeypatch, output=response(text))
    with pytest.raises(TranscriptionError, match="unintelligible_audio"):
        transcribe_audio(wav_bytes(), "audio/wav", Settings("test-key"))


@pytest.mark.parametrize("output", [
    types.GenerateContentResponse(), response("Incomplete", "MAX_TOKENS"), response("Blocked", "SAFETY"),
])
def test_missing_blocked_and_truncated_outputs_are_not_accepted(monkeypatch, output):
    mock_client(monkeypatch, output=output)
    with pytest.raises(TranscriptionError, match="invalid_output"):
        transcribe_audio(wav_bytes(), "audio/wav", Settings("test-key"))


@pytest.mark.parametrize("text", [
    "My headphones worth 2999 arrived damaged.",
    "मेरा सामान नहीं पहुँचा, मुझे रिफंड चाहिए।",
    "Maine Flipkart se ₹4500 ka product liya tha.",
])
def test_production_structured_part_is_not_misclassified_as_no_speech(monkeypatch, text):
    # Actual documented wire field names, parsed by the installed SDK types.
    output = types.GenerateContentResponse.model_validate({"candidates":[{
        "finishReason":"STOP", "content":{"role":"model","parts":[
            {"audioTranscription":{"text":text,"languageCode":"en-IN"}}
        ]}
    }]})
    assert output.text is None  # This is why the previous production parser failed.
    _, client = mock_client(monkeypatch, output=output)
    result = transcribe_audio(wav_bytes(), "audio/wav", Settings("offline-key"))
    assert result.transcript == text and result.review_required
    client.models.generate_content.assert_called_once()


def test_segment_order_thought_exclusion_and_duplicate_representations():
    output = types.GenerateContentResponse(candidates=[types.Candidate(finish_reason="STOP",
        content=types.Content(parts=[
            types.Part(text="Internal thought",thought=True),
            types.Part(audio_transcription=types.Transcription(text="First segment.")),
            types.Part(audio_transcription=types.Transcription(text="दूसरा हिस्सा।")),
        ]))])
    assert extract_transcript(output) == "First segment. दूसरा हिस्सा।"
    output.candidates[0].content.parts.append(types.Part(text="First segment. दूसरा हिस्सा।"))
    assert extract_transcript(output) == "First segment. दूसरा हिस्सा।"


@pytest.mark.parametrize("parts", [
    [], [types.Part(text="")], [types.Part(text="   ")],
    [types.Part(audio_transcription=types.Transcription(text=""))],
])
def test_empty_completed_provider_output_is_not_proof_of_no_speech(monkeypatch, parts):
    output=types.GenerateContentResponse(candidates=[types.Candidate(finish_reason="STOP",content=types.Content(parts=parts))])
    mock_client(monkeypatch,output=output)
    with pytest.raises(TranscriptionError,match="empty_transcription"):
        transcribe_audio(wav_bytes(),"audio/wav",Settings("offline-key"))


def test_diagnostics_contain_signal_metrics_but_no_content_or_credentials(monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO,logger="nyaysaathi.transcription")
    text="Private synthetic transcript marker"
    mock_client(monkeypatch,output=response(text))
    audio=wav_bytes()
    result=transcribe_audio(audio,"audio/wav",Settings("private-offline-key-marker"))
    assert "transcription_audio_validated" in caplog.text
    assert "rms=" in caplog.text and "peak=" in caplog.text
    for hidden in (text,"private-offline-key-marker",result.audio.recording_id,audio.hex()):
        assert hidden not in caplog.text
