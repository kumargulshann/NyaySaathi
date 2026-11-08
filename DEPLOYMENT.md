# Phase 10 publication and verification

Authorized repository: https://github.com/kumargulshann/NyaySaathi

No public application URL is claimed until its actual HTTPS endpoints are checked.
The repository did not have local Git history when Phase 10 started. An earlier
development key had appeared in `.env.example` and
`.streamlit/secrets.toml.example`; the examples now contain placeholders. The user
confirmed revoking/replacing the key and updating local `.env` during Phase 10.
Removing a key from a file is not a substitute for revocation.

## Local browser and completed-intake fix

The workspace settings keep the existing Python environment behavior and set:

```json
{
  "workbench.browser.openLocalhostLinks": false,
  "workbench.externalBrowser": "chrome"
}
```

These are the [documented VS Code settings](https://code.visualstudio.com/docs/debugtest/integrated-browser)
for opening terminal localhost links externally. The settings are local/ignored.
If an older VS Code version ignores a workspace setting, enter the same settings
in VS Code User Settings, or paste `http://127.0.0.1:8000/` directly into Chrome.
Opening a link inside VS Code does not itself cause the HTTP 502.

The 502 was reproduced offline with a structured `ready_for_review` response and
`next_question: null`: JSON schema allowed null, but the semantic validator rejected
it. Completed consumer intake now permits no new question only when the core case
facts exist. It returns navigation to the existing Case File, checked information
and Action Package. Unknown dates/evidence stay unknown. Missing core facts still
fail closed; citation validation and correction rules are unchanged. The prompt
also stops repeatedly asking for confirmation after the user requests next steps.
The screenshot's original raw response was unavailable, so this does not prove
every possible 502 has the same cause. Malformed/unsafe provider outputs still fail.

## Security review and local evidence

Never publish `.env`, `.streamlit/secrets.toml`, virtual environments, editor/cache
data, private credentials, the assignment PDF or unreviewed user data. Git and
Vercel exclusions cover these files. The scanner checks exact active-key matches,
common credential patterns, private-key headers and forbidden file paths without
printing matching values:

```powershell
.\.venv\Scripts\python.exe scripts/audit_publication.py --history
```

The staged blobs, not just working files, are scanned. Pattern checks are not an
exhaustive secret/PII detector. The included evaluation scenarios declare fictional
provenance; recorded user turns are compared with that frozen dataset before
publication. No real user session is persisted. Original Phase 6 raw files are
preserved locally, and their 37 recorded artifact hashes must remain unchanged.
No existing Git history is rewritten.

## Vercel GitHub integration

1. Sign in at https://vercel.com/new using your own account. Do not paste a Vercel
   token or Gemini key into chat.
2. Import **kumargulshann/NyaySaathi** through the official GitHub integration.
   Authorize that repository if it is absent from the list. Keep the project root
   as the repository root and select **FastAPI** as the framework if not detected.
3. Use the existing `pyproject.toml` entrypoint `backend.main:app`, Python 3.13,
   and `vercel.json` function budget. There is no Node/frontend build command.
   Keep project-defined build/install defaults; confirm web-only dependencies in
   the build log. The root Streamlit entrypoint is deliberately excluded.
4. In **Settings → Environment Variables**, add these server-side names for
   **Preview** and **Production**, using values from your rotated local `.env`:
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL` (keep the existing working text model)
   - `GEMINI_TRANSCRIPTION_MODEL` (the documented transcription model)
   Do not prefix them with a frontend/public environment-variable prefix.
5. Create a Preview deployment first when practical (a branch/PR deployment),
   then promote to Production after checks. If importing `main` creates the first
   production deployment automatically, treat it as unverified until these checks
   pass. Redeploy after environment-variable changes. Share the actual deployment
   URL, never an invented project slug.
6. If Deployment Protection blocks anonymous access, sign in using your own account
   for private checks. For a shareable assignment prototype, deliberately review
   who can access the project. Do not share bypass tokens in chat or source.

This project has no authentication or robust server-side rate limiter. Public
visitors can consume Gemini quota even on a free plan. Keep the demo limited,
monitor quota/spend, and use platform access controls as appropriate. It is not
abuse-proof or approved for unrestricted production use.

## Check an actual deployment

After the user supplies a real authorized public HTTPS origin:

```powershell
# No model calls: HTML, health, assets, safe validation errors and credential scan.
.\.venv\Scripts\python.exe scripts/verify_deployment.py https://YOUR-ACTUAL-HOST
# At most TWO fictional chat requests, once only after server variables are set.
.\.venv\Scripts\python.exe scripts/verify_deployment.py https://YOUR-ACTUAL-HOST --live
```

The live script reserves request attempts before sending in the ignored
`.pytest_cache/phase10_live_budget.json`. Do not delete/reset this file or repeat
the run to exceed the two-call Phase 10 budget. The calls are English damaged
headphones and Hinglish non-delivery, not genuine voice-recognition tests. An
HTTP timeout does not prove the server made no model request. No automatic retry
or model switching is performed. Keep failures in the report rather than hiding
them with further requests.

Generate a complaint package from an existing fictional CaseFile through
`/api/action-package`; that endpoint makes no Gemini call. For browser checks,
open the actual URL in Chrome on desktop and at narrow/mobile width. Check the
conversation, case/guidance, source links, edit retention, stale-draft warning,
explicit regeneration and TXT downloads. Do not repeat automated browser attempts
if the automation service times out.

Microphone access requires HTTPS (or localhost). Manually check permission,
record/stop, elapsed time and preview. Only click Transcribe for a genuine safe
spoken sample with a separately available call budget; review/edit before sending.
Without such a sample, live recognition remains **not verified**. Recording and
preview alone require no model call.
