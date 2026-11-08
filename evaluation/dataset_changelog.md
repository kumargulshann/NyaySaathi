# Dataset change log

## Version 1.0 — initial dataset, before the first Phase 6 live run

Ten wholly fictional scenarios, twelve user turns. T05 and T06 have two turns.
Expectations were specified before observing Phase 6 model responses. They are
never included in the model prompt. No scenario has been revised in response
to a score. The SHA-256 in dataset_manifest.json freezes these exact bytes.

Any later change must create a new dataset version and a dated entry here,
explain the reason, retain the original raw results and their dataset hashes,
and regenerate the manifest explicitly. Never silently tune the gold answers
after reading model output. A revised dataset needs a separately authorized live budget.
