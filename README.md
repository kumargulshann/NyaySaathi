# NyaySaathi AI — Phase 10

Multilingual case intake for Indian consumer refunds, defective products,
non-delivery, and related service complaints. **Legal information assistance
only; not a substitute for a qualified lawyer.** Dynamic intake and source-grounded
consumer information use a small, checked local knowledge base. No definitive legal
advice, outcome guarantees, or lawyer-issued legal notices are generated. The
Action Package creates editable consumer preparation documents without model calls.

Publication/verification instructions and the completed-intake 502 fix are in
[DEPLOYMENT.md](DEPLOYMENT.md). Authorized source repository:
[kumargulshann/NyaySaathi](https://github.com/kumargulshann/NyaySaathi).
The actual HTTPS deployment results and remaining limits are linked below.
Earlier exposed example credentials require revocation, not just removal; the
user confirmed rotation during Phase 10. Never commit real keys.

**Verified public prototype:** [Open NyaySaathi AI](https://nyay-saathi-psi.vercel.app/).
The deployed endpoints and two real fictional Gemini cases were checked on
9 November 2026. See [DEPLOYMENT_VERIFICATION.md](DEPLOYMENT_VERIFICATION.md)
for results, the refund-intent inference requiring review, and voice limitations.
Share as a limited prototype; live voice recognition remains unverified.

## Web application: FastAPI + vanilla browser frontend

The browser version is a second interface over the **same** `nyaysaathi` services.
`backend/main.py` exposes the stateless API; `web/` contains HTML, CSS and native
JavaScript modules. The existing Streamlit `app.py` and intelligence modules are
unchanged in Phase 9. There is no frontend framework, Node build, database or
additional AI pipeline.

### Run the web version locally (PowerShell)

Use the existing environment and `.env`; do not overwrite a configured key:

```powershell
cd E:\KukuProblem2
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000/**. For a fresh checkout, create `.venv` and copy
`.env.example` to `.env` using the setup below first. Python 3.13 is the tested
environment and configured Vercel runtime. No npm install/build is needed.

The web server reads server-side environment variables or the local project
`.env`: `GEMINI_API_KEY`, `GEMINI_MODEL`, and optionally
`GEMINI_TRANSCRIPTION_MODEL` (default `gemini-3.5-transcribe`). Environment values
take priority over `.env`. Unlike Streamlit, this entrypoint does **not** read
`.streamlit/secrets.toml`. The page and local document templates work without a
key; chat/transcription show a safe configuration error when their settings are
missing. Health checks do not contact Gemini or prove model connectivity.

### Browser workflow

Choose English/Hindi interface labels; describe a fictional grievance by text or
voice. Hinglish text/speech is also supported by the configured services. An
example button fills the message box without sending. After each turn, review
the Case File, missing details, checked legal explanations, source links, next
steps and limitations. Interface language changes do not translate existing
user statements or silently modify facts/documents.

Voice uses `getUserMedia` and `AudioWorklet`, not renamed WebM recordings. It
mixes captured channels to mono, resamples the actual device rate (including
44.1/48 kHz) with a windowed-sinc low-pass filter, and encodes a genuine 16 kHz
16-bit PCM RIFF/WAV file. Recording stops at 60 seconds; the largest resulting
WAV is 1,920,044 bytes, below the backend's 2 MB limit. Tracks and audio-context
resources are released on stop, failure or page exit. Preview the recording,
explicitly transcribe, edit the transcript, then explicitly send the approved text.
No microphone access, transcription or intake request occurs on page load.

Audio capture requires a recent browser with AudioWorklet and microphone access
on localhost or HTTPS. Permission denial or unsupported APIs leave text chat
usable. A recording/transcript can be sent once per case. Pending operations
disable duplicate actions. A failed request is not retried automatically; review
the retained message before deliberately resending via text.

Generate the Action Package only when requested. Select the provisional checkbox
if details are missing. The API independently checks readiness and safety; browser
status flags cannot authorize generation. Complaint and NCH text are editable;
TXT downloads use the current editor values and a UTF-8 BOM. Case/language changes
show an outdated warning, retaining edits until **Regenerate package (replaces
edits)** is clicked. Case corrections invalidate stale narratives just as in
Streamlit. Add fresh neutral descriptions in the editors where required.

**Start new case** clears conversation, case, audio preview/transcript and document
edits. State is held only in page memory: refresh/close clears it, and no localStorage,
IndexedDB, cookie session or server conversation database is used. Download work
before clearing or closing. This differs from Streamlit's server session state.

### API contracts

| Endpoint | Request | Response |
| --- | --- | --- |
| `GET /api/health` | None | Safe application status; no credential/configuration values |
| `POST /api/chat` | JSON: `message`, `language` (`en`/`hi`/`hinglish`), `case`, `history` | Updated case, reply, checked guidance/citations, missing information, readiness, fingerprint and optional safe error |
| `POST /api/transcribe` | **Raw PCM WAV bytes**, `Content-Type: audio/wav` | Structured transcript/model/audio metadata and review-required flag; no case update |
| `POST /api/action-package` | JSON: `case`, `language` (`en`/`hi`), `provisional`, optional `history` | Readiness and deterministic package, or `package: null` if blocked/incomplete |

JSON requests use Pydantic with extra fields forbidden. `case` is the existing
CaseFile schema, limited to 24 KB serialized. History has at most 12 user/assistant
messages and 24,000 characters total; the new message is separate, up to 12,000
characters. The browser sends bounded recent context. HTTP bodies are capped
before parsing: 160,000 bytes for JSON and 1,999,999 bytes for WAV, even without
Content-Length. The audio route uses raw bytes to avoid multipart disk spooling;
`python-multipart` is installed as requested, but multipart file forms are not
this endpoint's contract. No audio file is written locally or uploaded through
Gemini's Files API. Existing WAV/content/duration validation is reused.

Client-supplied citations, source records, legal verified flags and system messages
are rejected. Legal explanations/URLs come only from the existing server retrieval
and claim validator. Action-package scope checks reuse the existing safety logic
and supplied user context. Case facts themselves remain client-supplied allegations,
not independently verified or cryptographically authenticated history.

Quota errors use 429, provider timeouts 504, unavailable configuration/provider
failures 503/502, invalid requests 422 and oversized bodies 413. Error responses
have `{ "error": { "code": "...", "message": "..." } }` without rejected input
or provider exception text. A successful chat can still include a safe intake
validation error while retaining the previous case and independently checked
guidance, consistent with the production pipeline. No application retries occur.
SDK calls retain their 45-second timeout; the browser stops waiting after 55 seconds.

### Vercel deployment configuration

Configuration follows the current [Vercel FastAPI documentation](https://vercel.com/docs/frameworks/backend/fastapi):
`pyproject.toml` explicitly sets `tool.vercel.entrypoint = "backend.main:app"`,
preventing discovery of the root Streamlit `app.py`. It declares Python 3.13 and
web-only runtime dependencies. `requirements.txt` remains the local combined
Streamlit/test/web dependency list and is excluded from CLI deployment uploads
by `.vercelignore`. `vercel.json` selects a 60-second function budget and excludes
development/evaluation files; `.vercelignore` also excludes credentials and the
local environment. No Streamlit or pytest runtime dependency is declared in the
deployment manifest.

The API serves `/` and mounts `/static` with FastAPI StaticFiles; it does not
mount a Vercel `public/` directory. All application/knowledge/static paths resolve
from their module location. `nyaysaathi/data/legal_knowledge.json` stays in the
bundle. No writable working directory or server session is required. The security
middleware may keep static assets in the function rather than promoting them to
the CDN; either way they are served at the same `/static/...` paths.

For a new deployment, use the repository root, the FastAPI framework preset,
and server-side Vercel environment settings for the three Gemini variables. Keep
secrets out of source/assets. Phase 9 prepared this configuration without deploying.
Phase 10 subsequently verified the actual public deployment linked above. Review
dependency selection, bundle size, static routing and the function budget for
future preview builds. Existing legal-source review cutoffs still apply.

### Web verification and limits

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_api.py
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe -m compileall -q backend nyaysaathi tests app.py
node --check web/app.js
node --check web/audio.js
node --check web/pcm-worklet.js
node --test tests/web_audio.test.mjs tests/web_ui.test.mjs
```

Node 22+ is needed only for the optional offline JavaScript tests. Tests mock
Gemini and block real client construction. The JavaScript tests cover real WAV
encoding/resampling, resource cleanup and DOM/event logic for edited drafts,
outdated warnings, approved transcripts, duplicate prevention and new-case reset.
The small DOM harness is **not a real browser**, CSS rendering or permission test.
Local HTTP checks verify the production routes/assets with mocked model outputs.
Browser automation timed out in Phase 9. In Phase 10 it successfully checked the
public desktop/mobile layouts, language controls, example prefill and reset.
Microphone permission, real recording/preview, browser downloads and genuine
transcription **still need manual verification**. No live Gemini calls were made
for Phase 9; exactly two fictional chat calls were made for Phase 10. See the
verification report for their actual results and limitations.

Final Phase 9 checks: **201 Python tests passed** (the existing 169 plus 32 API
tests), **8 JavaScript tests passed**, syntax/import checks passed, and `pip check`
reported no broken requirements. One upstream Starlette TestClient warning about
its deprecated httpx transport remains; tests still pass. Original evaluation
artifacts and intelligence modules were preserved.

This is a demonstration without authentication, server-side rate/spend limits,
signed case state or distributed request deduplication. Direct callers can alter
their own submitted case/context. UI locking prevents ordinary duplicate actions,
but repeated HTTP requests are independent; an aborted browser request may still
complete on the server. Configure deployment access/spend controls before public
sharing. There is no legal-accuracy or production-security guarantee. Audio/text
are transmitted to Google only on the relevant explicit actions; provider/platform
data handling applies separately. Use fictional information and review every fact.

## Existing Streamlit setup (PowerShell, Python 3.11+)

```powershell
cd E:\KukuProblem2
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Run the copy command only when creating your first `.env`; preserve an existing
configuration. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).
In `.env`, fill both values, save, and close the editor:

```dotenv
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=your_available_structured_output_model_id
GEMINI_TRANSCRIPTION_MODEL=gemini-3.5-transcribe
```

Replace both placeholders. Choose an available model ID from Google AI Studio
that supports structured JSON output; the app has no hardcoded model.
Account access, quota, and billing depend on your Google account.
The transcription model defaults to `gemini-3.5-transcribe` and is independent
of the intake model. An override must support the dedicated transcription config;
the app does not silently fall back to another model.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the URL printed by Streamlit, normally `http://localhost:8501`.
For macOS/Linux use `.venv/bin/python` in place of
`.\.venv\Scripts\python.exe` and your local project path.

## Reproducible evaluation

See [evaluation/README.md](evaluation/README.md) for the frozen ten-case dataset,
offline fixtures, opt-in live CLI, explicit scoring rules and human-review checklist.
The first live suite used exactly 12 requests with no retries. Original responses
and complete SDK payloads are preserved separately from scores. Read the
[evaluation report](evaluation/results/evaluation_summary.md), including its
failure analysis, before interpreting automatic pass counts as application quality.
Existing results are never overwritten and the persistent first-live budget is spent.
Saved results can be rescored with zero API calls.

### Phase 7: correction consistency fix

Corrections and withdrawals now invalidate derived summaries and timelines when
their provenance cannot be trusted. Current structured fields are retained;
unresolved conflicting fields become unknown and require clarification. Earlier
conversation quotes cannot silently restore invalidated prose. Draft generation
uses current fields and review placeholders instead of stale narratives.

After invalidation, review the fields and explicitly choose a provisional draft.
Add a fresh neutral description and timeline in the editor. Existing edited drafts
remain untouched and carry an outdated warning until you explicitly regenerate.
Automatic narrative restoration is deliberately not implemented. The legacy
amount/date conflict checks are conservative heuristics, not complete fact checking.

The original T05/T06 failures and Phase 6 scores remain intact. See the
[fix analysis](evaluation/results/failure_analysis.md#phase-7-correction-consistency-fix)
and [stored-response replay](evaluation/results/phase7_replay/replay_summary.md).
Replay uses no Gemini requests; choose a new output folder for each run:

```powershell
.\.venv\Scripts\python.exe -m evaluation.replay_phase7 --output evaluation/results/my-phase7-replay
```

### Other configuration options

Instead of `.env`, set environment variables in the terminal used to launch:

```powershell
$env:GEMINI_API_KEY = "your_actual_key_here"
$env:GEMINI_MODEL = "your_available_structured_output_model_id"
```

Or use the ignored Streamlit secrets file:

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
notepad .streamlit\secrets.toml
```

Fill the two quoted strings. Do not overwrite existing secrets.
Per-setting precedence is **Streamlit secrets > environment > project `.env`**;
blank values fall through. Restart Streamlit after changing secrets. `.env` is
read from the project folder and does not export values into the environment.
Without either setting the UI still opens and preserves submitted messages,
but shows a configuration error instead of fabricating an assistant reply.

`.env`, `.env.*` except `.env.example`, and `.streamlit/secrets.toml` are ignored
by Git. Example files contain no credentials. Keys are never rendered or included
in app error messages. Do not paste real API keys into chat.

## Voice input: record, review, then send

Voice uses the existing key and the maintained `google-genai` SDK (installed and
tested against 2.34.0; no additional dependencies). The service uses Google's
[documented generateContent transcription endpoint](https://ai.google.dev/gemini-api/docs/generate-content/transcribe)
with `AudioTranscriptionConfig(mode="VERBATIM", language_codes=[])`.
Automatic detection handles English, Hindi and code-switching; no translation is
requested. Verbatim mode preserves spoken self-corrections for review instead of
silently cleaning them up. No legal-generation prompt or case context is sent
with audio. The existing intake API interaction is unchanged.

To test locally, run the app using the setup above, then:

1. Allow microphone access in your browser for localhost. In **Voice input**,
   record a short fictional English, Hindi or Hinglish consumer complaint and stop
   within 60 seconds. If permission is unavailable, text chat remains usable.
2. Preview the recording, then click **Transcribe Audio**. Recording alone sends
   nothing to Google. This explicit action makes one transcription request.
3. Review and edit the transcript, especially seller names, amounts, dates and
   spoken corrections. Nothing is added to the case at this stage.
4. Click **Send to NyaySaathi**. Only the approved text goes through the existing
   intake/retrieval/citation/correction path, making one normal intake request.
5. Check the Case File and guidance. Ordinary reruns and language changes make
   no transcription calls; a successfully transcribed recording is not transcribed
   again. A failed transcription can be retried only by explicitly clicking again.

An approved recording can be sent once per case; its recording hash prevents
repeat sends on rerun or reselecting identical audio. If intake fails, the message
is kept and the case stays unchanged. Use text chat to deliberately resend/correct
it. Recording new audio clears the previous transcript editor. **Start a new case**
clears the conversation, case, document edits and voice state, and resets the
microphone widget. Download any work to keep before using that button.

### Audio limits and privacy

The browser widget records at 16 kHz. The reusable service accepts **16-bit PCM
WAV only**, one or two channels, 8–48 kHz, at most **60 seconds**, and **below
2,000,000 bytes** (maximum 1,999,999). It validates MIME aliases, RIFF/WAVE headers,
PCM properties, duration and complete frame data. Empty, truncated, unsupported,
oversized, overlong and all-zero silent recordings are rejected before any API
request. Longer recording is not automatically stopped by the browser widget;
it is rejected after recording. Other formats are deliberately unsupported locally
even though Gemini accepts more formats, so duration/content validation needs
no FFmpeg or heavy decoding library.

Audio is passed inline from memory to Google; no local audio files or provider
Files API uploads are created, so there are no temporary/provider files to clean
up. No raw audio or transcripts are logged by application code. Browser playback
and transcript/editor state are held in the current Streamlit session, not saved
to a case database. Google's API data handling applies separately; avoid sensitive
real-world details in this demo. Clear the recording or start a new case when done.

Timeouts are bounded to 45 seconds per SDK request and automatic retries are
disabled. Quota, timeout, configuration and malformed/blocked/truncated-output
errors are shown without provider exception details. Empty or explicitly unclear
transcripts are errors. These checks cannot reliably detect every noisy recording,
hallucinated word or wrong name/number; user review remains essential. A transcript
is an unverified user-approved account, not proof of what was spoken or independent
evidence of a purchase.

`nyaysaathi.transcription.transcribe_audio(audio_bytes, mime_type, settings)`
returns a Pydantic `TranscriptionResult` containing the transcript, model, validated
audio metadata and review flag, or raises `TranscriptionError` with a safe code.
It imports no Streamlit code and can be called unchanged by a future FastAPI
endpoint; request-level authentication/rate limits would belong to that backend.
No FastAPI/Vercel application is added in this phase.

Phase 8 verification uses synthetic WAV containers and mocked responses, not
artificial evidence of speech recognition. No genuine spoken-audio fixture was
available, so **no live transcription test was performed**. Manually test the
three languages with short fictional speech and confirm model access/quota before
claiming live recognition quality. Normal voice use costs one transcription call
plus one intake call after approval.

The full offline suite passed **169 tests**, including the existing 132 tests.
Syntax compilation and a separate mocked localhost Streamlit runtime exercise
also passed: explicit transcription, transcript editing, shared correction intake,
no duplicate calls on rerun, and new-case reset. These are workflow checks, not
evidence of real speech recognition. Run the focused offline checks with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_transcription.py tests/test_voice_app.py tests/test_settings.py
```

## Action Package: local documents without additional AI calls

After reviewing your Case File, open **Action Package** and choose an English or
Hindi formal template. Hinglish users can choose either. Case wording is copied
as supplied, not automatically translated; edit it into the final language yourself.
The generator uses only the validated CaseFile snapshot and deterministic templates.
It does not consult Gemini, retrieve additional law, or alter the case or validators.
Templates were chosen to keep wording auditable and avoid invented facts/legal claims.

The package contains:

- **Seller/company complaint:** a neutral subject, the user's account, recorded
  amount/date, supplied timeline, identifiable previous communication, requested
  resolution, a polite request for a written response, and closing placeholders.
- **NCH preparation summary:** labeled transaction/grievance/evidence/attempt/outcome
  sections and missing information. It is neither automatically submitted nor
  officially validated by NCH.
- **Personalized evidence checklist:** evidence the user reports having, potentially
  useful items to collect/check, and other standard items with unknown availability.
  Suggestions are not claims that evidence exists or a mandatory legal checklist.

### Readiness and review

- **Ready to draft:** core case details, amount/date, and reported evidence are present.
  This does not mean ready to send; identity/reference placeholders still need review.
- **Draft contains missing information:** explicitly select the provisional option.
- **Insufficient information:** essentials are listed. A known issue type can support
  an explicitly provisional placeholder draft; a completely empty case cannot.
- **Out of scope:** generation is disabled. Existing professional-review warnings
  for notices, threats/criminal allegations, and unrelated matters also block generation.

Review every allegation, seller name, amount, date, evidence statement and timeline
before use. An amount does not by itself prove a payment. The generic incident date
is never promoted to a purchase date. Exact decimal amounts are not silently rounded.
The current schema has no dedicated order ID, product name, buyer name/contact, or
purchase-date field, so these use explicit editable placeholders even if mentioned
in the narrative. Copy confirmed details into them after checking your records.
Only identifiable, non-negated communication entries from the supplied timeline
are included as previous contact; other history remains in the timeline for review.
Non-neutral wording or legal-claim text can be replaced/omitted for manual review;
this does not change the Case File. Keyword checks are conservative, not a complete
language-safety classifier. Always review the text yourself.

### Editing, copying and downloads

Click **Generate complaint package** only when you want documents. Both the
complaint and structured NCH summary have native text editors. Their edits persist
across ordinary reruns, interface language changes and case corrections in the
current session. A fingerprint flags changed case facts or document-language choices;
it does not regenerate anything. **Regenerate package (replaces your edits)** is the
explicit action that replaces the existing package and edits.

Download either reviewed editor as a UTF-8 text file (with BOM for Hindi/rupee
compatibility), or use the native copy buttons under **Copy-ready text**. Downloads
contain the current committed edits, not the original template text. Commit edits
by leaving the field or pressing Ctrl+Enter before downloading. Earlier package
edits remain visible if scope changes, but generation/downloads are disabled while
the current case is blocked. Stale drafts can still be reviewed/downloaded with an
outdated warning, so check all changes before use.

Nothing is sent, emailed, filed or saved to a database. These are consumer complaint
preparation documents, not lawyer-issued legal notices. There are no statutory
sections, penalties, response deadlines, guaranteed refunds or compensation promises
in the templates. Manual additions are the user's responsibility. Session data can
be lost on refresh/restart: download work you want to keep.

The fictional file in `examples/fictional_complaint_en.txt` demonstrates actual
generator output and its placeholders. No extra dependencies are required.

## Grounding architecture

1. Local deterministic retrieval ranks up to six records using the latest question
   and existing case issue, summary, and desired resolution. Question matches carry
   more weight than case matches; stable ID sorting breaks ties. Match reasons are
   included in the model context. There is no vector database or network retrieval.
2. One Gemini request combines the existing structured intake with selection/order
   of up to four grounded explanations and one relevant follow-up question.
3. Pydantic validates the response. Existing quote grounding, correction rules,
   unknown defaults, and transactional case updates are preserved.
4. Legal output uses a deliberately conservative claim-level gate: every selected
   ID must belong to THIS turn's retrieved records, and its explanation must exactly
   match that record's audited wording in the chosen English/Hindi/Hinglish language.
   Novel legal paraphrases are withheld instead of being labeled verified.
5. The application, not the model, supplies official URLs, provision/page locations,
   checked dates, practical next steps, and limitations from the accepted records.
   Unknown IDs, fabricated URLs, fabricated sections, guarantees, or altered legal
   statements cannot become validated references.
6. Legal Guidance / Your Options shows the accepted explanations and citations.
   When sources are missing, expired, irrelevant, or fail validation, it displays an
   explicit uncertainty or safety notice. It never silently displays rejected prose.

The model dynamically selects relevant information and asks follow-ups; it cannot
freely write new legal claims. This trades answer breadth for auditable support.
A correct URL alone is never accepted as proof of the generated claim.

## Three distinct types of information

- **User allegations:** Case File facts and the acknowledgment of the user's account.
  Amounts, seller names, dates, and evidence are user-reported and not independently verified.
- **Checked official information:** Curated general statements with source IDs,
  locations, dates, and applicability limits.
- **AI-selected explanations:** Gemini chooses and orders the audited statements
  for the question and case. This is not an official adjudication or independent
  legal interpretation. The model also generates the intake question and missing-detail assessment.

The chat remains intact. Legal explanations appear in the options section; chat
asks one follow-up or shows an urgent/scope warning. A failed turn retains the user
message and previous case, and clears the previous legal panel so it is not
mistaken for a new answer. No automatic retries; the SDK timeout remains 45 seconds.

An independently validated legal explanation can still be shown if the proposed
case-fact update fails (for example a nonverbatim evidence quote). In that situation
the entire Case File remains unchanged and an explicit error notice is shown;
the app does not relax the fact checks or silently apply a partial update.

## Official sources and supported topics

The 11 records live in `nyaysaathi/data/legal_knowledge.json`.
Each has a unique ID, topic, multilingual statement/action/limitation, exact official
URL, relevant provision or page location, checked date, and review cutoff.

| Official source | Supported information |
| --- | --- |
| [Consumer Protection Act, official DoCA copy](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) | Consumer complaint overview, defective goods and possible remedies, documentary evidence, professional-help caution |
| [DoCA legislation and rules index](https://consumeraffairs.gov.in/pages/consumer-protection-acts) | Audit trail for the Act, e-commerce rules, corrigendum, and amendments |
| [E-Commerce Rules, 2020](https://consumeraffairs.gov.in/public/upload/files/E%20commerce%20rules_1732703966.pdf) | Conditional refund/late-delivery information, seller/platform contacts |
| [NCH home](https://consumerhelpline.gov.in/) and [contact](https://consumerhelpline.gov.in/public/contact) | Grievance registration/tracking route and published phone numbers |
| [e-Jagriti Help Docs](https://e-jagriti.gov.in/help-docs) | Official onboarding/Consumer Complaint filing-guide listings only |
| [2026 e-commerce amendment](https://consumeraffairs.gov.in/public/upload/files/E%20Commerce%20Amendment%20Rules%202026_1789127949.pdf) | Verified future commencement status |

**Checked: 9 November 2026.** The published 2026 amendment commences on
**1 January 2027**, confirmed visually on English PDF page 5. Its added duties are
not applied as current law before that date. All records expire for retrieval
after **31 December 2026** until manually rechecked and updated.

The requested India Code record timed out; the Act claims were checked against
DoCA's official Gazette copy instead. The e-Jagriti direct page was JavaScript-only;
only its official-domain indexed guide listings could be checked. Detailed fees,
upload procedures, jurisdiction thresholds, individual eligibility, judicial
decisions, fixed refund timelines, and calculated filing/appeal deadlines are omitted.
See `nyaysaathi/data/verification_notes.md` for exact source checks, amendment
review, the downloaded amendment hash, limitations, and the update procedure.

## Scope and safe escalation

Supported: Indian consumer refunds, defective goods, non-delivery, and related
service complaints, within the checked records. No automatic refund or success claim
is made. Evidence lists are preparation suggestions, not mandatory legal checklists.

Deterministic keyword guards and the model's structured safety flag identify
unrelated legal topics, notices/hearings/deadlines, threats/violence/injury/criminal
allegations, and insufficient sources. They suppress legal conclusions and direct
users to qualified help when appropriate. Safety notices are app cautions, not
statutory advice. Keyword/model classification can miss context or be overcautious;
it is not an emergency service or a complete legal triage system.

## Verify offline

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe -m compileall -q app.py nyaysaathi tests
```

Tests use clearly labeled synthetic outputs and mocked providers/SDK clients.
The automatic fixture blocks real Gemini client construction. They cover existing
intake behavior plus defective goods, non-delivery, refunds, Hindi/Hinglish wording,
unknown/nonretrieved IDs, real IDs with invented claims, fabricated sections/URLs,
insufficient/expired sources, escalation, failures, case preservation, and the options UI.
Mocks are not live-model evidence. Optional chat smoke checks consume Google API quota;
Action Package generation, editing, copying and downloading make no model calls.

If Windows temporary-folder permissions block pytest fixtures, use a fresh dedicated
base folder, for example `--basetemp=.pytest_cache/local-test-temp`. Pytest clears
that folder. Some restricted Windows environments also block Streamlit's local
event loop; run the offline tests from a normal local terminal in that situation.

## Replace the model

Change `GEMINI_MODEL` to an available Gemini model supporting structured JSON;
no UI change is needed. For another provider, implement the small `ModelProvider`
interface in `nyaysaathi/intake.py`: accept case, conversation, language, and the
retrieval context, then return JSON matching `IntakeResponse`. Pass that provider
to `run_turn`. Keep retrieval, quote checks, citation/claim validation, and UI commits
outside the vendor adapter. Do not bypass validation to accommodate a model.

## Privacy and limits

Submitting sends the text conversation, current case, and selected local source
records to Google's Gemini API. The app does not save cases/conversations to a
database. Session state may be lost on refresh/restart. Google's API data handling
applies separately; use fictional examples for demos.

There is no automatic source refresh, exhaustive legal corpus, independent legal
review, or guarantee that a selected general statement applies to a particular case.
The local translations are app translations. The app cannot authenticate evidence
or prove that the model interpreted user facts/corrections correctly. Review the
case and the linked official text. Legal wording is bounded to the audited records;
unsupported questions can therefore receive a cautious fallback.

Voice transcription is implemented as the explicit review-before-send flow above.
No PDF generation, e-Jagriti filing automation, external messaging, agent framework,
autonomous agents, vector database, deployment, or additional paid service is added.

## Main files

```text
app.py                              Chat, Legal Guidance / Your Options, Action Package
backend/main.py                     Stateless FastAPI adapter and static asset routes
backend/schemas.py                  Bounded Pydantic HTTP contracts
web/                                HTML/CSS/JS browser UI and genuine PCM WAV capture
nyaysaathi/action_package.py         Pure readiness/templates/checklist/text exports
nyaysaathi/models.py                 Case and combined response schemas
nyaysaathi/settings.py               Secrets/environment/.env configuration
nyaysaathi/transcription.py          In-memory WAV validation and Gemini transcription
nyaysaathi/gemini.py                  One-request SDK adapter and source-aware instructions
nyaysaathi/intake.py                  Case merge and combined turn coordination
nyaysaathi/consistency.py             Correction/conflict narrative invalidation
nyaysaathi/knowledge.py               Local record loading and deterministic retrieval
nyaysaathi/guidance.py                Citation/claim validation and safety fallbacks
nyaysaathi/data/legal_knowledge.json  11 auditable multilingual records
nyaysaathi/data/verification_notes.md Source verification and omitted claims
tests/                              Offline schema/provider/grounding/document/UI tests
```
