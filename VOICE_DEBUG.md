# Phase 11 — production voice parsing failure

Date: 9 November 2026 (Asia/Calcutta).

## Evidence and failure classification

The user recorded approximately 16 seconds in Chrome/Windows and saw a playable
preview, then the API's no-usable-speech error. That preview alone did not establish
server-side audio quality. Subsequent user-supplied Vercel logs established that:

1. The production request reached `/api/transcribe` and passed validation: the
   application invoked Gemini only after validation succeeded.
2. The configured transcription model's Generate Content request returned HTTP 200.
3. The SDK warned that the response had non-text `audio_transcription` parts and
   that its `.text` accessor returned only ordinary text parts.
4. Our service read only `response.text`, treating its empty result as no speech.

**Primary failure: E, response parsing.** The code ignored a supported response
representation. This is not evidence of an upload failure, timeout, unavailable
model or Gemini exception. Logs alone do not reveal the actual words or prove
the structured text was nonempty; the original audio/response was not retained.
That boundary is preserved rather than claiming a successful recognition test.

The installed SDK is `google-genai` 2.34.0. Its `Part.audio_transcription` is a
`types.Transcription` object. The [official API reference](https://ai.google.dev/api/generate-content?hl=en)
documents `audioTranscription.text`; the [Generate Content transcription guide](https://ai.google.dev/gemini-api/docs/generate-content/transcribe?hl=en)
also describes transcription annotations in candidate parts. The SDK's `.text`
implementation explicitly ignores non-text parts, reproduced offline with typed
responses parsed from the documented camel-case wire fields.

Generate Content remains documented for this model. The current payload is inline
`audio/wav`, verbatim transcription with automatic language detection, one bounded
45-second request and no retries. There is no need to switch to Interactions,
change models or upgrade the SDK to read a field it already supports. The AFC
"max remote calls: 10" log was a limit, not proof of ten requests. Automatic
function calling is now explicitly disabled for transcription, which uses no tools.

## Minimal fix and error distinctions

- Read completed candidate parts directly. Use plain text when supplied, otherwise
  collect ordered `audio_transcription.text` segments. Ignore thought parts and
  avoid duplicating a transcript present in both representations.
- Keep finish-reason and output-length checks. Blocked/truncated output remains
  invalid; do not display an incomplete transcript as successful.
- `silent_audio` (400): the validated PCM sample data is all zero, before any
  provider call. The WAV header itself is never mistaken for a speech signal.
- `unintelligible_audio` (400): output explicitly marks unclear/no speech.
- `empty_transcription` (502): a completed provider response has neither usable
  text representation. Empty provider output is not presented as proof of silence.
- Transport, quota, configuration and malformed-output errors remain separately
  handled. No provider exception text reaches the browser.

Validated audio metadata now includes normalized RMS and peak sample levels.
Diagnostics contain byte count, duration and these aggregate signal levels, or
empty-output candidate/part counts. They contain **no audio, transcript text,
credentials, recording hash or raw provider response**. Vercel's existing request
IDs correlate its log lines; no additional session/store is introduced. Signal
amplitude does not prove intelligible speech, so quiet nonzero input is not
arbitrarily rejected or automatically amplified.

The frontend continues to show a nonempty returned transcript in its editable
field. It sends nothing to intake until explicit approval. English/Hindi/Hinglish,
recording limits, citation validation, case corrections and deterministic documents
are preserved. Streamlit's error catalog understands the two distinct new codes.

## Offline evidence and live-test boundary

Regression tests cover the exact structured response shape that previously failed,
plain/structured overlap, segment order, English/Hindi/Hinglish strings, missing,
silent, blocked and malformed output, timeouts/provider failures, signal amplitude,
safe logging, API response delivery and browser error/edit/approval behavior.
Synthetic WAV signals test validation/encoding only, not speech recognition.

The user confirmed that the original recording exists only in the browser, not as
an accessible file. Therefore **no new live Gemini request** is made for this fix.
The at-most-one Phase 11 transcription test remains for a genuine fresh recording;
it must not be replaced with synthetic speech or a model-output mock.

## Exact manual check after the new deployment is ready

1. Reload https://nyay-saathi-psi.vercel.app/ in Chrome to load the new JavaScript.
2. Record 5–10 seconds of genuine fictional speech, for example: "I ordered
   headphones for 2999 rupees. They arrived damaged."
3. Stop and play the preview. Confirm your voice is audible; don't infer this
   from the duration or player alone.
4. Click **Transcribe audio once**. Expect an editable transcript. Correct a word
   to confirm editing; there is no need to click Send for this transcription test.
5. If it fails, do not repeatedly retry. Share only the safe error code/HTTP status
   and the `transcription_audio_validated` / `transcription_empty_output` metadata
   from Vercel Logs. Do not share keys, raw audio or transcript text.

Offline verification passed: **220 Python tests**, **8 JavaScript tests**, syntax
and dependency checks. The existing upstream TestClient/httpx deprecation warning
remains non-failing. Deployment status is verified against the actual fix commit
and production's distinct silent-audio response, without calling Gemini.
