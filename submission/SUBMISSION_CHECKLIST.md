# Kuku AI Generalist Assignment · Problem 2

Copy-ready values for the placement-cell form. The brief asks for one submission within 48 hours of receiving it. Confirm the exact deadline in the placement-cell message.

| Form item | Value or action |
| --- | --- |
| Name | Enter your name as registered with the placement cell. |
| Roll number | Enter your roll number. |
| Branch | Enter your academic branch. |
| Problem selected | **Problem 2 — Build an AI Lawyer** |
| Project | **NyaySaathi AI** |
| Prototype link, required | <https://nyay-saathi-psi.vercel.app/> |
| Solution document link, required | <https://github.com/kumargulshann/NyaySaathi/releases/download/kuku-problem-2-submission/Kuku_NyaySaathi_Solution.pdf> |
| Raw outputs link, required | <https://github.com/kumargulshann/NyaySaathi/releases/download/kuku-problem-2-submission/Kuku_NyaySaathi_Raw_Outputs.zip> |
| Source code link | <https://github.com/kumargulshann/NyaySaathi> |
| Walkthrough link, optional and recommended | No video link. [Walkthrough script](walkthrough_script.md) for an optional recording of up to three minutes in your own voice. |

The ZIP contains the original live responses in `live-first-v1/` and the frozen fictional cases in `case_inputs/`. If the form requires a browsable folder instead of a download, the public [evaluation folder](https://github.com/kumargulshann/NyaySaathi/tree/e8cf378e1775a0c0bfcf44e046dd279d9f6a2b86/evaluation) contains both the [raw output directory](https://github.com/kumargulshann/NyaySaathi/tree/e8cf378e1775a0c0bfcf44e046dd279d9f6a2b86/evaluation/raw_outputs/live-first-v1) and the [test cases](https://github.com/kumargulshann/NyaySaathi/blob/e8cf378e1775a0c0bfcf44e046dd279d9f6a2b86/evaluation/cases.json).

Before submitting:

- Enter your registered name, roll number and branch. Paste the values above into the corresponding form fields.
- If you include a walkthrough, record it, upload it with link access, and check that the video opens in a private browser window.
- Review the [editable solution](Kuku_NyaySaathi_Solution.md) and the [raw-output audit](RAW_OUTPUT_AUDIT.md), then submit the placement-cell form once.

The project author reported a successful production retest of the corrected conversation and manual voice transcription in English, Hindi and Hinglish. The separate offline suite passed 267 Python and 8 JavaScript tests. These checks did not measure recognition accuracy.

The assignment evaluates problem choice and framing, the split between AI and code and its cost at scale, quality checking backed by real runs and failures, a working prototype, and clear communication. Problem 2 uses original test cases rather than Kuku's microdrama input pack.

To regenerate after editing the Markdown, run `python submission/render_solution.py` from the repository root with ReportLab installed. The renderer uses Segoe UI or DejaVu Sans. Check that the regenerated PDF still fits two A4 pages.
