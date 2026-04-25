"""Unit tests for scripts/eval/eval-prompt-change.py rubric and validation.

Targets the controlled-vocabulary verdict matching introduced for issue #1755:
- check_scenario_pass: exact match on canonical verdict + reason substring
- _verdict_options: defaults to [expected, OTHER]; honors explicit verdict_options
- load_scenarios: validates verdict_options shape and consistency
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
sys.path.insert(0, str(EVAL_DIR))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "eval_prompt_change", EVAL_DIR / "eval-prompt-change.py"
)
assert _spec and _spec.loader
eval_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_mod)


# ---------------------------------------------------------------------------
# check_scenario_pass
# ---------------------------------------------------------------------------

class TestCheckScenarioPass:
    def test_exact_verdict_match_passes(self):
        result = {"verdict": "ROUTE", "reason": "delegate to analyst"}
        scenario = {"expected_verdict": "ROUTE"}
        assert eval_mod.check_scenario_pass(result, scenario) is True

    def test_case_insensitive_verdict_match(self):
        result = {"verdict": "route", "reason": "x"}
        scenario = {"expected_verdict": "ROUTE"}
        assert eval_mod.check_scenario_pass(result, scenario) is True

    def test_mismatched_verdict_fails(self):
        result = {"verdict": "EXECUTE", "reason": "x"}
        scenario = {"expected_verdict": "ROUTE"}
        assert eval_mod.check_scenario_pass(result, scenario) is False

    def test_reason_contains_required_substring(self):
        result = {"verdict": "ROUTE", "reason": "delegate to analyst"}
        scenario = {
            "expected_verdict": "ROUTE",
            "expected_reason_contains": "analyst",
        }
        assert eval_mod.check_scenario_pass(result, scenario) is True

    def test_reason_contains_missing_fails(self):
        result = {"verdict": "ROUTE", "reason": "fix it now"}
        scenario = {
            "expected_verdict": "ROUTE",
            "expected_reason_contains": "analyst",
        }
        assert eval_mod.check_scenario_pass(result, scenario) is False

    def test_reason_contains_case_insensitive(self):
        result = {"verdict": "IDENTIFY", "reason": "Detected CWE-22 issue"}
        scenario = {
            "expected_verdict": "IDENTIFY",
            "expected_reason_contains": "cwe-22",
        }
        assert eval_mod.check_scenario_pass(result, scenario) is True

    def test_empty_reason_contains_field_ignored(self):
        result = {"verdict": "ROUTE", "reason": ""}
        scenario = {
            "expected_verdict": "ROUTE",
            "expected_reason_contains": "",
        }
        assert eval_mod.check_scenario_pass(result, scenario) is True

    def test_parse_error_verdict_fails(self):
        result = {"verdict": "PARSE_ERROR", "reason": "could not parse"}
        scenario = {"expected_verdict": "IDENTIFY"}
        assert eval_mod.check_scenario_pass(result, scenario) is False


# ---------------------------------------------------------------------------
# _verdict_options
# ---------------------------------------------------------------------------

class TestVerdictOptions:
    def test_defaults_to_expected_plus_other(self):
        scenario = {"expected_verdict": "ROUTE"}
        assert eval_mod._verdict_options(scenario) == ["ROUTE", "OTHER"]

    def test_uses_explicit_options(self):
        scenario = {
            "expected_verdict": "ROUTE",
            "verdict_options": ["ROUTE", "DELEGATE", "EXECUTE"],
        }
        assert eval_mod._verdict_options(scenario) == ["ROUTE", "DELEGATE", "EXECUTE"]

    def test_uppercases_explicit_options(self):
        scenario = {
            "expected_verdict": "produce",
            "verdict_options": ["produce", "blocked"],
        }
        assert eval_mod._verdict_options(scenario) == ["PRODUCE", "BLOCKED"]

    def test_no_duplicate_other_when_expected_is_other(self):
        scenario = {"expected_verdict": "OTHER"}
        assert eval_mod._verdict_options(scenario) == ["OTHER"]


# ---------------------------------------------------------------------------
# load_scenarios validation
# ---------------------------------------------------------------------------

class TestLoadScenariosValidation:
    @staticmethod
    def _write(tmp_path: Path, payload: dict) -> str:
        p = tmp_path / "scen.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return str(p)

    def test_valid_with_options(self, tmp_path):
        path = self._write(tmp_path, {
            "scenarios": [{
                "id": "S1", "desc": "x", "input": "y",
                "expected_verdict": "ROUTE",
                "verdict_options": ["ROUTE", "DELEGATE"],
            }]
        })
        scenarios = eval_mod.load_scenarios(path)
        assert len(scenarios) == 1

    def test_rejects_options_not_list(self, tmp_path):
        path = self._write(tmp_path, {
            "scenarios": [{
                "id": "S1", "desc": "x", "input": "y",
                "expected_verdict": "ROUTE",
                "verdict_options": "ROUTE,DELEGATE",
            }]
        })
        with pytest.raises(RuntimeError, match="non-empty list"):
            eval_mod.load_scenarios(path)

    def test_rejects_empty_options_list(self, tmp_path):
        path = self._write(tmp_path, {
            "scenarios": [{
                "id": "S1", "desc": "x", "input": "y",
                "expected_verdict": "ROUTE",
                "verdict_options": [],
            }]
        })
        with pytest.raises(RuntimeError, match="non-empty list"):
            eval_mod.load_scenarios(path)

    def test_rejects_expected_not_in_options(self, tmp_path):
        path = self._write(tmp_path, {
            "scenarios": [{
                "id": "S1", "desc": "x", "input": "y",
                "expected_verdict": "ROUTE",
                "verdict_options": ["DELEGATE", "EXECUTE"],
            }]
        })
        with pytest.raises(RuntimeError, match="not in verdict_options"):
            eval_mod.load_scenarios(path)

    def test_accepts_no_options(self, tmp_path):
        path = self._write(tmp_path, {
            "scenarios": [{
                "id": "S1", "desc": "x", "input": "y",
                "expected_verdict": "ROUTE",
            }]
        })
        scenarios = eval_mod.load_scenarios(path)
        assert scenarios[0]["expected_verdict"] == "ROUTE"

    def test_rejects_missing_required_field(self, tmp_path):
        path = self._write(tmp_path, {
            "scenarios": [{"id": "S1", "desc": "x", "input": "y"}]  # no expected_verdict
        })
        with pytest.raises(RuntimeError, match="missing required fields"):
            eval_mod.load_scenarios(path)


# ---------------------------------------------------------------------------
# Shipped scenario files load and remain consistent
# ---------------------------------------------------------------------------

class TestShippedScenariosValid:
    def _scenario_files(self):
        return sorted((REPO_ROOT / "tests" / "evals").glob("*-scenarios.json"))

    def test_all_scenario_files_load(self):
        for path in self._scenario_files():
            scenarios = eval_mod.load_scenarios(str(path))
            assert scenarios, f"no scenarios in {path.name}"

    def test_all_scenarios_declare_verdict_options(self):
        # Issue #1755: every shipped scenario must declare verdict_options to
        # constrain LLM output to a controlled vocabulary.
        for path in self._scenario_files():
            scenarios = eval_mod.load_scenarios(str(path))
            for s in scenarios:
                assert "verdict_options" in s, (
                    f"{path.name} scenario {s['id']} missing verdict_options"
                )
                assert len(s["verdict_options"]) >= 2, (
                    f"{path.name} scenario {s['id']} verdict_options must "
                    f"offer at least 2 choices"
                )
