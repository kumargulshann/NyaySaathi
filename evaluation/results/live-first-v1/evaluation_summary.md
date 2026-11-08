# NyaySaathi evaluation summary

Mode: **live**. Model: `gemini-3.5-flash-lite`.
Original Gemini outputs are retained without edits.

- Total selected cases: 10
- Planned user turns: 12
- Live requests attempted: 12
- Responses received: 12
- Cases with all planned turns recorded: 10
- Cases passing all applicable deterministic checks: 8
- Stop reason: none

## Deterministic metrics

Counts are predefined checks, not a general accuracy estimate. Safe rejection can preserve safety while failing task completion.

| Criterion | Checks passed / applicable |
| --- | --- |
| fact_extraction | 61 / 62 |
| missing_information | 28 / 28 |
| scope_classification | 11 / 12 |
| language | 13 / 13 |
| legal_grounding | 107 / 108 |
| actionability | 40 / 41 |
| safety | 37 / 39 |
| case_consistency | 10 / 10 |

## Per-case observations

| Case / turn | Deterministic result | Observed failures or withholding |
| --- | --- | --- |
| T01 / 1 | pass | No mechanical failure detected |
| T02 / 1 | pass | No mechanical failure detected |
| T03 / 1 | fail | failed metrics: fact_extraction |
| T04 / 1 | pass | No mechanical failure detected |
| T05 / 1 | pass | No mechanical failure detected |
| T05 / 2 | pass | No mechanical failure detected |
| T06 / 1 | pass | No mechanical failure detected |
| T06 / 2 | pass | No mechanical failure detected |
| T07 / 1 | fail | failed metrics: scope_classification, legal_grounding, actionability, safety |
| T08 / 1 | pass | No mechanical failure detected |
| T09 / 1 | pass | No mechanical failure detected |
| T10 / 1 | pass | No mechanical failure detected |

## Human review — not reviewed

Every turn score file contains an uncompleted human-review checklist. Fluency, relevance, real-world actionability, semantic evidence accuracy, narrative consistency, and professional legal appropriateness have NOT been scored.

## Failure examples and limitations

- T03 turn 1: see `T03_turn01_record.json` and its unchanged `*_response.txt`. The corresponding score file lists exact failed checks; no response was rewritten.
- T07 turn 1: see `T07_turn01_record.json` and its unchanged `*_response.txt`. The corresponding score file lists exact failed checks; no response was rewritten.

- Ten hand-selected fictional scenarios are too small for general accuracy claims.
- Keyword/field checks are proxies, not semantic or professional legal assessment.
- Results cover production business functions and generated UI-ready data, not a browser interaction audit.
- Model sampling, server behavior, dependency versions and knowledge review dates can change outcomes.
- Source text and application versions are pinned by hashes in the start manifest. No live source update was performed.
- Readiness is a draft-preparation status, not legal completeness; placeholders still need review.

## Potential improvements (not implemented)

- Address observed quote/correction handling without weakening factual grounding.
- Review all subjective checklist items, especially whether corrected numeric facts disagree with the narrative.
- Add broader independently authored scenarios and repeat only under a separately approved API budget.

Raw records: `evaluation/raw_outputs/live-first-v1/`.
Scores: `evaluation/results/live-first-v1/`.
