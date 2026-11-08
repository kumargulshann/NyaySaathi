"""Offline harness/metric tests only. No paid or live requests are permitted."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from evaluation import run
from evaluation.scoring import observed_diagnostics, score_turn
from nyaysaathi.intake import IntakeError


def test_dataset_is_frozen_fictional_and_exactly_twelve_turns():
    dataset, manifest = run.load_dataset()
    assert [case["id"] for case in dataset["cases"]] == [f"T{number:02d}" for number in range(1, 11)]
    assert sum(len(case["turns"]) for case in dataset["cases"]) == 12
    assert all(case["fictional"] for case in dataset["cases"])
    assert manifest["frozen_before_phase6_live_outputs"]
    assert all("expectations" in turn and "model_output" not in turn for case in dataset["cases"] for turn in case["turns"])


def test_dataset_edits_require_a_new_recorded_version(monkeypatch, tmp_path):
    (tmp_path / "cases.json").write_bytes((run.ROOT / "cases.json").read_bytes() + b" ")
    (tmp_path / "dataset_manifest.json").write_bytes((run.ROOT / "dataset_manifest.json").read_bytes())
    monkeypatch.setattr(run, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Dataset changed"):
        run.load_dataset()


def test_offline_selected_multiturn_run_reuses_production_and_preserves_history(tmp_path, monkeypatch):
    spy = Mock(wraps=run.run_turn)
    monkeypatch.setattr(run, "run_turn", spy)
    result = run.evaluate(run_id="offline-unit", selected=["T04", "T05"], output_root=tmp_path)
    assert result["live_requests_attempted"] == 0
    assert result["turns_recorded"] == 3
    assert spy.call_count == 3
    record = json.loads((tmp_path / "raw_outputs/offline-unit/T05_turn02_record.json").read_text(encoding="utf-8"))
    assert len(record["input_messages"]) == 3
    assert record["input_messages"][1]["role"] == "assistant"
    assert record["case_before"]["amount_inr"] == "2000"
    assert record["case_after"]["amount_inr"] == "2500"
    assert record["response_origin"] == "synthetic_mock"
    assert record["model"] == "OFFLINE_MOCK_NOT_GEMINI"
    assert record["action_package"]["complaint"]
    assert not record["sdk_response_received"]
    scores = json.loads((tmp_path / "results/offline-unit/T05_turn02_scores.json").read_text(encoding="utf-8"))
    assert all(item["status"] == "not reviewed" for item in scores["human_review"])


def test_runs_cannot_overwrite_original_outputs(tmp_path):
    run.evaluate(run_id="immutable", selected=["T01"], output_root=tmp_path)
    response = tmp_path / "raw_outputs/immutable/T01_turn01_response.txt"
    original = response.read_bytes()
    with pytest.raises(FileExistsError):
        run.evaluate(run_id="immutable", selected=["T01"], output_root=tmp_path)
    assert response.read_bytes() == original


def test_sdk_observer_keeps_original_text_and_full_response_without_retry(tmp_path):
    budget = run.Budget(tmp_path, 12)
    capture = run.CaptureProvider(None, tmp_path, "unit", "T01", "live", "test-model", "placeholder-secret", budget)
    capture.turn = 1
    capture.record = {"live_requests_attempted": 0}
    original_text = '{\r\n  "unchanged": "हाँ", "format": "original"\r\n}\n'
    response = SimpleNamespace(text=original_text, model_dump=lambda **kwargs: {
        "candidates": [{"content": {"parts": [{"text": original_text}]}}], "usage_metadata": {"total_token_count": 99},
    })
    original = Mock(return_value=response)
    assert capture.observe_sdk(original, object()) is response
    original.assert_called_once()
    assert (tmp_path / "T01_turn01_response.txt").read_bytes() == original_text.encode("utf-8")
    full = json.loads((tmp_path / "T01_turn01_sdk_response.json").read_text(encoding="utf-8"))
    assert full["usage_metadata"]["total_token_count"] == 99
    assert capture.record["original_response_sha256"] == hashlib.sha256(original_text.encode()).hexdigest()


def test_budget_is_persistent_and_blocks_a_thirteenth_attempt(tmp_path):
    budget = run.Budget(tmp_path, 12)
    for number in range(12):
        budget.reserve("T01", number + 1, "unit")
    restored = run.Budget(tmp_path, 12)
    with pytest.raises(IntakeError, match="evaluation_budget_exhausted"):
        restored.reserve("T10", 1, "different-run-id")
    assert restored.used == 12


def test_failed_sdk_attempt_is_counted_once_and_not_retried(tmp_path):
    capture = run.CaptureProvider(None, tmp_path, "unit", "T01", "live", "test-model", None, run.Budget(tmp_path, 12))
    capture.turn = 1
    capture.record = {"live_requests_attempted": 0}
    original = Mock(side_effect=TimeoutError("not for logging"))
    with pytest.raises(TimeoutError):
        capture.observe_sdk(original, object())
    original.assert_called_once()
    assert capture.record["live_requests_attempted"] == 1
    assert not (tmp_path / "T01_turn01_response.txt").exists()


def test_secret_capture_is_withheld_not_redacted_or_printed(tmp_path, capsys):
    capture = run.CaptureProvider(None, tmp_path, "unit", "T01", "live", "test-model", "dummy-key", None)
    with pytest.raises(IntakeError, match="capture_withheld_possible_secret"):
        capture.safe_capture(tmp_path / "must-not-exist.txt", "response contains dummy-key", raw_text=True)
    assert not (tmp_path / "must-not-exist.txt").exists()
    assert "dummy-key" not in capsys.readouterr().out


def test_live_requires_explicit_flag_and_is_never_allowed_inside_pytest(tmp_path):
    with pytest.raises(SystemExit):
        run.main(["--mode", "live", "--run-id", "forbidden"])
    with pytest.raises(ValueError, match="forbidden inside pytest"):
        run.evaluate(mode="live", run_id="forbidden", output_root=tmp_path)
    assert not (tmp_path / "raw_outputs").exists()


def test_unknown_case_and_excessive_budget_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown or empty"):
        run.evaluate(run_id="bad", selected=["T99"], output_root=tmp_path)
    with pytest.raises(ValueError, match="between 1 and 12"):
        run.evaluate(run_id="bad", max_live_calls=13, output_root=tmp_path)


def test_metrics_distinguish_safe_withholding_from_successful_extraction(tmp_path):
    run.evaluate(run_id="checks", selected=["T01"], output_root=tmp_path)
    record = json.loads((tmp_path / "raw_outputs/checks/T01_turn01_record.json").read_text(encoding="utf-8"))
    dataset, _ = run.load_dataset()
    gold = dataset["cases"][0]["turns"][0]["expectations"]
    record["case_after"]["company_or_seller"] = None
    judged = score_turn(record, gold)
    assert judged["metrics"]["fact_extraction"]["status"] == "fail"
    assert judged["metrics"]["legal_grounding"]["status"] == "pass"
    record["parsed_response"]["changes"][0]["source_quote"] = "not a verbatim user quote"
    assert any("nonverbatim" in item for item in observed_diagnostics(record))


def test_unknown_citation_attempt_is_observed_even_if_not_displayed(tmp_path):
    run.evaluate(run_id="citation", selected=["T07"], output_root=tmp_path)
    record = json.loads((tmp_path / "raw_outputs/citation/T07_turn01_record.json").read_text(encoding="utf-8"))
    record["parsed_response"]["guidance"] = [{"source_id": "FAKE-SOURCE-999", "explanation": "invented"}]
    assert any("nonretrieved citation" in item for item in observed_diagnostics(record))
    assert record["displayed_guidance"]["entries"] == []


def test_rescore_reproduces_checks_and_detects_modified_originals(tmp_path):
    run.evaluate(run_id="reproduce", selected=["T01"], output_root=tmp_path)
    result = run.rescore_saved("reproduce", tmp_path)
    assert result["all_metrics_match"] and result["live_requests_attempted"] == 0
    response = tmp_path / "raw_outputs/reproduce/T01_turn01_response.txt"
    response.write_bytes(response.read_bytes() + b"edited")
    with pytest.raises(ValueError, match="hash mismatch"):
        run.rescore_saved("reproduce", tmp_path)


def test_malformed_model_output_is_preserved_and_validation_errors_are_serializable(tmp_path, monkeypatch):
    raw = '{"scope":"in_scope","reply_language":"en","next_question":"Which date? Which seller?"}'
    monkeypatch.setattr(run.FixtureProvider, "analyze", lambda *args, **kwargs: raw)
    result = run.evaluate(run_id="malformed", selected=["T01"], output_root=tmp_path)
    assert result["turns_recorded"] == 1
    folder = tmp_path / "raw_outputs/malformed"
    assert (folder / "T01_turn01_response.txt").read_bytes() == raw.encode()
    record = json.loads((folder / "T01_turn01_record.json").read_text(encoding="utf-8"))
    assert record["schema_validation"] == "failed"
    assert record["application_error"] == "invalid_output"
    assert record["case_after"]["amount_inr"] is None
