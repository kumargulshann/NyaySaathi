"""Vercel/local FastAPI entrypoint. No sessions, case storage or new AI logic."""
from typing import Annotated
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from backend.schemas import (
    ChatRequest, ChatResponse, Citation, GuidanceResponse, HealthResponse,
    PackageContent, PackageRequest, PackageResponse, SafeError,
)
from nyaysaathi.action_package import assess_readiness, case_fingerprint, generate_package
from nyaysaathi.gemini import GeminiProvider
from nyaysaathi.intake import IntakeError, run_turn
from nyaysaathi.knowledge import detect_safety
from nyaysaathi.settings import Settings, get_settings
from nyaysaathi.transcription import MAX_AUDIO_BYTES, TranscriptionError, TranscriptionResult, transcribe_audio


WEB = Path(__file__).resolve().parent.parent / "web"
ERRORS = {
    "missing_configuration": "Gemini is not configured on the server. Check the API key and model settings.",
    "rate_limit": "The provider quota or rate limit was reached. Wait and check your quota before trying again.",
    "timeout": "The provider timed out. No automatic retry was made.",
    "model_error": "The provider could not complete this request. Check model access and connection.",
    "invalid_output": "The response could not be safely validated. Your previous case is unchanged.",
    "empty_audio": "The recording is empty. Record again or use text chat.",
    "audio_too_large": "Audio must be below 2 MB. Record a shorter message.",
    "audio_too_long": "Audio must be at most 60 seconds long.",
    "unsupported_audio": "Only 16-bit PCM WAV audio is accepted.",
    "invalid_audio": "The WAV recording is invalid or incomplete.",
    "silent_audio": "The recording contains only silence. Check your microphone and listen to the preview before recording again.",
    "empty_transcription": "The transcription provider returned no transcript. This does not confirm silence. Check the preview and try again later; nothing was sent to intake.",
    "unintelligible_audio": "No usable speech transcript was returned. Record again or type your message.",
    "invalid_request": "The request is invalid or exceeds the case/conversation limits.",
    "request_too_large": "The request exceeds the size limit. Shorten the recording or conversation.",
    "internal_error": "The request could not be completed. Your existing browser data is kept.",
}


def safe_error(code: str) -> SafeError:
    code = code if code in ERRORS else "internal_error"
    return SafeError(code=code, message=ERRORS[code])


def error_response(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": safe_error(code).model_dump()}, status_code=status)


class RequestLimits:
    """Bound body bytes before parsing; WAV stays in memory, never disk-spooled."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def secured_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"microphone=(self)"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"),
                ]
            await send(message)
        if scope["method"] == "POST" and scope["path"].startswith("/api/"):
            maximum = MAX_AUDIO_BYTES if scope["path"] == "/api/transcribe" else 160_000
            headers = dict(scope.get("headers", []))
            try:
                claimed = int(headers.get(b"content-length", b"0"))
                if claimed < 0:
                    raise ValueError
            except ValueError:
                return await error_response("invalid_request", 400)(scope, receive, secured_send)
            if claimed > maximum:
                return await error_response("request_too_large", 413)(scope, receive, secured_send)
            body = bytearray()
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    return
                body.extend(event.get("body", b""))
                if len(body) > maximum:
                    return await error_response("request_too_large", 413)(scope, receive, secured_send)
                if not event.get("more_body", False):
                    break
            async def buffered_receive():
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await self.app(scope, buffered_receive, secured_send)
        await self.app(scope, receive, secured_send)


app = FastAPI(title="NyaySaathi AI", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(RequestLimits)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    # Pydantic's default error includes rejected input; never reflect case text/keys.
    return error_response("invalid_request", 422)


@app.exception_handler(HTTPException)
async def http_error(request: Request, error: HTTPException):
    return error_response("invalid_request", error.status_code)


def server_settings() -> Settings:
    try:
        return get_settings()  # Environment and local .env; no Streamlit dependency.
    except OSError:
        return Settings()


def blocked_from_context(case, history) -> bool:
    # Reuse the existing safety classifier. No client guidance/status flags accepted.
    text = " ".join(item.content for item in history if item.role == "user")
    return detect_safety(text) in ("out_of_scope", "urgent_notice", "threat_or_crime")


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, settings: Annotated[Settings, Depends(server_settings)]):
    messages = [item.model_dump() for item in payload.history]
    messages.append({"role": "user", "content": payload.message})
    try:
        turn = run_turn(payload.case, messages, payload.language, GeminiProvider(settings))
        guidance = turn.guidance
        citations = [Citation(
            source_id=item.source_id, title=item.source_title, url=item.source_url,
            explanation=item.guidance[guidance.language], next_step=item.next_step[guidance.language],
            limitation=item.limitation[guidance.language], location=item.provision_or_location,
            date_checked=item.date_checked.isoformat(),
        ) for item in guidance.entries]
        return ChatResponse(
            case=turn.case, reply=turn.reply,
            guidance=GuidanceResponse(status=guidance.status, language=guidance.language,
                                      message=guidance.message, citations=citations),
            missing_information=turn.case.unanswered_questions,
            readiness=assess_readiness(turn.case, out_of_scope=guidance.status in (
                "out_of_scope", "urgent_notice", "threat_or_crime",
            )), fingerprint=case_fingerprint(turn.case),
            error=safe_error(turn.intake_error) if turn.intake_error else None,
        )
    except IntakeError as error:
        status = {"rate_limit": 429, "timeout": 504, "invalid_output": 502}.get(error.code, 503)
        return error_response(error.code, status)
    except Exception:
        return error_response("internal_error", 500)


@app.post("/api/transcribe", response_model=TranscriptionResult)
def transcribe(
    request: Request,
    settings: Annotated[Settings, Depends(server_settings)],
    audio: Annotated[bytes, Body(media_type="audio/wav")] = b"",
):
    try:
        return transcribe_audio(audio, request.headers.get("content-type", ""), settings)
    except TranscriptionError as error:
        status = {"missing_configuration": 503, "rate_limit": 429, "timeout": 504,
                  "model_error": 502, "invalid_output": 502, "empty_transcription": 502}.get(error.code, 400)
        return error_response(error.code, status)
    except Exception:
        return error_response("internal_error", 500)


@app.post("/api/action-package", response_model=PackageResponse)
def action_package(payload: PackageRequest):
    try:
        blocked = blocked_from_context(payload.case, payload.history)
        readiness = assess_readiness(payload.case, out_of_scope=blocked)
        if readiness.status == "out_of_scope" or not readiness.provisional_allowed or (
            readiness.status != "ready" and not payload.provisional
        ):
            return PackageResponse(readiness=readiness)
        package = generate_package(payload.case, payload.language, provisional=payload.provisional, out_of_scope=blocked)
        return PackageResponse(readiness=package.readiness, package=PackageContent(
            complaint=package.complaint, summary=package.summary, checklist=package.checklist,
            fingerprint=package.fingerprint, language=package.language,
        ))
    except (ValueError, TypeError):
        return error_response("invalid_request", 422)
    except Exception:
        return error_response("internal_error", 500)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
