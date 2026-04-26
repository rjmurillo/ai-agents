"""Unit tests for scripts/eval/eval-prompt-change.py rubric and validation.

Targets the controlled-vocabulary verdict matching introduced for issue #1755:
- check_scenario_pass: exact match on canonical verdict + reason substring
- _verdict_options: defaults to [expected, OTHER]; honors explicit verdict_options
- load_scenarios: validates verdict_options shape and consistency
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"

# eval-prompt-change.py imports sibling modules (_anthropic_api, _eval_common)
# via plain `from X import Y` statements, so EVAL_DIR must be on sys.path
# while the module is loaded. Scope the mutation to the load itself and
# remove it afterward so the test file does not change import resolution
# for any other test module in the run.
_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    _spec = importlib.util.spec_from_file_location(
        "eval_prompt_change", EVAL_DIR / "eval-prompt-change.py"
    )
    assert _spec and _spec.loader
    eval_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(eval_mod)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


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

    def test_rejects_non_dict_scenario_entry(self, tmp_path):
        # PR #1756 review (Copilot): non-object entries must raise RuntimeError,
        # not AttributeError/TypeError.
        path = self._write(tmp_path, {"scenarios": ["not-an-object"]})
        with pytest.raises(RuntimeError, match="not a JSON object"):
            eval_mod.load_scenarios(path)

    def test_strips_whitespace_when_validating_expected_in_options(self, tmp_path):
        # PR #1756 review (gemini): leading/trailing whitespace in JSON must
        # not break the expected-in-options check.
        path = self._write(tmp_path, {
            "scenarios": [{
                "id": "S1", "desc": "x", "input": "y",
                "expected_verdict": "  ROUTE  ",
                "verdict_options": [" ROUTE ", "DELEGATE"],
            }]
        })
        scenarios = eval_mod.load_scenarios(path)
        assert scenarios[0]["expected_verdict"] == "  ROUTE  "  # raw preserved


# ---------------------------------------------------------------------------
# Whitespace and prompt-construction edge cases (PR #1756 review)
# ---------------------------------------------------------------------------

class TestWhitespaceHandling:
    def test_check_scenario_pass_strips_actual_verdict(self):
        result = {"verdict": "  ROUTE  ", "reason": "x"}
        scenario = {"expected_verdict": "ROUTE"}
        assert eval_mod.check_scenario_pass(result, scenario) is True

    def test_check_scenario_pass_strips_expected_verdict(self):
        result = {"verdict": "ROUTE", "reason": "x"}
        scenario = {"expected_verdict": " ROUTE\n"}
        assert eval_mod.check_scenario_pass(result, scenario) is True

    def test_verdict_options_strips_explicit_options(self):
        scenario = {
            "expected_verdict": "ROUTE",
            "verdict_options": [" ROUTE ", "\tDELEGATE\n"],
        }
        assert eval_mod._verdict_options(scenario) == ["ROUTE", "DELEGATE"]

    def test_verdict_options_strips_default_expected(self):
        scenario = {"expected_verdict": " ROUTE\n"}
        assert eval_mod._verdict_options(scenario) == ["ROUTE", "OTHER"]


class TestJudgePromptConstruction:
    """PR #1756 review (Copilot): the OTHER fallback hint must only appear
    when OTHER is actually in the controlled vocabulary."""

    def _build_user_message(self, scenario):
        # Replicate the user-message construction logic from judge_scenario
        # without requiring an actual API call.
        options = eval_mod._verdict_options(scenario)
        options_str = ", ".join(options)
        fallback_hint = ""
        if eval_mod.DEFAULT_FALLBACK_VERDICT in options:
            fallback_hint = (
                f"Use {eval_mod.DEFAULT_FALLBACK_VERDICT} only if no other "
                f"label fits.\n"
            )
        return (
            f"Scenario: {scenario['desc']}\n\n"
            f"Context:\n{scenario['input']}\n\n"
            "Based on your instructions, classify your action.\n"
            f"Your verdict MUST be exactly one of these labels (uppercase, "
            f"no extra words): {options_str}.\n"
            f"{fallback_hint}"
            "Respond with a JSON object only, no surrounding prose: "
            '{"verdict": "<one of the labels>", "reason": "<brief explanation>"}'
        )

    def test_other_hint_present_when_other_in_options(self):
        scenario = {"id": "S", "desc": "d", "input": "i", "expected_verdict": "ROUTE"}
        msg = self._build_user_message(scenario)
        assert "Use OTHER only if no other label fits" in msg

    def test_other_hint_absent_when_options_explicit_and_no_other(self):
        scenario = {
            "id": "S", "desc": "d", "input": "i",
            "expected_verdict": "ROUTE",
            "verdict_options": ["ROUTE", "DELEGATE", "EXECUTE"],
        }
        msg = self._build_user_message(scenario)
        assert "OTHER" not in msg
        # Only ROUTE/DELEGATE/EXECUTE appear as label tokens
        assert "ROUTE, DELEGATE, EXECUTE" in msg

    def test_other_hint_present_when_options_explicit_includes_other(self):
        scenario = {
            "id": "S", "desc": "d", "input": "i",
            "expected_verdict": "ROUTE",
            "verdict_options": ["ROUTE", "OTHER"],
        }
        msg = self._build_user_message(scenario)
        assert "Use OTHER only if no other label fits" in msg


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


# ---------------------------------------------------------------------------
# load_scenarios error paths
# ---------------------------------------------------------------------------

class TestLoadScenariosErrorPaths:
    def test_file_not_found(self, tmp_path):
        missing = tmp_path / "does-not-exist.json"
        with pytest.raises(RuntimeError, match="not found"):
            eval_mod.load_scenarios(str(missing))

    def test_invalid_json_decode_error(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Invalid JSON"):
            eval_mod.load_scenarios(str(p))

    def test_top_level_not_object_or_list_rejected(self, tmp_path):
        p = tmp_path / "scen.json"
        p.write_text(json.dumps("just-a-string"), encoding="utf-8")
        with pytest.raises(RuntimeError, match="expected 'scenarios' array"):
            eval_mod.load_scenarios(str(p))

    def test_empty_scenarios_array_rejected(self, tmp_path):
        p = tmp_path / "scen.json"
        p.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="0 scenarios"):
            eval_mod.load_scenarios(str(p))

    def test_top_level_array_form_accepted(self, tmp_path):
        # Spec allows either {"scenarios": [...]} or top-level [...]
        p = tmp_path / "scen.json"
        p.write_text(json.dumps([{
            "id": "S1", "desc": "d", "input": "i", "expected_verdict": "OK",
        }]), encoding="utf-8")
        scenarios = eval_mod.load_scenarios(str(p))
        assert len(scenarios) == 1


# ---------------------------------------------------------------------------
# load_prompt_from_file
# ---------------------------------------------------------------------------

class TestLoadPromptFromFile:
    def test_loads_existing_file(self, tmp_path):
        p = tmp_path / "prompt.md"
        p.write_text("hello prompt", encoding="utf-8")
        assert eval_mod.load_prompt_from_file(str(p)) == "hello prompt"

    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "absent.md"
        with pytest.raises(RuntimeError, match="not found"):
            eval_mod.load_prompt_from_file(str(missing))


# ---------------------------------------------------------------------------
# load_prompt_from_ref (subprocess-mocked)
# ---------------------------------------------------------------------------

class TestLoadPromptFromRef:
    def test_returns_stdout_on_success(self, monkeypatch):
        from subprocess import CompletedProcess

        def fake_run(*args, **kwargs):
            return CompletedProcess(args, 0, stdout="prompt content", stderr="")

        monkeypatch.setattr(eval_mod.subprocess, "run", fake_run)
        out = eval_mod.load_prompt_from_ref("path.md", "main")
        assert out == "prompt content"

    def test_called_process_error_raises(self, monkeypatch):
        from subprocess import CalledProcessError

        def fake_run(*args, **kwargs):
            raise CalledProcessError(1, args, stderr="bad ref\n")

        monkeypatch.setattr(eval_mod.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="Cannot load"):
            eval_mod.load_prompt_from_ref("path.md", "no-such-ref")

    def test_timeout_raises(self, monkeypatch):
        from subprocess import TimeoutExpired

        def fake_run(*args, **kwargs):
            raise TimeoutExpired(args, 30)

        monkeypatch.setattr(eval_mod.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="Timed out"):
            eval_mod.load_prompt_from_ref("path.md", "main")


# ---------------------------------------------------------------------------
# judge_scenario (call_api mocked)
# ---------------------------------------------------------------------------

class TestJudgeScenario:
    SCENARIO = {
        "id": "S1", "desc": "d", "input": "i",
        "expected_verdict": "ROUTE",
        "verdict_options": ["ROUTE", "DELEGATE"],
    }

    def _patch_call_api(self, monkeypatch, response: str):
        captured = {}

        def fake(api_key, messages, system, model, max_tokens):
            captured["api_key"] = api_key
            captured["messages"] = messages
            captured["system"] = system
            captured["model"] = model
            return response

        monkeypatch.setattr(eval_mod, "call_api", fake)
        return captured

    def test_parses_plain_json_response(self, monkeypatch):
        self._patch_call_api(monkeypatch, '{"verdict": "ROUTE", "reason": "ok"}')
        out = eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        assert out["verdict"] == "ROUTE"
        assert out["reason"] == "ok"
        assert out["raw"] == '{"verdict": "ROUTE", "reason": "ok"}'

    def test_strips_code_fences(self, monkeypatch):
        self._patch_call_api(
            monkeypatch,
            '```json\n{"verdict": "DELEGATE", "reason": "fenced"}\n```',
        )
        out = eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        assert out["verdict"] == "DELEGATE"
        assert out["reason"] == "fenced"

    def test_extracts_json_from_surrounding_text(self, monkeypatch):
        self._patch_call_api(
            monkeypatch,
            'My analysis: {"verdict": "ROUTE", "reason": "found"} done.',
        )
        out = eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        assert out["verdict"] == "ROUTE"

    def test_unparseable_response_returns_parse_error(self, monkeypatch):
        self._patch_call_api(monkeypatch, "no json here at all")
        out = eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        assert out["verdict"] == "PARSE_ERROR"
        assert "Could not parse" in out["reason"]

    def test_malformed_json_inside_braces_returns_parse_error(self, monkeypatch):
        self._patch_call_api(monkeypatch, '{"verdict": ROUTE, broken}')
        out = eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        assert out["verdict"] == "PARSE_ERROR"

    def test_uppercases_verdict_field(self, monkeypatch):
        self._patch_call_api(monkeypatch, '{"verdict": "route", "reason": "lowercase"}')
        out = eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        assert out["verdict"] == "ROUTE"

    def test_missing_verdict_field_defaults_to_unknown(self, monkeypatch):
        self._patch_call_api(monkeypatch, '{"reason": "no verdict key"}')
        out = eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        assert out["verdict"] == "UNKNOWN"

    def test_user_message_includes_options(self, monkeypatch):
        captured = self._patch_call_api(
            monkeypatch, '{"verdict": "ROUTE", "reason": "x"}'
        )
        eval_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")
        user_text = captured["messages"][0]["content"]
        assert "ROUTE, DELEGATE" in user_text
        # OTHER not in this scenario's options, so its hint must be absent
        assert "Use OTHER" not in user_text

    def test_user_message_includes_other_hint_when_default_options(self, monkeypatch):
        captured = self._patch_call_api(
            monkeypatch, '{"verdict": "ROUTE", "reason": "x"}'
        )
        plain_scenario = {
            "id": "S1", "desc": "d", "input": "i", "expected_verdict": "ROUTE",
        }
        eval_mod.judge_scenario("k", "sys", plain_scenario, "claude")
        user_text = captured["messages"][0]["content"]
        assert "Use OTHER only if no other label fits" in user_text


# ---------------------------------------------------------------------------
# run_scenario_multi (judge_scenario mocked)
# ---------------------------------------------------------------------------

class TestRunScenarioMulti:
    SCENARIO = {
        "id": "S1", "desc": "d", "input": "i",
        "expected_verdict": "ROUTE",
        "verdict_options": ["ROUTE", "DELEGATE"],
    }

    def _stub_judge(self, monkeypatch, verdicts):
        idx = {"i": 0}

        def fake(api_key, prompt, scenario, model):
            v = verdicts[idx["i"] % len(verdicts)]
            idx["i"] += 1
            return {"verdict": v, "reason": f"verdict={v}", "raw": ""}

        monkeypatch.setattr(eval_mod, "judge_scenario", fake)
        # avoid sleeps in tests
        monkeypatch.setattr(eval_mod.time, "sleep", lambda _s: None)

    def test_all_runs_pass(self, monkeypatch):
        self._stub_judge(monkeypatch, ["ROUTE", "ROUTE", "ROUTE"])
        out = eval_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)
        assert out["passes"] == 3
        assert out["pass_rate"] == 1.0
        assert out["passed"] is True
        assert out["flaky"] is False

    def test_all_runs_fail(self, monkeypatch):
        self._stub_judge(monkeypatch, ["EXECUTE"] * 3)
        out = eval_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)
        assert out["passes"] == 0
        assert out["passed"] is False
        assert out["flaky"] is False  # 0/N is not flaky, it is uniform fail

    def test_two_of_three_passes_threshold(self, monkeypatch):
        self._stub_judge(monkeypatch, ["ROUTE", "ROUTE", "EXECUTE"])
        out = eval_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)
        assert out["passes"] == 2
        assert out["passed"] is True  # 2/3 >= threshold
        assert out["flaky"] is True

    def test_one_of_three_below_threshold(self, monkeypatch):
        self._stub_judge(monkeypatch, ["ROUTE", "EXECUTE", "EXECUTE"])
        out = eval_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)
        assert out["passes"] == 1
        assert out["passed"] is False
        assert out["flaky"] is True

    def test_security_critical_5_runs_full_pass(self, monkeypatch):
        self._stub_judge(monkeypatch, ["ROUTE"] * 5)
        out = eval_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 5)
        assert out["passes"] == 5
        assert out["passed"] is True
        assert out["flaky"] is False


# ---------------------------------------------------------------------------
# run_comparison
# ---------------------------------------------------------------------------

class TestRunComparison:
    SCENARIOS = [
        {
            "id": "S1", "desc": "d", "input": "i",
            "expected_verdict": "ROUTE",
            "verdict_options": ["ROUTE", "DELEGATE"],
        },
        {
            "id": "S2", "desc": "d2", "input": "i2",
            "expected_verdict": "DELEGATE",
            "verdict_options": ["ROUTE", "DELEGATE"],
        },
    ]

    def test_identical_before_after_yields_zero_delta(self, monkeypatch):
        def fake(api_key, prompt, scenario, model, runs):
            return {
                "scenario_id": scenario["id"], "passes": runs, "runs": runs,
                "pass_rate": 1.0, "passed": True, "flaky": False, "per_run": [],
            }

        monkeypatch.setattr(eval_mod, "run_scenario_multi", fake)
        out = eval_mod.run_comparison("k", "before", "before", self.SCENARIOS, "m", 3)
        assert out["before_score"] == 1.0
        assert out["after_score"] == 1.0
        assert out["delta"] == 0.0
        assert out["scenario_count"] == 2
        assert out["api_calls"] == 3 * 2 * 2  # 3 runs * 2 (before+after) * 2 scenarios

    def test_after_improves_over_before(self, monkeypatch):
        # Before: S1 fails, S2 passes; After: both pass.
        # Distinguish phase by prompt text ("old" vs "new").
        def fake(api_key, prompt, scenario, model, n):
            is_before_phase = prompt == "old"
            if is_before_phase and scenario["id"] == "S1":
                return {
                    "scenario_id": "S1", "passes": 0, "runs": n,
                    "pass_rate": 0.0, "passed": False, "flaky": False, "per_run": [],
                }
            return {
                "scenario_id": scenario["id"], "passes": n, "runs": n,
                "pass_rate": 1.0, "passed": True, "flaky": False, "per_run": [],
            }

        monkeypatch.setattr(eval_mod, "run_scenario_multi", fake)
        out = eval_mod.run_comparison("k", "old", "new", self.SCENARIOS, "m", 3)
        assert out["before_score"] == 0.5
        assert out["after_score"] == 1.0
        assert out["delta"] == 0.5


# ---------------------------------------------------------------------------
# acceptance_gate
# ---------------------------------------------------------------------------

class TestAcceptanceGate:
    def _comparison(self, before, after, before_score=None, after_score=None):
        return {
            "before_score": before_score if before_score is not None else (
                sum(1 for r in before if r["passed"]) / len(before)
            ),
            "after_score": after_score if after_score is not None else (
                sum(1 for r in after if r["passed"]) / len(after)
            ),
            "delta": 0.0,
            "before_results": before,
            "after_results": after,
        }

    @staticmethod
    def _r(sid, passed, pass_rate=None, runs=3, flaky=False):
        return {
            "scenario_id": sid, "passed": passed, "flaky": flaky,
            "runs": runs,
            "pass_rate": pass_rate if pass_rate is not None else (1.0 if passed else 0.0),
        }

    def test_all_pass_gate_passes(self):
        before = [self._r("S1", True), self._r("S2", True)]
        after = [self._r("S1", True), self._r("S2", True)]
        comp = self._comparison(before, after)
        comp["delta"] = 0.0
        gate = eval_mod.acceptance_gate(comp)
        assert gate["passed"] is True
        assert gate["verdict"] == "PASS"
        assert gate["criteria"]["no_regression"] is True
        assert gate["criteria"]["has_improvement"] is True
        assert gate["criteria"]["no_unexplained_regressions"] is True

    def test_regression_fails_gate(self):
        before = [self._r("S1", True), self._r("S2", True)]
        after = [self._r("S1", True), self._r("S2", False)]
        comp = self._comparison(before, after)
        comp["delta"] = -0.5
        gate = eval_mod.acceptance_gate(comp)
        assert gate["passed"] is False
        assert gate["criteria"]["no_regression"] is False
        assert gate["criteria"]["no_unexplained_regressions"] is False
        assert "S2" in gate["regressions"]

    def test_improvement_satisfies_gate(self):
        before = [self._r("S1", False), self._r("S2", True)]
        after = [self._r("S1", True), self._r("S2", True)]
        comp = self._comparison(before, after)
        comp["delta"] = 0.5
        gate = eval_mod.acceptance_gate(comp)
        assert gate["passed"] is True
        assert "S1" in gate["improvements"]

    def test_no_improvement_below_one_fails(self):
        before = [self._r("S1", False), self._r("S2", False)]
        after = [self._r("S1", False), self._r("S2", False)]
        comp = self._comparison(before, after)
        comp["delta"] = 0.0
        gate = eval_mod.acceptance_gate(comp)
        assert gate["passed"] is False
        assert gate["criteria"]["has_improvement"] is False

    def test_security_critical_requires_100_percent(self):
        before = [self._r("S1", True, pass_rate=1.0, runs=5)]
        after = [self._r("S1", True, pass_rate=0.8, runs=5)]
        comp = self._comparison(before, after, before_score=1.0, after_score=1.0)
        comp["delta"] = 0.0
        gate = eval_mod.acceptance_gate(comp, security_critical=True)
        assert gate["passed"] is False
        assert gate["criteria"]["security_all_runs_pass"] is False

    def test_security_critical_all_runs_pass(self):
        before = [self._r("S1", True, pass_rate=1.0, runs=5)]
        after = [self._r("S1", True, pass_rate=1.0, runs=5)]
        comp = self._comparison(before, after, before_score=1.0, after_score=1.0)
        comp["delta"] = 0.0
        gate = eval_mod.acceptance_gate(comp, security_critical=True)
        assert gate["passed"] is True
        assert gate["criteria"]["security_all_runs_pass"] is True

    def test_high_flakiness_fails_gate(self):
        # 30% pass rate => fail rate 70% > 40% threshold => blocked
        before = [self._r("S1", True, pass_rate=1.0)]
        after = [self._r("S1", False, pass_rate=0.3, flaky=True, runs=10)]
        comp = self._comparison(before, after, before_score=1.0, after_score=0.0)
        comp["delta"] = -1.0
        gate = eval_mod.acceptance_gate(comp)
        assert gate["passed"] is False
        assert gate["criteria"]["no_high_flakiness"] is False
        assert "S1" in gate["high_flakiness_scenarios"]

    def test_low_flakiness_does_not_fail_gate(self):
        # 80% pass rate => fail rate 20% <= 40% threshold => not blocked
        before = [self._r("S1", True, pass_rate=1.0)]
        after = [self._r("S1", True, pass_rate=0.8, flaky=True)]
        comp = self._comparison(before, after, before_score=1.0, after_score=1.0)
        comp["delta"] = 0.0
        gate = eval_mod.acceptance_gate(comp)
        assert gate["criteria"]["no_high_flakiness"] is True


# ---------------------------------------------------------------------------
# CLI parsing (_parse_args)
# ---------------------------------------------------------------------------

class TestParseArgs:
    def _run(self, argv, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", *argv])
        return eval_mod._parse_args()

    def test_explicit_before_after(self, monkeypatch):
        ns = self._run([
            "--before", "a.md", "--after", "b.md",
            "--scenarios", "s.json",
        ], monkeypatch)
        assert ns.before == "a.md"
        assert ns.after == "b.md"

    def test_prompt_with_default_base_ref(self, monkeypatch):
        ns = self._run(["--prompt", "p.md", "--scenarios", "s.json"], monkeypatch)
        assert ns.prompt == "p.md"
        assert ns.base_ref == "main"

    def test_missing_prompt_source_errors(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "--scenarios", "s.json"])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()

    def test_explicit_and_git_conflict_errors(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "prog", "--prompt", "p.md", "--before", "a.md", "--after", "b.md",
            "--scenarios", "s.json",
        ])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()

    def test_only_before_errors(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", "a.md", "--scenarios", "s.json",
        ])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()

    def test_only_after_errors(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "prog", "--after", "b.md", "--scenarios", "s.json",
        ])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()

    def test_prompt_with_only_before_errors(self, monkeypatch):
        # Reaches the --before/--after-must-pair validation past the earlier
        # has_explicit/has_git short-circuits.
        monkeypatch.setattr(sys, "argv", [
            "prog", "--prompt", "p.md", "--before", "a.md",
            "--scenarios", "s.json",
        ])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()

    def test_runs_below_minimum_errors(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "prog", "--prompt", "p.md", "--scenarios", "s.json", "--runs", "1",
        ])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()

    def test_security_critical_overrides_runs(self, monkeypatch):
        ns = self._run([
            "--prompt", "p.md", "--scenarios", "s.json",
            "--security-critical", "--runs", "3",
        ], monkeypatch)
        assert ns.runs == eval_mod.SECURITY_RUNS

    def test_zero_runs_rejected(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "prog", "--prompt", "p.md", "--scenarios", "s.json", "--runs", "0",
        ])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()


# ---------------------------------------------------------------------------
# _load_prompts
# ---------------------------------------------------------------------------

class TestLoadPrompts:
    def test_explicit_files(self, tmp_path, monkeypatch):
        a = tmp_path / "a.md"
        a.write_text("A", encoding="utf-8")
        b = tmp_path / "b.md"
        b.write_text("B", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(a), "--after", str(b), "--scenarios", "s.json",
        ])
        ns = eval_mod._parse_args()
        before, after, source = eval_mod._load_prompts(ns)
        assert before == "A"
        assert after == "B"
        assert "explicit" in source

    def test_git_ref_form(self, tmp_path, monkeypatch):
        p = tmp_path / "p.md"
        p.write_text("WORKING", encoding="utf-8")

        def fake_load_ref(path, ref):
            return f"REF[{ref}]:{path}"

        monkeypatch.setattr(eval_mod, "load_prompt_from_ref", fake_load_ref)
        monkeypatch.setattr(sys, "argv", [
            "prog", "--prompt", str(p), "--scenarios", "s.json",
        ])
        ns = eval_mod._parse_args()
        before, after, source = eval_mod._load_prompts(ns)
        assert before == f"REF[main]:{p}"
        assert after == "WORKING"
        assert "git" in source


# ---------------------------------------------------------------------------
# _print_gate_summary (smoke test - exercises every branch)
# ---------------------------------------------------------------------------

class TestPrintGateSummary:
    def test_prints_pass_summary(self, capsys):
        gate = {
            "verdict": "PASS", "passed": True,
            "before_score": 1.0, "after_score": 1.0, "delta": 0.0,
            "criteria": {"no_regression": True, "has_improvement": True},
            "improvements": [], "regressions": [],
            "flaky_scenarios": [], "high_flakiness_scenarios": [],
        }
        eval_mod._print_gate_summary(gate)
        err = capsys.readouterr().err
        assert "PASS" in err

    def test_prints_failures_and_flaky(self, capsys):
        gate = {
            "verdict": "FAIL", "passed": False,
            "before_score": 1.0, "after_score": 0.5, "delta": -0.5,
            "criteria": {"no_regression": False},
            "improvements": ["S2"], "regressions": ["S1"],
            "flaky_scenarios": ["S3"], "high_flakiness_scenarios": ["S4"],
        }
        eval_mod._print_gate_summary(gate)
        err = capsys.readouterr().err
        assert "FAIL" in err
        assert "S1" in err  # regression listed
        assert "S2" in err  # improvement listed
        assert "S3" in err  # flaky listed
        assert "S4" in err  # blocked listed


# ---------------------------------------------------------------------------
# main() and _run_and_report end-to-end (subprocess paths mocked)
# ---------------------------------------------------------------------------

class TestMainCLI:
    def _make_scenarios_file(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({
            "scenarios": [{
                "id": "S1", "desc": "d", "input": "i",
                "expected_verdict": "ROUTE",
                "verdict_options": ["ROUTE", "DELEGATE"],
            }]
        }), encoding="utf-8")
        return p

    def test_dry_run_exits_zero(self, tmp_path, monkeypatch, capsys):
        scen = self._make_scenarios_file(tmp_path)
        before = tmp_path / "a.md"
        before.write_text("system prompt", encoding="utf-8")
        after = tmp_path / "b.md"
        after.write_text("system prompt", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(before), "--after", str(after),
            "--scenarios", str(scen), "--dry-run",
        ])
        with pytest.raises(SystemExit) as exc:
            eval_mod.main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "dry_run" in out

    def test_load_scenarios_failure_exits_two(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", "/no", "--after", "/no",
            "--scenarios", str(tmp_path / "missing.json"),
        ])
        with pytest.raises(SystemExit) as exc:
            eval_mod.main()
        assert exc.value.code == 2

    def test_full_run_prints_to_stdout_when_no_output_flag(self, tmp_path, monkeypatch, capsys):
        scen = self._make_scenarios_file(tmp_path)
        before = tmp_path / "a.md"
        before.write_text("p", encoding="utf-8")
        after = tmp_path / "b.md"
        after.write_text("p", encoding="utf-8")

        monkeypatch.setattr(eval_mod, "load_api_key", lambda: "test-key")
        monkeypatch.setattr(eval_mod, "call_api",
            lambda *a, **kw: '{"verdict": "ROUTE", "reason": "ok"}')
        monkeypatch.setattr(eval_mod.time, "sleep", lambda _s: None)

        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(before), "--after", str(after),
            "--scenarios", str(scen),
        ])
        with pytest.raises(SystemExit):
            eval_mod.main()
        out = capsys.readouterr().out
        assert "comparison" in out

    def test_full_run_exits_zero_on_pass(self, tmp_path, monkeypatch):
        scen = self._make_scenarios_file(tmp_path)
        before = tmp_path / "a.md"
        before.write_text("p", encoding="utf-8")
        after = tmp_path / "b.md"
        after.write_text("p", encoding="utf-8")

        # Stub everything that touches the network/filesystem for the API call
        monkeypatch.setattr(eval_mod, "load_api_key", lambda: "test-key")
        monkeypatch.setattr(eval_mod, "call_api",
            lambda *a, **kw: '{"verdict": "ROUTE", "reason": "ok"}')
        monkeypatch.setattr(eval_mod.time, "sleep", lambda _s: None)

        out_path = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(before), "--after", str(after),
            "--scenarios", str(scen), "--output", str(out_path),
        ])
        with pytest.raises(SystemExit) as exc:
            eval_mod.main()
        # Gate fails because before==after==1.0 satisfies has_improvement
        # via before_score==1.0 clause
        assert exc.value.code == 0
        result = json.loads(out_path.read_text())
        assert result["gate"]["verdict"] == "PASS"

    def test_load_api_key_missing_exits_two(self, tmp_path, monkeypatch):
        scen = self._make_scenarios_file(tmp_path)
        before = tmp_path / "a.md"
        before.write_text("p", encoding="utf-8")
        after = tmp_path / "b.md"
        after.write_text("p", encoding="utf-8")

        def boom():
            raise RuntimeError("no key")

        monkeypatch.setattr(eval_mod, "load_api_key", boom)
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(before), "--after", str(after),
            "--scenarios", str(scen),
        ])
        with pytest.raises(SystemExit) as exc:
            eval_mod.main()
        assert exc.value.code == 2

    def test_load_prompts_failure_exits_two(self, tmp_path, monkeypatch):
        scen = self._make_scenarios_file(tmp_path)
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(tmp_path / "nope-a.md"),
            "--after", str(tmp_path / "nope-b.md"),
            "--scenarios", str(scen),
        ])
        with pytest.raises(SystemExit) as exc:
            eval_mod.main()
        assert exc.value.code == 2

    def test_runtime_error_during_run_exits_three(self, tmp_path, monkeypatch):
        scen = self._make_scenarios_file(tmp_path)
        before = tmp_path / "a.md"
        before.write_text("p", encoding="utf-8")
        after = tmp_path / "b.md"
        after.write_text("p", encoding="utf-8")

        monkeypatch.setattr(eval_mod, "load_api_key", lambda: "test-key")

        def boom_run(*a, **kw):
            raise RuntimeError("api blew up")

        monkeypatch.setattr(eval_mod, "_run_and_report", boom_run)
        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(before), "--after", str(after),
            "--scenarios", str(scen),
        ])
        with pytest.raises(SystemExit) as exc:
            eval_mod.main()
        assert exc.value.code == 3

    def test_identical_before_after_warning_emitted(self, tmp_path, monkeypatch, capsys):
        scen = self._make_scenarios_file(tmp_path)
        before = tmp_path / "a.md"
        before.write_text("same content", encoding="utf-8")
        after = tmp_path / "b.md"
        after.write_text("same content", encoding="utf-8")

        monkeypatch.setattr(sys, "argv", [
            "prog", "--before", str(before), "--after", str(after),
            "--scenarios", str(scen), "--dry-run",
        ])
        with pytest.raises(SystemExit):
            eval_mod.main()
        err = capsys.readouterr().err
        assert "before and after prompt text are identical" in err
