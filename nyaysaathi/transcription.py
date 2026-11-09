"""Bounded, in-memory speech transcription; no Streamlit, storage or intake logic.

Uses the documented generateContent transcription endpoint supported by google-genai
2.34: https://ai.google.dev/gemini-api/docs/generate-content/transcribe
Only PCM WAV is accepted locally so content and duration can be checked without
native decoders. The provider supports more formats; this service deliberately
offers a smaller, verifiable input contract.
"""

from array import array
from hashlib import sha256
from io import BytesIO
import logging
import math
import re
import struct
import sys
import wave

from google import genai
from google.genai import errors, types
from httpx import TimeoutException
from pydantic import BaseModel, ConfigDict, Field

from nyaysaathi.settings import Settings


MAX_AUDIO_BYTES = 1_999_999
MAX_AUDIO_SECONDS = 60
WAV_MIMES = frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"})
LOGGER = logging.getLogger(__name__)
UNCLEAR = re.compile(
    r"\[(?:inaudible|unintelligible|unclear|silence|no speech)[^\]]*\]|"
    r"^\s*(?:inaudible|unintelligible|no (?:intelligible )?speech(?: detected)?|silence)\s*[.!]?\s*$|"
    r"\[(?:अस्पष्ट|सुनाई नहीं)[^\]]*\]",
    re.IGNORECASE,
)


class TranscriptionError(Exception):
    """Safe code only: provider errors may contain credentials or audio/transcripts."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class AudioInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    mime_type: str = "audio/wav"
    duration_seconds: float
    recording_id: str
    rms_level: float
    peak_level: float


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    transcript: str = Field(min_length=1, max_length=12_000, repr=False)
    model: str
    audio: AudioInfo
    review_required: bool = True


def validate_audio(audio_bytes: bytes, mime_type: str) -> AudioInfo:
    """Validate declared MIME, RIFF/WAVE structure, complete PCM frames and duration."""
    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise TranscriptionError("empty_audio")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise TranscriptionError("audio_too_large")
    if not isinstance(mime_type, str) or mime_type.lower().strip() not in WAV_MIMES:
        raise TranscriptionError("unsupported_audio")
    try:
        if (audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE"
                or struct.unpack_from("<I", audio_bytes, 4)[0] + 8 != len(audio_bytes)):
            raise ValueError("Invalid WAV container")
        with wave.open(BytesIO(audio_bytes), "rb") as audio:
            frames, rate = audio.getnframes(), audio.getframerate()
            channels, width = audio.getnchannels(), audio.getsampwidth()
            if (audio.getcomptype() != "NONE" or width != 2 or channels not in (1, 2)
                    or not 8_000 <= rate <= 48_000 or frames <= 0):
                raise ValueError("Only complete 16-bit PCM WAV is supported")
            duration = frames / rate
            if duration > MAX_AUDIO_SECONDS:
                raise TranscriptionError("audio_too_long")
            # Read one extra frame to expose a malformed partial final frame
            # instead of silently truncating it via getnframes()' integer division.
            pcm = audio.readframes(frames + 1)
            if len(pcm) != frames * channels * width:
                raise ValueError("Truncated PCM data")
            if not any(pcm):
                raise TranscriptionError("silent_audio")
            samples = array("h")
            samples.frombytes(pcm)
            if sys.byteorder != "little":
                samples.byteswap()
            rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768
            peak = max(abs(value) for value in samples) / 32768
    except TranscriptionError:
        raise
    except (wave.Error, EOFError, ValueError, struct.error, OSError):
        raise TranscriptionError("invalid_audio") from None
    return AudioInfo(duration_seconds=duration, recording_id=sha256(audio_bytes).hexdigest(),
                     rms_level=rms, peak_level=peak)


def extract_transcript(response: types.GenerateContentResponse) -> str:
    """Read documented Part.text and Part.audio_transcription.text, once each.

    google-genai 2.34's response.text convenience accessor ignores structured
    transcription parts. Prefer complete plain text when supplied; otherwise
    join structured speaker/segment text from the first completed candidate.
    Never join both representations and duplicate the transcript.
    """
    candidates = response.candidates or []
    if not candidates or candidates[0].finish_reason != types.FinishReason.STOP:
        raise TranscriptionError("invalid_output")
    parts = candidates[0].content.parts if candidates[0].content else []
    parts = [part for part in (parts or []) if not part.thought]
    plain = "".join(part.text for part in parts if isinstance(part.text, str)).strip()
    segments = [part.audio_transcription.text.strip() for part in parts
                if part.audio_transcription and isinstance(part.audio_transcription.text, str)
                and part.audio_transcription.text.strip()]
    transcript = plain or " ".join(segments)
    if not transcript:
        # A completed but empty provider response does not prove absent speech.
        # Log shape/counts only: no audio, text, hashes, keys or raw exceptions.
        LOGGER.warning("transcription_empty_output candidates=%d parts=%d structured_parts=%d",
                       len(candidates), len(parts), sum(part.audio_transcription is not None for part in parts))
        raise TranscriptionError("empty_transcription")
    if UNCLEAR.search(transcript):
        raise TranscriptionError("unintelligible_audio")
    if len(transcript) > 12_000:
        raise TranscriptionError("invalid_output")
    return transcript


def transcribe_audio(audio_bytes: bytes, mime_type: str, settings: Settings) -> TranscriptionResult:
    """One server-side SDK request; no retries, files API uploads or local audio files.

    Verbatim transcription retains spoken corrections. Automatic language detection
    preserves English/Hindi/code-switching rather than requesting translation.
    This ASR endpoint receives audio only, never case context or a legal prompt.
    """
    audio = validate_audio(audio_bytes, mime_type)
    LOGGER.info("transcription_audio_validated bytes=%d seconds=%.3f rms=%.6f peak=%.6f",
                len(audio_bytes), audio.duration_seconds, audio.rms_level, audio.peak_level)
    if not settings.gemini_api_key or not settings.gemini_transcription_model.strip():
        raise TranscriptionError("missing_configuration")
    try:
        with genai.Client(
            api_key=settings.gemini_api_key, vertexai=False,
            http_options=types.HttpOptions(
                timeout=45_000, retry_options=types.HttpRetryOptions(attempts=1),
            ),
        ) as client:
            response = client.models.generate_content(
                model=settings.gemini_transcription_model,
                contents=[types.Part.from_bytes(data=audio_bytes, mime_type=audio.mime_type)],
                config=types.GenerateContentConfig(
                    audio_transcription_config=types.AudioTranscriptionConfig(
                        mode="VERBATIM", language_codes=[],
                    ),
                    max_output_tokens=4096,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            transcript = extract_transcript(response)
            return TranscriptionResult(
                transcript=transcript, model=settings.gemini_transcription_model, audio=audio,
            )
    except TranscriptionError:
        raise
    except (TimeoutError, TimeoutException):
        raise TranscriptionError("timeout") from None
    except errors.APIError as error:
        code = "rate_limit" if error.code == 429 else "model_error"
        if error.code in (408, 504):
            code = "timeout"
        raise TranscriptionError(code) from None
    except Exception:
        raise TranscriptionError("model_error") from None
