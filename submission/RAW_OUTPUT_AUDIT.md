# Raw-output audit · Original live run

**Submission archive** [Kuku_NyaySaathi_Raw_Outputs.zip](https://github.com/kumargulshann/NyaySaathi/releases/download/kuku-problem-2-submission/Kuku_NyaySaathi_Raw_Outputs.zip). The archive keeps original evidence separate from the score commentary and later regression outputs. The integrity and privacy checks below were repeated for publication in Phase 16.

| Archive path | Contents |
| --- | --- |
| `live-first-v1/Txx_turnNN_response.txt` | 12 original UTF-8 Gemini text responses, captured before application validation. |
| `live-first-v1/Txx_turnNN_sdk_response.json` | 12 complete serialized Gemini SDK responses with candidate and usage data. These are SDK serializations rather than HTTP wire captures. |
| `live-first-v1/Txx_turnNN_record.json` | 12 original turn records with the input conversation, retrieval context, validation and the actual case and document outputs. |
| `live-first-v1/manifest_start.json`, `manifest_final.json` | Original provenance, run totals and recorded SHA-256 hashes. |
| `case_inputs/cases.json`, `dataset_manifest.json` | Frozen fictional test cases, expectations and their dataset hash. The expectations were withheld from the model. |

## Integrity and privacy checks

- All **37** raw-artifact SHA-256 values matched the frozen final manifest. The final manifest itself matched the original aggregate. The cases file matched both dataset manifests.
- All **12** saved text responses matched the text returned by reading their original SDK captures offline. The turn IDs and submitted user messages matched all **10** frozen fictional cases. No output was redacted, reformatted or regenerated.
- The ZIP's **40** entries were read back and compared byte for byte with the source files. The original evidence and scores stayed unchanged.
- Archive SHA-256: `053f9526c7c35c15dcdc6a9a648801602bcce4ea72e00a8d322f27d8df29eda5`.
- The audit checked the active-key value in memory, known credential patterns, sensitive SDK header names, email and personal mobile-number patterns, URL hosts, and the fictional case and recorded fact contents. No credentials, private personal information or unrelated confidential material were found in the reviewed inputs and captures. URLs detected in the archive sources used the official Department of Consumer Affairs and National Consumer Helpline domains. The assignment PDF, environment files, offline mock data, post-run scores and commentary are outside the ZIP.

## Evidence boundaries

The original live run completed 10 fictional cases with 12 requests and 12 responses. Eight cases passed all predefined checks. T03 and T07 failed the automated gate. Later engineering inspection found stale narrative in T05 and T06 despite correct scalar updates. The Phase 7 replay and later regressions are software verification, separate from those original scores. The project author's later manual production and voice checks do not rescore the run. Human-review checklist items remain unscored.

[Original evaluation report](../evaluation/results/evaluation_summary.md) · [Failure analysis](../evaluation/results/failure_analysis.md) · [Offline correction replay](../evaluation/results/phase7_replay/replay_summary.md) · [Later text smoke tests](../DEPLOYMENT_VERIFICATION.md) · [Voice parsing evidence](../VOICE_DEBUG.md)
