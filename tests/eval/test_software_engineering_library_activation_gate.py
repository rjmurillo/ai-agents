"""Tests for the software-engineering-library activation rollback gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval" / "software_engineering_library_activation_gate.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "software-engineering-library-activation.yml"


def _load_gate_module():
    spec = importlib.util.spec_from_file_location(
        "software_engineering_library_activation_gate", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _passing_results() -> dict[str, object]:
    return {
        "rules": {
            reference_id: {"summary": {"verdict": "PASS"}}
            for reference_id in _load_gate_module().MOVED_REFERENCE_IDS
        }
    }


def test_state_tracks_each_moved_reference_and_resets_passes(tmp_path: Path):
    gate = _load_gate_module()
    existing = {
        "references": {
            "refactoring": {
                "consecutive_activation_failures": 1,
                "last_verdict": "FAIL_THRESHOLD",
            }
        }
    }

    state = gate.update_state(
        existing,
        _passing_results(),
        run_id="12345",
        checked_at="2026-07-28T16:00:00Z",
    )

    assert state["owner"] == "agent-qa"
    assert state["cadence"] == "weekly Monday 06:30 UTC and pull_request dry-run gate"
    assert sorted(state["references"]) == sorted(gate.MOVED_REFERENCE_IDS)
    assert state["references"]["refactoring"]["consecutive_activation_failures"] == 0
    assert state["references"]["refactoring"]["last_verdict"] == "PASS"


def test_state_increments_consecutive_failures_and_reports_threshold():
    gate = _load_gate_module()
    results = _passing_results()
    results["rules"]["release-it"] = {"summary": {"verdict": "FAIL_THRESHOLD"}}

    state = gate.update_state(
        {"references": {"release-it": {"consecutive_activation_failures": 1}}},
        results,
        run_id="12346",
        checked_at="2026-07-28T16:00:00Z",
    )
    report = gate.evaluate_thresholds(state, threshold=2)

    assert state["references"]["release-it"]["consecutive_activation_failures"] == 2
    assert state["references"]["release-it"]["last_verdict"] == "FAIL_THRESHOLD"
    assert report["threshold_exceeded"] is True
    assert report["references_at_threshold"] == ["release-it"]


def test_judge_errors_do_not_increment_activation_failure_streak():
    gate = _load_gate_module()
    results = _passing_results()
    results["rules"]["clean-architecture"] = {
        "summary": {"verdict": "FAIL_JUDGE_ERRORS"}
    }

    state = gate.update_state(
        {"references": {"clean-architecture": {"consecutive_activation_failures": 1}}},
        results,
        run_id="12347",
        checked_at="2026-07-28T16:00:00Z",
    )

    reference_state = state["references"]["clean-architecture"]
    assert reference_state["consecutive_activation_failures"] == 1
    assert reference_state["last_verdict"] == "FAIL_JUDGE_ERRORS"
    assert reference_state["last_result_counted_for_rollback"] is False


def test_workflow_runs_weekly_and_invokes_all_moved_reference_scenarios():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = workflow[True]

    assert triggers["schedule"] == [{"cron": "30 6 * * 1"}]
    assert workflow["permissions"] == {
        "contents": "read",
        "issues": "write",
        "actions": "read",
    }

    run_eval_step = next(
        step
        for step in workflow["jobs"]["activation-gate"]["steps"]
        if step["name"] == "Run live activation eval"
    )
    command = run_eval_step["run"]
    for reference_id in _load_gate_module().MOVED_REFERENCE_IDS:
        assert f"tests/evals/rule-scenarios/{reference_id}.json" in command
    assert "software_engineering_library_activation_gate.py" in command
    assert "--fail-on-threshold" in command


def test_documentation_names_owner_cadence_state_and_restoration_pr_policy():
    readme = (REPO_ROOT / "scripts" / "eval" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "Owner: `agent-qa`" in readme
    assert "Cadence: weekly Monday 06:30 UTC" in readme
    assert "consecutive_activation_failures" in readme
    assert "restoration PR" in readme
