# NyaySaathi AI

Consumer grievance intake and complaint preparation for India

## Problem 2 · Build an AI Lawyer

I chose online purchase disputes because the first barrier is often turning a messy story into a clear account of what happened, what evidence exists, and what to do next. NyaySaathi helps ordinary consumers with damaged goods, missing deliveries, refunds and closely related service complaints. A narrow scope makes the guidance easier to check and the documents easier to evaluate.

**Assumptions.** The user can describe the purchase or speak a short account. Dates, seller identity and desired remedy may be unknown. Case facts and evidence are user-reported. The app prepares documents for review. Users decide what to submit and file it themselves.

## From a story to an editable complaint

1. Type in English, Hindi or Hinglish, or record a short clip. Preview the recording, then review and edit the Gemini transcript before sending it to intake.
2. Review the Case File. The assistant records supported facts, leaves unknowns open and asks one follow-up at a time. A seller's past refusal is recorded as an event and requires separate confirmation of the remedy the user wants now.
3. Read the plain-language options with official source links. Generate an editable complaint, National Consumer Helpline (NCH) preparation summary and evidence checklist. Missing details become placeholders. New facts flag existing drafts for review and the user's edits stay until explicit regeneration.

## Architecture and division of work

**Browser → FastAPI on Vercel → Gemini → validated Case File and local templates.** The browser keeps temporary state. The Python server checks the signed Case File on follow-ups and draft requests. Gemini transcribes approved audio and proposes structured fact changes, a question and source selections. Pydantic and Python validate the schema and user quotes, enforce correction rules and render the documents without another model call.

**Legal grounding.** Local retrieval ranks dated records drawn from the Consumer Protection Act, E-Commerce Rules, NCH and other official sources. A legal statement appears only if Gemini selects a record retrieved for that turn and returns its exact reviewed wording in the chosen language. The server supplies the URL and applicability limits. Missing, expired or unsupported sources lead to a cautious fallback. Urgent and out-of-scope matters can trigger a referral to qualified help. Users should review the case and official text before relying on this general information or using a draft.

**Tools.** Codex supported implementation, tests and failure analysis. Gemini handles intake and transcription. Python, FastAPI, Pydantic, browser JavaScript, GitHub and Vercel make up the deployed prototype.

**Prototype** [nyay-saathi-psi.vercel.app](https://nyay-saathi-psi.vercel.app/) · **Source** [github.com/kumargulshann/NyaySaathi](https://github.com/kumargulshann/NyaySaathi)

<!-- pagebreak -->

# What the evaluation found

## Original live run · 10 scenarios, 12 requests, 8/10 passed

I froze fictional cases and their expected checks before running `gemini-3.5-flash-lite` through production intake, retrieval, validation and document generation. The cases cover three languages, missing facts, corrections, out-of-scope and urgent requests, invented law and prompt injection. All 12 responses parsed. Fact extraction passed 61/62 applicable checks and legal grounding passed 107/108. This small set is not a representative accuracy benchmark. Human review of fluency, usefulness and legal appropriateness remains unscored.

## Failures that shaped the implementation

**T03 · Name spelling.** Gemini returned “Fictional Kamal Store” in Latin script for a seller named in Hindi, failing the frozen literal-name check. The intake now asks for and checks the name in the user's original script. The original result remains in the score.

**T07 · Over-refusal.** Gemini rejected the whole defective-goods turn when it was also asked to invent a law and guarantee compensation. The app withheld the false claim, but the consumer task failed the expected narrower response. Mixed requests remain a limitation.

**T05 and T06 · Stale drafts.** A correction updated the amount to ₹2,500, but the template also copied ₹2,000 from the old summary. A separate draft repeated a withdrawn date. The scalar checks missed both. The fix invalidates affected prose and uses current structured facts and placeholders. Offline replay of all 12 original responses verified the correction behavior without changing the live scores.

**Later checks.** Phase 13 blocked generic seller labels and inferred remedies from becoming confirmed facts in the Case File and drafts. Phase 15 removed the repeated review question and separated the order date from the incident date. The project author reported that the final production conversation worked through a date correction and follow-up questions, and that voice transcription worked in English, Hindi and Hinglish. These are manual checks without a measured recognition rate. The current offline suite passed **267 Python and 8 JavaScript tests**.

## Reuse, cost and limits

Change `GEMINI_MODEL` to swap structured-output Gemini models, or replace the small provider adapter while keeping validation and templates. A normal intake turn uses one model call. Voice adds one transcription call when requested. Local retrieval and drafts use zero model calls. Request bounds and no automatic retries limit per-turn work. The public demo lacks robust quota protection. At higher volume I would add access and quota controls and measure usage, latency and cost before broadening scope.

Quote checks can miss semantic errors. The curated consumer-law records need periodic review. The app prepares drafts for review and leaves filing to the user. It does not authenticate evidence, guarantee legal outcomes or replace a lawyer.

[Original evaluation report](https://github.com/kumargulshann/NyaySaathi/blob/ba740e9167f90829ad5f3e8b890f7b2e03c79191/evaluation/results/evaluation_summary.md) · [Phase 7 replay](https://github.com/kumargulshann/NyaySaathi/blob/ba740e9167f90829ad5f3e8b890f7b2e03c79191/evaluation/results/phase7_replay/replay_summary.md)
