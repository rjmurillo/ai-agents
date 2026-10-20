"""Load-bearing contract for rule-activation scenarios (issue #5405).

Covers `scripts/eval/_load_bearing.py` and its wiring in
`eval-rule-activation.py`: the control arm, the three checks, the exit code,
and the voice scenario file that declares the contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.eval.test_eval_rule_activation import _make_scenario, eval_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_SCENARIOS = REPO_ROOT / "tests" / "evals" / "rule-scenarios" / "voice.json"

EVAL_DIR = str(REPO_ROOT / "scripts" / "eval")
if EVAL_DIR not in sys.path:
    sys.path.insert(0, EVAL_DIR)
import _load_bearing as lb  # noqa: E402

SPEC: dict[str, Any] = {
    "control_instruction": "Be verbose.",
    "min_shrink_vs_control": 0.25,
    "min_score_gain_vs_control": 0.5,
    "max_exempt_shrink_vs_baseline": 0.2,
}


def _cell(
    *,
    chars: float | None = None,
    tokens: float | None = None,
    avg: float | None = 4.0,
    n: int = 2,
    chars_n: int | None = None,
    tokens_n: int | None = None,
) -> dict[str, Any]:
    return {
        "scenario_count": n,
        "graded_count": n if avg is not None else 0,
        "avg_score": avg,
        "mean_response_chars": chars,
        "response_chars_count": (n if chars is not None else 0) if chars_n is None else chars_n,
        "mean_output_tokens": tokens,
        "output_token_count": (n if tokens is not None else 0) if tokens_n is None else tokens_n,
    }


def _passing_pools() -> tuple[dict[str, Any], dict[str, Any]]:
    positive = {
        "baseline": _cell(chars=500, avg=3.0),
        "full": _cell(chars=300, avg=4.8),
        "control": _cell(chars=900, avg=2.5),
    }
    negative = {
        "baseline": _cell(chars=1500, avg=5.0),
        "full": _cell(chars=1450, avg=5.0),
    }
    return positive, negative


class TestValidateSpec:
    def test_valid_spec_is_accepted(self):
        assert lb.validate_spec(SPEC) is None

    @pytest.mark.parametrize("spec", [None, [], "x", 3])
    def test_non_object_is_refused(self, spec):
        assert "must be an object" in lb.validate_spec(spec)

    @pytest.mark.parametrize("instruction", [None, "", "   ", 5])
    def test_control_instruction_must_be_text(self, instruction):
        error = lb.validate_spec({**SPEC, "control_instruction": instruction})
        assert "control_instruction" in error

    @pytest.mark.parametrize("field", sorted(lb._THRESHOLD_FIELDS))
    @pytest.mark.parametrize("value", [None, "0.2", True, float("nan"), float("inf")])
    def test_threshold_must_be_a_finite_number(self, field, value):
        assert field in lb.validate_spec({**SPEC, field: value})

    @pytest.mark.parametrize("field", sorted(lb._THRESHOLD_FIELDS))
    def test_an_oversized_integer_threshold_is_refused_not_a_crash(self, field):
        assert field in lb.validate_spec({**SPEC, field: 10**500})

    def test_missing_threshold_is_refused(self):
        spec = {k: v for k, v in SPEC.items() if k != "min_shrink_vs_control"}
        assert "min_shrink_vs_control" in lb.validate_spec(spec)

    @pytest.mark.parametrize("field", ["min_shrink_vs_control", "max_exempt_shrink_vs_baseline"])
    @pytest.mark.parametrize("value", [0, 1, -0.1, 1.5])
    def test_shrink_fractions_stay_inside_zero_and_one(self, field, value):
        assert field in lb.validate_spec({**SPEC, field: value})

    @pytest.mark.parametrize("value", [0, -1, 4.5])
    def test_score_gain_stays_on_the_rubric_range(self, value):
        assert "min_score_gain_vs_control" in lb.validate_spec(
            {**SPEC, "min_score_gain_vs_control": value}
        )


class TestEvaluate:
    def test_all_checks_pass(self):
        positive, negative = _passing_pools()
        result = lb.evaluate(SPEC, positive, negative)
        assert result["status"] == lb.PASS
        assert {c["status"] for c in result["checks"].values()} == {lb.PASS}
        assert result["checks"]["concision"]["shrink"] == pytest.approx(0.667, abs=0.001)
        assert result["checks"]["grounding"]["gain"] == 2.3
        assert result["checks"]["exempt"]["shrink"] == pytest.approx(0.033, abs=0.001)
        assert lb.exit_code(result) == 0

    def test_concision_fails_when_the_rule_barely_beats_the_control(self):
        positive, negative = _passing_pools()
        positive["control"] = _cell(chars=350, avg=2.5)
        result = lb.evaluate(SPEC, positive, negative)
        assert result["checks"]["concision"]["status"] == lb.FAIL
        assert result["status"] == lb.FAIL
        assert lb.exit_code(result) == 1

    def test_concision_fails_when_the_rule_makes_output_longer(self):
        positive, negative = _passing_pools()
        positive["control"] = _cell(chars=200, avg=2.5)
        result = lb.evaluate(SPEC, positive, negative)
        assert result["checks"]["concision"]["status"] == lb.FAIL
        assert result["checks"]["concision"]["shrink"] < 0

    def test_grounding_fails_when_the_control_scores_as_well(self):
        positive, negative = _passing_pools()
        positive["control"] = _cell(chars=900, avg=4.5)
        result = lb.evaluate(SPEC, positive, negative)
        assert result["checks"]["grounding"]["status"] == lb.FAIL
        assert result["status"] == lb.FAIL

    def test_grounding_passes_at_exactly_the_threshold(self):
        positive, negative = _passing_pools()
        positive["full"] = _cell(chars=300, avg=3.0)
        positive["control"] = _cell(chars=900, avg=2.5)
        assert lb.evaluate(SPEC, positive, negative)["checks"]["grounding"]["status"] == lb.PASS

    def test_exempt_fails_when_the_rule_shrinks_a_requested_deliverable(self):
        positive, negative = _passing_pools()
        negative["full"] = _cell(chars=1000, avg=5.0)
        result = lb.evaluate(SPEC, positive, negative)
        assert result["checks"]["exempt"]["status"] == lb.FAIL
        assert result["checks"]["exempt"]["shrink"] == pytest.approx(0.333, abs=0.001)
        assert result["status"] == lb.FAIL

    def test_exempt_passes_when_the_rule_lengthens_exempt_output(self):
        positive, negative = _passing_pools()
        negative["full"] = _cell(chars=2000, avg=5.0)
        assert lb.evaluate(SPEC, positive, negative)["checks"]["exempt"]["status"] == lb.PASS

    def test_exempt_passes_at_exactly_the_limit(self):
        positive, negative = _passing_pools()
        negative["full"] = _cell(chars=1200, avg=5.0)
        assert lb.evaluate(SPEC, positive, negative)["checks"]["exempt"]["status"] == lb.PASS

    def test_archived_negative_pool_means_pass_the_exempt_limit(self):
        """The 2026-10-18 voice run: 1498.8 to 1489.0 characters, a 0.7% shrink."""
        positive, _ = _passing_pools()
        held = {"baseline": _cell(chars=1498.8), "full": _cell(chars=1489.0)}
        check = lb.evaluate(SPEC, positive, held)["checks"]["exempt"]
        assert check["status"] == lb.PASS
        assert check["shrink"] == pytest.approx(0.007, abs=0.001)

    def test_a_missing_control_arm_is_unmeasured_not_a_pass(self):
        positive, negative = _passing_pools()
        del positive["control"]
        result = lb.evaluate(SPEC, positive, negative)
        assert result["checks"]["concision"]["status"] == lb.UNMEASURED
        assert result["checks"]["grounding"]["status"] == lb.UNMEASURED
        assert result["status"] == lb.UNMEASURED
        assert lb.exit_code(result) == 1

    def test_a_failure_outranks_an_unmeasured_check(self):
        positive, negative = _passing_pools()
        del positive["control"]
        negative["full"] = _cell(chars=100, avg=5.0)
        assert lb.evaluate(SPEC, positive, negative)["status"] == lb.FAIL

    def test_empty_pools_are_unmeasured(self):
        result = lb.evaluate(SPEC, {}, {})
        assert result["status"] == lb.UNMEASURED
        assert {c["status"] for c in result["checks"].values()} == {lb.UNMEASURED}

    def test_ungraded_control_cell_is_unmeasured(self):
        positive, negative = _passing_pools()
        positive["control"] = _cell(chars=900, avg=None)
        assert (
            lb.evaluate(SPEC, positive, negative)["checks"]["grounding"]["status"] == lb.UNMEASURED
        )

    def test_partially_graded_control_cell_is_unmeasured(self):
        positive, negative = _passing_pools()
        positive["control"] = {**_cell(chars=900, avg=2.5), "graded_count": 1}
        assert (
            lb.evaluate(SPEC, positive, negative)["checks"]["grounding"]["status"] == lb.UNMEASURED
        )

    @pytest.mark.parametrize(
        "key", ["judge_failures", "judge_failure_cells", "judge_failure_samples"]
    )
    @pytest.mark.parametrize("arm", ["control", "full"])
    def test_a_failed_judge_sample_makes_grounding_unmeasured(self, arm, key):
        positive, negative = _passing_pools()
        positive[arm] = {**positive[arm], key: 1}
        result = lb.evaluate(SPEC, positive, negative)
        assert result["checks"]["grounding"]["status"] == lb.UNMEASURED
        assert result["status"] == lb.UNMEASURED
        assert lb.exit_code(result) == 1

    def test_a_decimal_gain_equal_to_the_threshold_passes(self):
        positive, negative = _passing_pools()
        positive["full"] = _cell(chars=300, avg=4.1)
        positive["control"] = _cell(chars=900, avg=3.6)
        check = lb.evaluate(SPEC, positive, negative)["checks"]["grounding"]
        assert check["gain"] == 0.5
        assert check["status"] == lb.PASS

    def test_a_decimal_shrink_equal_to_the_exempt_limit_passes(self):
        positive, negative = _passing_pools()
        negative["baseline"] = _cell(chars=1000, avg=5.0)
        negative["full"] = _cell(chars=800, avg=5.0)
        check = lb.evaluate(SPEC, positive, negative)["checks"]["exempt"]
        assert check["shrink"] == 0.2
        assert check["status"] == lb.PASS

    def test_tokens_are_preferred_when_both_sides_reported_them(self):
        positive, negative = _passing_pools()
        positive["full"] = _cell(chars=300, tokens=100, avg=4.8)
        positive["control"] = _cell(chars=900, tokens=120, avg=2.5)
        check = lb.evaluate(SPEC, positive, negative)["checks"]["concision"]
        assert check["metric"] == "output_tokens"
        assert check["status"] == lb.FAIL

    def test_chars_are_used_when_tokens_cover_only_one_side(self):
        positive, negative = _passing_pools()
        positive["full"] = _cell(chars=300, tokens=100, avg=4.8)
        check = lb.evaluate(SPEC, positive, negative)["checks"]["concision"]
        assert check["metric"] == "response_chars"
        assert check["status"] == lb.PASS

    def test_chars_are_used_when_tokens_cover_part_of_a_pool(self):
        positive, negative = _passing_pools()
        positive["full"] = _cell(chars=300, tokens=100, avg=4.8, tokens_n=1)
        positive["control"] = _cell(chars=900, tokens=400, avg=2.5)
        assert lb.evaluate(SPEC, positive, negative)["checks"]["concision"]["metric"] == (
            "response_chars"
        )

    def test_size_on_part_of_a_pool_is_unmeasured(self):
        positive, negative = _passing_pools()
        positive["control"] = _cell(chars=900, avg=2.5, chars_n=1)
        assert (
            lb.evaluate(SPEC, positive, negative)["checks"]["concision"]["status"] == lb.UNMEASURED
        )

    def test_a_zero_reference_is_unmeasured_not_a_division_error(self):
        positive, negative = _passing_pools()
        positive["control"] = _cell(chars=0, avg=2.5)
        negative["baseline"] = _cell(chars=0, avg=5.0)
        checks = lb.evaluate(SPEC, positive, negative)["checks"]
        assert checks["concision"]["status"] == lb.UNMEASURED
        assert checks["exempt"]["status"] == lb.UNMEASURED

    def test_exact_means_are_used_over_rounded_ones(self):
        positive, negative = _passing_pools()
        negative["baseline"] = {**_cell(chars=100.0), "mean_response_chars_exact": 100.04}
        negative["full"] = {**_cell(chars=80.0), "mean_response_chars_exact": 80.03}
        check = lb.evaluate(SPEC, positive, negative)["checks"]["exempt"]
        assert check["baseline"] == 100.04
        assert check["full"] == 80.03


class TestRender:
    def test_each_check_names_its_numbers(self):
        positive, negative = _passing_pools()
        lines = lb.render(lb.evaluate(SPEC, positive, negative))
        text = "\n".join(lines)
        assert lines[0] == "Load-bearing contract: PASS"
        assert "concision: PASS response_chars rule 300.0 vs control 900.0" in text
        assert "grounding: PASS rule 4.8 vs control 2.5, gain 2.3" in text
        assert "exempt: PASS response_chars rule 1450.0 vs baseline 1500.0" in text

    def test_unmeasured_checks_say_what_is_missing(self):
        text = "\n".join(lb.render(lb.evaluate(SPEC, {}, {})))
        assert "Load-bearing contract: UNMEASURED" in text
        assert "concision: UNMEASURED" in text
        assert "grounding: UNMEASURED" in text
        assert "exempt: UNMEASURED" in text

    def test_failure_is_labelled(self):
        positive, negative = _passing_pools()
        negative["full"] = _cell(chars=100, avg=5.0)
        assert "exempt: FAIL" in "\n".join(lb.render(lb.evaluate(SPEC, positive, negative)))


class TestControlArm:
    @staticmethod
    def _run(monkeypatch, control_instruction: str | None) -> tuple[dict[str, Any], list[str]]:
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
        systems: list[str] = []

        def fake_call(api_key, messages, *, system="", metadata=None, **kwargs):
            if metadata is not None:
                metadata["output_tokens"] = 7
            if messages[0]["content"] == "x":
                systems.append(system)
            return "response"

        monkeypatch.setattr(eval_mod, "_call_api", fake_call)
        monkeypatch.setattr(
            eval_mod,
            "score_response",
            lambda *a, **k: {
                "activation_score": 3,
                "citation_score": 3,
                "behavior_score": 3,
                "judge_failed": False,
            },
        )
        rule = {"name": "voice", "description": "d", "body": "rule body", "path": "p"}
        scenario = {"id": "V6", "input": "x", "expected_gate": "enforce-concise-reporting"}
        result = eval_mod.eval_one_scenario(
            "key",
            rule,
            "voice",
            scenario,
            "model",
            dry_run=False,
            judge_repeats=1,
            control_instruction=control_instruction,
        )
        return result, systems

    def test_control_cell_is_run_with_only_the_control_instruction(self, monkeypatch):
        result, systems = self._run(monkeypatch, "Be verbose.")
        assert list(result["mechanisms"]) == ["baseline", "description", "full", "control"]
        assert "Be verbose." in systems
        assert systems.count("Be verbose.") == 1
        control = result["mechanisms"]["control"]
        assert control["system_prompt_chars"] == len("Be verbose.")
        assert control["output_tokens"] == 7
        assert control["response_chars"] == len("response")

    def test_control_prompt_carries_no_rule_text(self, monkeypatch):
        _, systems = self._run(monkeypatch, "Be verbose.")
        control_system = next(s for s in systems if "verbose" in s)
        assert "rule body" not in control_system

    @pytest.mark.parametrize("instruction", [None, ""])
    def test_no_control_instruction_runs_no_control_arm(self, monkeypatch, instruction):
        result, _ = self._run(monkeypatch, instruction)
        assert "control" not in result["mechanisms"]
        assert list(result["mechanisms"]) == ["baseline", "description", "full"]

    def test_control_arm_is_not_a_gate_mechanism(self):
        assert "control" not in eval_mod.MECHANISMS
        scenarios = [
            _make_scenario(baseline=1, description=4, full=5),
            _make_scenario(baseline=1, description=5, full=5, negative=True),
        ]
        for s in scenarios:
            s["mechanisms"]["control"] = {
                "scores": {"activation_score": 1, "citation_score": 1, "behavior_score": 1}
            }
        summary = eval_mod.aggregate(scenarios)
        assert summary["verdict"] == "PASS"
        assert "control" not in summary["per_mechanism"]


class TestEvaluateOverScenarioCells:
    def test_contract_reads_the_recorded_cells(self):
        pos = _make_scenario(2, 3, 5)
        for arm, chars, score in (("baseline", 500, 2), ("full", 300, 5), ("control", 900, 2)):
            pos["mechanisms"][arm] = {
                "scores": {
                    "activation_score": score,
                    "citation_score": score,
                    "behavior_score": score,
                },
                "response_chars": chars,
            }
        neg = _make_scenario(5, 5, 5, negative=True)
        for arm, chars in (("baseline", 1500), ("full", 1000)):
            neg["mechanisms"][arm]["response_chars"] = chars
        result = eval_mod._evaluate_load_bearing(SPEC, [pos, neg])
        assert result["checks"]["concision"]["status"] == lb.PASS
        assert result["checks"]["grounding"]["status"] == lb.PASS
        assert result["checks"]["exempt"]["status"] == lb.FAIL
        assert result["status"] == lb.FAIL

    def test_non_boolean_pool_marker_is_refused(self):
        scenario = _make_scenario(2, 3, 5)
        scenario["negative_case"] = "false"
        with pytest.raises(ValueError, match="negative_case must be a boolean"):
            eval_mod._evaluate_load_bearing(SPEC, [scenario])


class TestLoadScenariosFile:
    @staticmethod
    def _write(tmp_path: Path, spec: Any) -> str:
        data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
        data["load_bearing"] = spec
        path = tmp_path / "voice.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_malformed_spec_exits_2_before_any_call(self, tmp_path, capsys):
        bad = {k: v for k, v in SPEC.items() if k != "max_exempt_shrink_vs_baseline"}
        assert eval_mod._load_scenarios_file(self._write(tmp_path, bad)) == 2
        assert "max_exempt_shrink_vs_baseline" in capsys.readouterr().err

    def test_valid_spec_loads(self, tmp_path):
        loaded = eval_mod._load_scenarios_file(self._write(tmp_path, SPEC))
        assert not isinstance(loaded, int)
        assert loaded[0]["load_bearing"] == SPEC


class TestVoiceScenarioFile:
    def test_voice_declares_a_valid_contract(self):
        data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
        assert lb.validate_spec(data["load_bearing"]) is None

    def test_voice_file_loads_through_the_harness(self):
        loaded = eval_mod._load_scenarios_file(str(VOICE_SCENARIOS))
        assert not isinstance(loaded, int)

    def test_control_instruction_does_not_borrow_the_rule_wording(self):
        data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
        rule_body = (REPO_ROOT / ".claude" / "rules" / "voice.md").read_text(encoding="utf-8")
        instruction = data["load_bearing"]["control_instruction"]
        assert instruction not in rule_body
        assert "telemetry" not in instruction.lower()


class TestProcessOneRule:
    @staticmethod
    def _args(dry_run: bool) -> SimpleNamespace:
        return SimpleNamespace(
            dry_run=dry_run,
            model="m",
            seed=0,
            judge_repeats=3,
            judge_reducer="median",
        )

    def test_dry_run_counts_the_control_arm(self, capsys):
        loaded = eval_mod._load_scenarios_file(str(VOICE_SCENARIOS))
        assert not isinstance(loaded, int)
        data, paths = loaded
        _, _, calls = eval_mod._process_one_rule("", data, paths, self._args(True))
        assert calls == len(data["scenarios"]) * 4 * 4
        assert "4 mechanisms" in capsys.readouterr().out

    def test_dry_run_without_a_contract_counts_three_arms(self, capsys):
        loaded = eval_mod._load_scenarios_file(str(VOICE_SCENARIOS))
        assert not isinstance(loaded, int)
        data, paths = loaded
        data = {k: v for k, v in data.items() if k != "load_bearing"}
        _, _, calls = eval_mod._process_one_rule("", data, paths, self._args(True))
        assert calls == len(data["scenarios"]) * 3 * 4
        assert "3 mechanisms" in capsys.readouterr().out


class TestExitCode:
    @staticmethod
    def _worst_exit(monkeypatch, summary: dict[str, Any]) -> int:
        monkeypatch.setattr(
            eval_mod, "_process_one_rule", lambda *a, **k: ("voice", {"summary": summary}, 1)
        )
        state = eval_mod._RunState()
        eval_mod._process_scenario_file(str(VOICE_SCENARIOS), "", None, {"rules": {}}, state)
        return state.worst_exit

    @pytest.mark.parametrize("status", [lb.FAIL, lb.UNMEASURED])
    def test_a_contract_that_did_not_pass_raises_the_exit_over_a_pass_verdict(
        self, monkeypatch, status
    ):
        summary = {"verdict": "PASS", "load_bearing": {"status": status}}
        assert self._worst_exit(monkeypatch, summary) == 1

    def test_passing_contract_leaves_a_pass_verdict_at_zero(self, monkeypatch):
        summary = {"verdict": "PASS", "load_bearing": {"status": lb.PASS}}
        assert self._worst_exit(monkeypatch, summary) == 0

    def test_a_rule_without_a_contract_is_unchanged(self, monkeypatch):
        assert self._worst_exit(monkeypatch, {"verdict": "PASS"}) == 0

    def test_a_failing_verdict_is_not_lowered_by_a_passing_contract(self, monkeypatch):
        summary = {"verdict": "FAIL_THRESHOLD", "load_bearing": {"status": lb.PASS}}
        assert self._worst_exit(monkeypatch, summary) == 1
