"""Offline software replay of unchanged Phase 6 outputs, not new model evaluation."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from nyaysaathi.action_package import assess_readiness, generate_package
from nyaysaathi.intake import IntakeError, run_turn
from nyaysaathi.models import CaseFile


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw_outputs" / "live-first-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_originals():
    manifest = json.loads((RAW / "manifest_final.json").read_text(encoding="utf-8"))
    for name, expected in manifest["raw_file_sha256"].items():
        if sha(RAW / name) != expected:
            raise ValueError("Original Phase 6 artifact hash mismatch")
    start = json.loads((RAW / "manifest_start.json").read_text(encoding="utf-8"))
    if sha(ROOT / "cases.json") != start["dataset"]["sha256"]:
        raise ValueError("The original evaluation dataset was changed")
    return manifest


class RecordedProvider:
    """Return original text bytes decoded as UTF-8; never create an SDK client."""

    def __init__(self, path):
        self.path = path
        self.calls = 0
        self.source_ids = []

    def analyze(self, case, messages, language, context=None):
        self.calls += 1
        self.source_ids = [item.source_id for item in context.entries]
        return self.path.read_bytes().decode("utf-8")


def replay(output):
    manifest = verify_originals()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    score_hashes = {path: sha(path) for path in (ROOT / "results" / "live-first-v1").glob("*_scores.json")}
    rows = []
    with patch("google.genai.Client", side_effect=AssertionError("No live clients in Phase 7 replay")) as blocked:
        for case_id in manifest["selected_cases"]:
            current = CaseFile()
            paths = sorted(RAW.glob(f"{case_id}_turn??_record.json"))
            for original_path in paths:
                old = json.loads(original_path.read_text(encoding="utf-8"))
                response_path = RAW / old["original_response_file"]
                provider = RecordedProvider(response_path)
                error = None
                try:
                    result = run_turn(current, old["input_messages"], old["interface_language"], provider)
                    current = result.case
                    reply, status = result.reply, result.guidance.status
                except IntakeError as exc:
                    reply, status, error = None, "unavailable", exc.code
                blocked_scope = status in ("out_of_scope", "urgent_notice", "threat_or_crime")
                readiness = assess_readiness(current, out_of_scope=blocked_scope)
                package = None
                if readiness.provisional_allowed and readiness.status != "out_of_scope":
                    package = generate_package(current, "hi" if case_id == "T03" else "en", provisional=True,
                                               out_of_scope=blocked_scope)
                row = {
                    "label": "Offline replay of a recorded Phase 6 Gemini response; not a new live result or accuracy score",
                    "case_id": case_id, "turn": old["turn"], "live_requests": 0,
                    "original_response": str(response_path.relative_to(ROOT)), "original_response_sha256": sha(response_path),
                    "original_input_messages": old["input_messages"],
                    "before_phase6_case": old["case_after"], "after_fixed_case": current.model_dump(mode="json"),
                    "before_phase6_complaint": (old["action_package"] or {}).get("complaint"),
                    "after_fixed_package": asdict(package) if package else None,
                    "displayed_reply": reply, "guidance_status": status, "application_error": error,
                    "retrieved_source_ids": provider.source_ids, "recorded_provider_calls": provider.calls,
                }
                (output / f"{case_id}_turn{old['turn']:02d}_replay.json").write_text(
                    json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n",
                )
                if package and case_id in ("T05", "T06") and old["turn"] == 2:
                    (output / f"{case_id}_after_complaint.txt").write_text(package.complaint, encoding="utf-8", newline="\n")
                rows.append(row)
        blocked.assert_not_called()
    for path, expected in score_hashes.items():
        if sha(path) != expected:
            raise AssertionError("An original Phase 6 score changed")
    verify_originals()
    targets = {row["case_id"]: row for row in rows if row["case_id"] in ("T05", "T06") and row["turn"] == 2}
    t05, t06 = targets["T05"], targets["T06"]
    assert t05["after_fixed_case"]["amount_inr"] == "2500"
    assert t05["after_fixed_case"]["user_summary"] is None
    assert "2000" not in t05["after_fixed_package"]["complaint"] + t05["after_fixed_package"]["summary"]
    assert t06["after_fixed_case"]["incident_date"] is None
    for text in ("2026-10-03", "3 October 2026", "8 October 2026"):
        assert text not in t06["after_fixed_package"]["complaint"] + t06["after_fixed_package"]["summary"]
    current_files = ["nyaysaathi/models.py", "nyaysaathi/consistency.py", "nyaysaathi/intake.py",
                     "nyaysaathi/action_package.py", "app.py", "evaluation/replay_phase7.py"]
    summary = {
        "label": "Software replay only; original model responses and Phase 6 scores unchanged",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "cases_replayed": len(manifest["selected_cases"]),
        "recorded_responses_replayed": len(rows), "live_requests": 0,
        "T05_regression": "passed", "T06_regression": "passed", "original_artifact_hashes": "verified unchanged",
        "current_source_sha256": {name: sha(ROOT.parent / name) for name in current_files},
        "limitations": "Recorded outputs were not regenerated for the new case metadata/context. This demonstrates corrected software handling, not new live-model reliability.",
    }
    (output / "replay_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    (output / "replay_summary.md").write_text(
        "# Phase 7 offline replay\n\n"
        "Reused all 12 original responses across ten fictional cases with **zero live calls**.\n"
        "Original input conversations were retained and production run_turn/document functions were used.\n\n"
        "| Regression | Original failure | Corrected software output |\n| --- | --- | --- |\n"
        "| T05 | Amount 2500, summary/timeline/complaint still 2000 | Amount 2500 retained; stale narratives cleared; regenerated complaint uses only current amount and review placeholders |\n"
        "| T06 | Date null, summary/timeline/complaint still 3 October | Date stays unknown; stale narratives cleared; no date is arbitrarily selected; regenerated complaint has a date placeholder |\n\n"
        "The earlier narrative is invalidated, not rewritten by string replacement. Other typed facts are retained.\n"
        "Review/provisional generation is required; an existing user's editable draft is never replaced by replay.\n\n"
        "All original raw files and per-turn scores passed unchanged hash checks. No original accuracy score was revised.\n"
        "This is a software regression replay of historical outputs, not a new live Gemini evaluation.\n",
        encoding="utf-8", newline="\n",
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "phase7_replay")
    args = parser.parse_args()
    result = replay(args.output)
    print(f"Replayed {result['recorded_responses_replayed']} stored responses; T05/T06 passed; live requests=0.")


if __name__ == "__main__":
    main()
