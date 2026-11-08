# Phase 7 offline replay

Reused all 12 original responses across ten fictional cases with **zero live calls**.
Original input conversations were retained and production run_turn/document functions were used.

| Regression | Original failure | Corrected software output |
| --- | --- | --- |
| T05 | Amount 2500, summary/timeline/complaint still 2000 | Amount 2500 retained; stale narratives cleared; regenerated complaint uses only current amount and review placeholders |
| T06 | Date null, summary/timeline/complaint still 3 October | Date stays unknown; stale narratives cleared; no date is arbitrarily selected; regenerated complaint has a date placeholder |

The earlier narrative is invalidated, not rewritten by string replacement. Other typed facts are retained.
Review/provisional generation is required; an existing user's editable draft is never replaced by replay.

All original raw files and per-turn scores passed unchanged hash checks. No original accuracy score was revised.
This is a software regression replay of historical outputs, not a new live Gemini evaluation.
