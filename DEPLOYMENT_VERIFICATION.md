# Phase 10 — actual HTTPS verification

Date: **9 November 2026** (Asia/Calcutta).

- Public prototype: **https://nyay-saathi-psi.vercel.app/**
- Source: **https://github.com/kumargulshann/NyaySaathi**
- Application revision checked: **2af5542**. Documentation-only updates do not
  change the application revision's tested Python/JavaScript behavior.

## Public endpoint checks

| Check | Observed result |
| --- | --- |
| `/` | 200, actual NyaySaathi HTML |
| `/api/health` | 200 |
| CSS, app JavaScript, WAV encoder, AudioWorklet | 200; byte hashes match the reviewed Git commit |
| Empty/extra-field chat request | 422, safe validation error, no model call |
| Invalid WAV request | 400 `invalid_audio`, no transcription call |
| `/api/action-package` | 200; complaint and NCH summary exactly match the local deterministic generator for the existing fictional fixture |
| Frontend/response credential check | No active key or known credential patterns detected in checked content |

The actual application and health endpoints were reachable anonymously at the
supplied production URL. No unexpected 404 or 500 occurred in these checks.

## Two real Gemini requests — budget exhausted

Exactly **two** fictional `/api/chat` requests were made, without retries/model
switching. No live transcription call was made.

| Input | Observed extraction | Guidance |
| --- | --- | --- |
| English damaged headphones worth ₹2,999; seller refuses refund | `defective_product`, amount 2999, seller/date unknown, no reported evidence; relevant English seller-name question | `grounded`; CPA-DEFECT, RULES-REFUND, RULES-CONTACT |
| Hinglish Flipkart order worth ₹4500, not delivered, refund requested | `non_delivery`, Flipkart, amount 4500, date unknown, no reported evidence; Hinglish date question | `grounded`; RULES-NONDELIVERY, RULES-REFUND |

Both responses returned 200, parsed into validated case state, and supplied exact
audited explanations/official URLs matching the local knowledge records. These
small checks do not establish general extraction or legal accuracy.

**Review observation:** the English test recorded `desired_resolution=refund`
despite only describing the seller's refusal, rather than separately stating the
user's requested outcome. That inference needs user confirmation; a valid quote
and schema do not independently prove semantic extraction. The interface's fact
review/correction requirement remains necessary. No additional calls were made
to tune or hide this observation.

## Browser and voice boundaries

The public page was opened in a real browser at desktop **1280×900** and narrow
**390×844** viewport settings. Checked English/Hindi labels, example-message
prefill and Start New Case clearing the input. DOM width checks showed no
horizontal overflow. Screenshots were saved locally, with no console warnings or
errors observed during this navigation. Viewport overrides were reset afterward.

The paid requests were sent through HTTP verification, not an additional browser
chat submission; the two-call limit prevented a further live browser conversation.
Frontend response-rendering, edit/download and duplicate safeguards are covered
by the offline DOM/event tests, not claimed as a third live request.

The voice controls were visible on HTTPS, and invalid-audio rejection was checked.
Actual microphone permission, record/stop/preview and genuine voice recognition
remain for the user to verify with a suitable spoken sample. No synthetic signal
was presented as successful live speech recognition. The current Phase 10 model
budget is spent; do not run another agent transcription/chat smoke test under it.

## Security and remaining limitations

The user confirmed key rotation before publication. Tracked source/history were
scanned without finding credentials; the original assignment PDF and private
local files are excluded. The 37 original Phase 6 raw-artifact hashes remain
unchanged. A subsequently entered key in the local `.env.example` was restored
to a placeholder without displaying it; the remote repository still matched the
reviewed secret-free commit at verification time. Keep credentials exclusively
in ignored `.env` or Vercel's server-side settings.

Live chat demonstrates usable server-side `GEMINI_API_KEY` and `GEMINI_MODEL`.
The effective transcription-model setting was not independently runtime-verified.
No key values are included here.

This is a **limited assignment prototype**, with no authentication, robust
server-side rate limiting, or production legal/security guarantee. Public visitors
can consume Gemini quota, including free-tier quota. Keep sharing limited and
monitor usage. Do not advertise live voice recognition as verified.

Offline verification: **210 Python tests**, **8 JavaScript tests**, syntax and
dependency checks passed. One upstream TestClient/httpx deprecation warning remains.
