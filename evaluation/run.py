"""Sequential CLI evaluation of the production pipeline. Offline by default."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import re
from unittest.mock import patch

from google.genai import errors, models as sdk_models
from pydantic import ValidationError

from nyaysaathi.action_package import assess_readiness, generate_package
from nyaysaathi.gemini import GeminiProvider, SYSTEM_INSTRUCTION
from nyaysaathi.intake import IntakeError, run_turn
from nyaysaathi.knowledge import DATA_FILE
from nyaysaathi.models import CaseFile, IntakeResponse
from nyaysaathi.settings import get_settings
from evaluation.scoring import METRICS, observed_diagnostics, score_turn


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
MAX_LIVE_CALLS = 12


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_once(path, value, *, raw_text=False):
    """Never replace an original response/record, including after a failed run."""
    data = value if raw_text else json.dumps(value, ensure_ascii=False, indent=2)
    with path.open("xb") as stream:
        stream.write(data.encode("utf-8"))


def load_dataset():
    content = (ROOT / "cases.json").read_bytes()
    manifest = json.loads((ROOT / "dataset_manifest.json").read_text(encoding="utf-8"))
    if digest(content) != manifest["sha256"]:
        raise ValueError("Dataset changed: record a new version and change-log entry before evaluation")
    dataset = json.loads(content)
    ids = [case["id"] for case in dataset["cases"]]
    if len(set(ids)) != len(ids) or not all(case["fictional"] for case in dataset["cases"]):
        raise ValueError("Dataset IDs must be unique and scenarios explicitly fictional")
    return dataset, manifest


def resolve_settings():
    """Same precedence as the UI, without ever printing settings/secrets."""
    from streamlit import secrets
    from streamlit.errors import StreamlitSecretNotFoundError
    try:
        values = dict(secrets)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        values = {}
    return get_settings(values)


class Budget:
    """Persistent first-live-run ledger; different run IDs cannot reset the cap."""

    def __init__(self, raw_root, limit):
        self.path = raw_root / "live_budget.json"
        if not self.path.exists():
            write_once(self.path, {"limit": MAX_LIVE_CALLS, "requests": []})
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        self.limit = min(limit, MAX_LIVE_CALLS)

    @property
    def used(self):
        return len(self.data["requests"])

    def reserve(self, case_id, turn, run_id):
        if self.used >= self.limit:
            raise IntakeError("evaluation_budget_exhausted")
        self.data["requests"].append({"run_id": run_id, "case_id": case_id, "turn": turn, "timestamp": now()})
        # This operational ledger is mutable; original responses and turn records are not.
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


@contextmanager
def live_lock(raw_root):
    lock = raw_root / ".live_evaluation.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write("Live evaluation running; do not start another process.\n")
    try:
        yield
    finally:
        lock.unlink()


class FixtureProvider:
    """Explicitly synthetic fixture output, never a simulated live result."""

    def __init__(self, case_id, fixtures):
        self.outputs = iter(fixtures["responses"][case_id])

    def analyze(self, case, messages, language, context=None):
        return json.dumps(next(self.outputs), ensure_ascii=False)


class CaptureProvider:
    def __init__(self, delegate, folder, run_id, case_id, mode, model, secret, budget):
        self.delegate = delegate
        self.folder, self.run_id, self.case_id = folder, run_id, case_id
        self.mode, self.model, self.secret, self.budget = mode, model, secret, budget
        self.turn = 0
        self.record = None
        self.raw = None

    def safe_capture(self, path, value, *, raw_text=False):
        serialized = value if raw_text else json.dumps(value, ensure_ascii=False, indent=2)
        if self.secret and self.secret in serialized:
            raise IntakeError("capture_withheld_possible_secret")
        write_once(path, serialized, raw_text=True)

    def capture_response_text(self, text):
        if self.raw is not None:
            return
        self.raw = text
        filename = f"{self.case_id}_turn{self.turn:02d}_response.txt"
        self.safe_capture(self.folder / filename, text, raw_text=True)
        self.record["original_response_file"] = filename
        self.record["original_response_sha256"] = digest(text.encode("utf-8"))
        self.record["provider_response_received"] = True

    def analyze(self, case, messages, language, context=None):
        self.record["retrieved_records"] = context.as_payload()["records"]
        self.record["retrieval_reasons"] = list(context.reasons)
        self.record["retrieval_safety"] = context.safety
        raw = self.delegate.analyze(case, messages, language, context)
        self.capture_response_text(raw)
        return raw

    def observe_sdk(self, original, sdk_self, *args, **kwargs):
        self.budget.reserve(self.case_id, self.turn, self.run_id)
        self.record["live_requests_attempted"] += 1
        try:
            response = original(sdk_self, *args, **kwargs)
        except errors.APIError as error:
            self.record["http_error_status"] = error.code
            self.record["provider_exception_type"] = type(error).__name__
            # Do not log SDK exceptions, request objects, headers or URLs with credentials.
            raise
        except Exception as error:
            self.record["provider_exception_type"] = type(error).__name__
            raise
        self.record["sdk_response_received"] = True
        self.capture_response_text(response.text or "")
        # Pydantic serialization of the COMPLETE SDK response, not raw HTTP wire bytes.
        filename = f"{self.case_id}_turn{self.turn:02d}_sdk_response.json"
        self.safe_capture(self.folder / filename, response.model_dump(mode="json"))
        self.record["complete_sdk_response_file"] = filename
        return response


def serialize_guidance(view):
    return {"status": view.status, "language": view.language, "message": view.message, "entries": [
        {"source_id": entry.source_id, "explanation": entry.guidance[view.language],
         "source_url": entry.source_url, "source_title": entry.source_title,
         "next_step": entry.next_step[view.language], "limitation": entry.limitation[view.language],
         "provision_or_location": entry.provision_or_location, "date_checked": entry.date_checked.isoformat()}
        for entry in view.entries
    ]}


def provenance():
    files = ["nyaysaathi/intake.py", "nyaysaathi/gemini.py", "nyaysaathi/models.py",
             "nyaysaathi/knowledge.py", "nyaysaathi/guidance.py", "nyaysaathi/action_package.py",
             "evaluation/run.py", "evaluation/scoring.py", "evaluation/mock_responses.json"]
    return {
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("google-genai", "pydantic", "streamlit")},
        "file_sha256": {name: digest((PROJECT / name).read_bytes()) for name in files},
        "knowledge_sha256": digest(DATA_FILE.read_bytes()),
        "system_instruction_sha256": digest(SYSTEM_INSTRUCTION.encode("utf-8")),
        "response_schema": IntakeResponse.model_json_schema(),
    }


def evaluate(*, mode="offline", selected=None, run_id, output_root=ROOT, settings=None, max_live_calls=12):
    if mode not in ("offline", "live") or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        raise ValueError("Invalid mode or run ID")
    if not 1 <= max_live_calls <= MAX_LIVE_CALLS:
        raise ValueError("Live call limit must be between 1 and 12")
    if mode == "live" and "PYTEST_CURRENT_TEST" in os.environ:
        raise ValueError("Live evaluation is forbidden inside pytest")
    dataset, dataset_manifest = load_dataset()
    cases = [case for case in dataset["cases"] if selected is None or case["id"] in selected]
    if not cases or (selected is not None and set(selected) != {case["id"] for case in cases}):
        raise ValueError("Unknown or empty case selection")
    planned = sum(len(case["turns"]) for case in cases)
    root = Path(output_root)
    raw_root, results_root = root / "raw_outputs", root / "results"
    raw_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)
    if (raw_root / run_id).exists() or (results_root / run_id).exists():
        raise FileExistsError("Run already exists; original results cannot be overwritten")
    if mode == "live":
        with live_lock(raw_root):
            budget = Budget(raw_root, max_live_calls)
            if planned > max_live_calls - budget.used:
                raise ValueError("Selected turns exceed the remaining persistent live budget")
            return _evaluate(cases, mode, run_id, raw_root, results_root, dataset_manifest, settings, budget)
    return _evaluate(cases, mode, run_id, raw_root, results_root, dataset_manifest, settings, None)


def _evaluate(cases, mode, run_id, raw_root, results_root, dataset_manifest, settings, budget):
    folder, scores_folder = raw_root / run_id, results_root / run_id
    folder.mkdir()
    scores_folder.mkdir()
    fixtures = json.loads((ROOT / "mock_responses.json").read_text(encoding="utf-8"))
    settings = settings or (resolve_settings() if mode == "live" else None)
    model = settings.gemini_model if mode == "live" else "OFFLINE_MOCK_NOT_GEMINI"
    if mode == "live" and model and not re.fullmatch(r"(?:models/)?gemini-[A-Za-z0-9._-]+", model):
        raise ValueError("Unexpected model identifier; refusing to print or store it")
    manifest = {
        "run_id": run_id, "mode": mode, "model": model, "started_at": now(),
        "dataset": dataset_manifest, "selected_cases": [case["id"] for case in cases],
        "planned_turns": sum(len(case["turns"]) for case in cases),
        "provenance": provenance(), "automatic_retries": 0,
        "action_policy": "Explicitly request deterministic provisional documents at each turn when production readiness allows.",
        "capture_format": "Exact response.text UTF-8 bytes plus complete SDK Pydantic serialization; not raw HTTP wire bytes.",
    }
    write_once(folder / "manifest_start.json", manifest)
    records, scores = [], []
    stop_reason = None
    if mode == "live" and (not settings.gemini_api_key or not settings.gemini_model):
        stop_reason = "missing_configuration"
    for scenario in cases:
        if stop_reason:
            break
        delegate = GeminiProvider(settings) if mode == "live" else FixtureProvider(scenario["id"], fixtures)
        capture = CaptureProvider(delegate, folder, run_id, scenario["id"], mode, model,
                                  settings.gemini_api_key if mode == "live" else None, budget)
        case, messages = CaseFile(), []
        for number, turn_spec in enumerate(scenario["turns"], 1):
            messages.append({"role": "user", "content": turn_spec["message"]})
            record = {
                "run_id": run_id, "case_id": scenario["id"], "turn": number,
                "mode": mode, "response_origin": "live_gemini" if mode == "live" else "synthetic_mock",
                "model": model, "timestamp": now(), "input_messages": [dict(item) for item in messages],
                "interface_language": scenario["interface_language"], "case_before": case.model_dump(mode="json"),
                "retrieved_records": [], "retrieval_reasons": [], "live_requests_attempted": 0,
                "provider_response_received": False, "sdk_response_received": False,
                "parsed_response": None, "schema_validation": "no_response", "application_processing": "not_completed",
                "displayed_reply": None, "displayed_guidance": None, "action_package": None,
                "original_response_file": None, "complete_sdk_response_file": None,
            }
            capture.turn, capture.record, capture.raw = number, record, None
            try:
                original = sdk_models.Models.generate_content

                def observed(sdk_self, *args, **kwargs):
                    return capture.observe_sdk(original, sdk_self, *args, **kwargs)

                with patch.object(sdk_models.Models, "generate_content", new=observed) if mode == "live" else _offline_guard():
                    outcome = run_turn(case, messages, scenario["interface_language"], capture)
                case = outcome.case
                record.update(application_processing="completed", displayed_reply=outcome.reply,
                              displayed_guidance=serialize_guidance(outcome.guidance), intake_error=outcome.intake_error)
                messages.append({"role": "assistant", "content": outcome.reply})
            except IntakeError as error:
                if error.code in ("invalid_output",):
                    record["application_error"] = error.code
                else:
                    record["provider_error"] = error.code
                    stop_reason = error.code
            except Exception as error:
                record["unexpected_error_type"] = type(error).__name__
                stop_reason = "unexpected_evaluation_error"
            if capture.raw is not None:
                try:
                    record["parsed_response"] = IntakeResponse.model_validate_json(capture.raw).model_dump(mode="json")
                    record["schema_validation"] = "passed"
                except ValidationError as error:
                    record["schema_validation"] = "failed"
                    record["schema_errors"] = error.errors(include_input=False, include_url=False, include_context=False)
            record["case_after"] = case.model_dump(mode="json")
            blocked = (record.get("displayed_guidance") or {}).get("status") in ("out_of_scope", "urgent_notice", "threat_or_crime")
            readiness = assess_readiness(case, out_of_scope=blocked)
            record["readiness"] = asdict(readiness)
            if record["application_processing"] == "completed" and readiness.status != "out_of_scope" and readiness.provisional_allowed:
                package = generate_package(case, scenario["document_language"], provisional=True, out_of_scope=blocked)
                record["action_package"] = asdict(package)
                record["provisional_generation_explicitly_requested_by_evaluation"] = True
            record["completed_at"] = now()
            capture.safe_capture(folder / f"{scenario['id']}_turn{number:02d}_record.json", record)
            judged = score_turn(record, turn_spec["expectations"])
            judged.update(case_id=scenario["id"], turn=number, mode=mode,
                          observations=observed_diagnostics(record), raw_record=f"{scenario['id']}_turn{number:02d}_record.json")
            write_once(scores_folder / f"{scenario['id']}_turn{number:02d}_scores.json", judged)
            records.append(record)
            scores.append(judged)
            print(f"{mode.upper()} {scenario['id']} turn {number}: schema={record['schema_validation']}; "
                  f"application={record['application_processing']}; checks={'pass' if judged['all_applicable_deterministic_checks_pass'] else 'fail'}", flush=True)
            if stop_reason:
                break
    final = {
        "run_id": run_id, "mode": mode, "model": model, "finished_at": now(),
        "selected_cases": [case["id"] for case in cases], "planned_turns": manifest["planned_turns"],
        "live_requests_attempted": sum(record["live_requests_attempted"] for record in records),
        "provider_responses_received": sum(record["provider_response_received"] for record in records),
        "turns_recorded": len(records), "stop_reason": stop_reason,
        "cases_completed": [case["id"] for case in cases if sum(record["case_id"] == case["id"] for record in records) == len(case["turns"])],
        "cases_with_all_deterministic_checks_passing": [case["id"] for case in cases if
            len([score for score in scores if score["case_id"] == case["id"]]) == len(case["turns"]) and
            all(score["all_applicable_deterministic_checks_pass"] for score in scores if score["case_id"] == case["id"])],
        "metric_totals": {name: {
            "passed_checks": sum(score["metrics"][name]["passed_checks"] for score in scores),
            "total_checks": sum(score["metrics"][name]["total_checks"] for score in scores),
        } for name in METRICS},
        "subjective_review": "not reviewed",
        "raw_file_sha256": {path.name: digest(path.read_bytes()) for path in sorted(folder.iterdir()) if path.is_file()},
    }
    write_once(folder / "manifest_final.json", final)
    write_once(scores_folder / "aggregate.json", final)
    summary = render_summary(final, records, scores)
    (scores_folder / "evaluation_summary.md").write_text(summary, encoding="utf-8")
    canonical = results_root / "evaluation_summary.md"
    if mode == "live" or not canonical.exists():
        canonical.write_text(summary, encoding="utf-8")
    else:
        (results_root / "offline_evaluation_summary.md").write_text(summary, encoding="utf-8")
    return final


def rescore_saved(run_id, output_root=ROOT):
    """Check original hashes and recompute checks without changing raw files or calling Gemini."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        raise ValueError("Invalid saved run ID")
    root = Path(output_root)
    folder = root / "raw_outputs" / run_id
    start = json.loads((folder / "manifest_start.json").read_text(encoding="utf-8"))
    final = json.loads((folder / "manifest_final.json").read_text(encoding="utf-8"))
    dataset, manifest = load_dataset()
    if start["dataset"]["sha256"] != manifest["sha256"]:
        raise ValueError("Original dataset version required to rescore this run")
    for name, expected_hash in final.get("raw_file_sha256", {}).items():
        if Path(name).name != name or digest((folder / name).read_bytes()) != expected_hash:
            raise ValueError("Original raw output hash mismatch")
    comparisons = []
    by_id = {case["id"]: case for case in dataset["cases"]}
    for path in sorted(folder.glob("*_record.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["original_response_file"]:
            if digest((folder / record["original_response_file"]).read_bytes()) != record["original_response_sha256"]:
                raise ValueError("Original model text changed")
        recomputed = score_turn(record, by_id[record["case_id"]]["turns"][record["turn"] - 1]["expectations"])
        original = json.loads((root / "results" / run_id / path.name.replace("_record", "_scores")).read_text(encoding="utf-8"))
        comparisons.append({"case_id": record["case_id"], "turn": record["turn"],
                            "metrics_match_original": recomputed["metrics"] == original["metrics"]})
    result = {"run_id": run_id, "recomputed_at": now(), "live_requests_attempted": 0,
              "all_metrics_match": all(item["metrics_match_original"] for item in comparisons), "turns": comparisons}
    write_once(root / "results" / run_id / "recomputed_checks.json", result)
    return result


@contextmanager
def _offline_guard():
    with patch("google.genai.Client", side_effect=AssertionError("Offline evaluation cannot construct a Gemini client")):
        yield


def render_summary(final, records, scores):
    lines = ["# NyaySaathi evaluation summary", "", f"Mode: **{final['mode']}**. Model: `{final['model']}`.",
             "Synthetic mock runs are NOT evidence of real-model quality." if final["mode"] == "offline" else "Original Gemini outputs are retained without edits.",
             "", f"- Total selected cases: {len(final['selected_cases'])}",
             f"- Planned user turns: {final['planned_turns']}",
             f"- Live requests attempted: {final['live_requests_attempted']}",
             f"- Responses received: {final['provider_responses_received']}",
             f"- Cases with all planned turns recorded: {len(final['cases_completed'])}",
             f"- Cases passing all applicable deterministic checks: {len(final['cases_with_all_deterministic_checks_passing'])}",
             f"- Stop reason: {final['stop_reason'] or 'none'}", "", "## Deterministic metrics", "",
             "Counts are predefined checks, not a general accuracy estimate. Safe rejection can preserve safety while failing task completion.",
             "", "| Criterion | Checks passed / applicable |", "| --- | --- |"]
    for name, counts in final["metric_totals"].items():
        lines.append(f"| {name} | {counts['passed_checks']} / {counts['total_checks']} |")
    lines += ["", "## Per-case observations", "", "| Case / turn | Deterministic result | Observed failures or withholding |", "| --- | --- | --- |"]
    for score in scores:
        failed = [name for name, metric in score["metrics"].items() if metric["status"] == "fail"]
        notes = score["observations"] + (["failed metrics: " + ", ".join(failed)] if failed else [])
        lines.append(f"| {score['case_id']} / {score['turn']} | {'pass' if not failed else 'fail'} | {'; '.join(notes) or 'No mechanical failure detected'} |")
    lines += ["", "## Human review — not reviewed", "",
              "Every turn score file contains an uncompleted human-review checklist. Fluency, relevance, real-world actionability, "
              "semantic evidence accuracy, narrative consistency, and professional legal appropriateness have NOT been scored.",
              "", "## Failure examples and limitations", ""]
    failures = [score for score in scores if score["observations"] or not score["all_applicable_deterministic_checks_pass"]]
    for score in failures:
        lines.append(f"- {score['case_id']} turn {score['turn']}: see `{score['raw_record']}` and its unchanged `*_response.txt`. "
                     "The corresponding score file lists exact failed checks; no response was rewritten.")
    if not failures:
        lines.append("No mechanical failure was observed in this run; this does not establish correctness or legal accuracy.")
    lines += ["", "- Ten hand-selected fictional scenarios are too small for general accuracy claims.",
              "- Keyword/field checks are proxies, not semantic or professional legal assessment.",
              "- Results cover production business functions and generated UI-ready data, not a browser interaction audit.",
              "- Model sampling, server behavior, dependency versions and knowledge review dates can change outcomes.",
              "- Source text and application versions are pinned by hashes in the start manifest. No live source update was performed.",
              "- Readiness is a draft-preparation status, not legal completeness; placeholders still need review.",
              "", "## Potential improvements (not implemented)", "",
              "- Address observed quote/correction handling without weakening factual grounding.",
              "- Review all subjective checklist items, especially whether corrected numeric facts disagree with the narrative.",
              "- Add broader independently authored scenarios and repeat only under a separately approved API budget.",
              "", f"Raw records: `evaluation/raw_outputs/{final['run_id']}/`.",
              f"Scores: `evaluation/results/{final['run_id']}/`.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--allow-live", action="store_true", help="Explicitly authorize the live run; never used by pytest")
    parser.add_argument("--cases", nargs="+", help="Case IDs, for example T01 T05")
    parser.add_argument("--run-id", help="New unique directory name; outputs are never replaced")
    parser.add_argument("--rescore-run", help="Recompute saved metric checks offline; does not change original responses")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--max-live-calls", type=int, default=12)
    args = parser.parse_args(argv)
    if args.rescore_run:
        if args.mode != "offline" or args.allow_live or args.run_id or args.cases:
            parser.error("--rescore-run is an offline-only operation and takes no new run ID/cases")
        try:
            result = rescore_saved(args.rescore_run, args.output_root)
        except Exception as error:
            print("Rescoring stopped safely:", type(error).__name__)
            return 2
        print(f"Recomputed {len(result['turns'])} turns; metrics match={result['all_metrics_match']}; live requests=0.")
        return 0 if result["all_metrics_match"] else 1
    if not args.run_id:
        parser.error("--run-id is required for a new evaluation")
    if args.mode == "live" and not args.allow_live:
        parser.error("Live mode requires --allow-live; it can consume quota or incur charges")
    # Avoid verbose vendor/transport logging that could expose credentials.
    for name in ("google.genai", "httpx", "httpcore"):
        logging.getLogger(name).disabled = True
    try:
        final = evaluate(mode=args.mode, selected=args.cases, run_id=args.run_id,
                         output_root=args.output_root, max_live_calls=args.max_live_calls)
    except Exception as error:
        print("Evaluation stopped safely:", type(error).__name__, "(no exception payload or secrets printed)")
        return 2
    print(f"Recorded {final['turns_recorded']} turns; live requests={final['live_requests_attempted']}; mode={final['mode']}.")
    return 2 if final["stop_reason"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
