"""Run-level checks for tests/evals/rule-scenarios/capability-first.json (issue #6658).

Drives `_process_one_rule` with stubbed model and judge calls to check how the
decision grade reaches the run report, the run verdict, and the exit code.
Offline scenario checks live in test_capability_first_scenarios.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
SCENARIO_FILE = REPO_ROOT / "tests" / "evals" / "rule-scenarios" / "capability-first.json"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _decision_grade as dg
    import software_engineering_library_activation_gate as gate

    _spec = importlib.util.spec_from_file_location(
        "eval_rule_activation_cf_run", EVAL_DIR / "eval-rule-activation.py"
    )
    assert _spec and _spec.loader
    runner = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(runner)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))

DATA: dict[str, Any] = json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))
SCENARIOS: list[dict[str, Any]] = DATA["scenarios"]

DESC_MARKER = "Project rules apply to your work"


def _judge_ok(*_a: object, **_kw: object) -> dict[str, object]:
    return {"activation_score": 3, "citation_score": 3, "behavior_score": 3, "judge_failed": False}


def _stub_run(
    monkeypatch: pytest.MonkeyPatch,
    per_mechanism: dict[str, str],
    *,
    rule_name: str = "universal.md",
    judge_verdict: str | None = None,
    termination: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run every scenario through `_process_one_rule` with stubbed model calls.

    `per_mechanism` maps a system-prompt marker to the response style the stub
    returns: "good" for each scenario's first known_good, "bad" for known_bad.
    `rule_name` picks the rule under test: a rule with a `description:` makes
    the `description` mechanism measurable. `judge_verdict` replaces the judge
    verdict after aggregation, to model a judge that passes on vocabulary.
    `termination` maps a mechanism to the stop reason the stub reports for it.
    """
    by_input = {s["input"]: s for s in SCENARIOS}

    def fake_call_api(_key: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        scenario = by_input[messages[0]["content"]]
        system = kwargs.get("system") or ""
        mech = "description" if system.startswith(DESC_MARKER) else "full" if system else "baseline"
        if termination and mech in termination:
            kwargs["metadata"]["termination"] = termination[mech]
        style = per_mechanism[mech]
        key = "known_good" if style == "good" else "known_bad"
        return str(scenario["decision"][key][0])

    def fake_score(*_a: object, **_kw: object) -> dict[str, object]:
        return {
            "activation_score": 3,
            "citation_score": 3,
            "behavior_score": 3,
            "judge_failed": False,
        }

    monkeypatch.setattr(runner, "RATE_LIMIT_SLEEP_SEC", 0)
    monkeypatch.setattr(runner, "_call_api", fake_call_api)
    monkeypatch.setattr(runner, "score_response", fake_score)
    args = type(
        "Args",
        (),
        {"dry_run": False, "model": "m", "seed": 0, "judge_repeats": 1, "judge_reducer": "median"},
    )()
    if judge_verdict is not None:
        real_aggregate = runner.aggregate

        def aggregate_with_verdict(*a: Any, **kw: Any) -> dict[str, Any]:
            summary = real_aggregate(*a, **kw)
            summary["verdict"] = judge_verdict
            return summary

        monkeypatch.setattr(runner, "aggregate", aggregate_with_verdict)
    rule_path = REPO_ROOT / ".claude" / "rules" / rule_name
    _id, result, _calls = runner._process_one_rule("key", DATA, (rule_path, None), args)
    assert result is not None
    return result


class TestRunnerIntegration:
    def test_baseline_vs_enabled_is_reported_with_limits(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = _stub_run(monkeypatch, {"baseline": "bad", "full": "good"})
        check = result["summary"]["decision_check"]
        base = check["per_mechanism"]["baseline"]
        full = check["per_mechanism"]["full"]
        assert base["positive"]["pass_rate"] == 0.0
        assert full["positive"]["pass_rate"] == 1.0
        assert base["negative"]["pass_rate"] == 0.0
        assert full["negative"]["pass_rate"] == 1.0
        # universal.md has no description, so the description cell collapses to
        # baseline and is declined. It must read UNMEASURED, never 0 or 1.
        desc = check["per_mechanism"]["description"]["positive"]
        assert desc["graded"] == 0
        assert desc["pass_rate"] == dg.UNMEASURED
        out = capsys.readouterr().out
        assert "Decision check" in out
        assert "gap full vs baseline: +1.0" in out
        assert f"gap description vs baseline: {dg.UNMEASURED}" in out

    def test_equal_arms_report_no_gap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _stub_run(monkeypatch, {"baseline": "good", "full": "good"})
        check = result["summary"]["decision_check"]
        assert check["per_mechanism"]["baseline"]["positive"]["pass_rate"] == 1.0
        assert check["per_mechanism"]["full"]["positive"]["pass_rate"] == 1.0

    def test_cell_records_the_decision_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _stub_run(monkeypatch, {"baseline": "bad", "full": "good"})
        s1 = next(s for s in result["scenarios"] if s["id"] == "S1")
        assert s1["decision_declared"] is True
        assert s1["mechanisms"]["baseline"]["decision"]["reason"] == dg.REASON_WRONG_DECISION
        assert s1["mechanisms"]["full"]["decision"]["passed"] is True

    def test_api_error_leaves_the_cell_ungraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: object, **_kw: object) -> str:
            raise RuntimeError("provider down")

        monkeypatch.setattr(runner, "RATE_LIMIT_SLEEP_SEC", 0)
        monkeypatch.setattr(runner, "_call_api", boom)
        scenario = SCENARIOS[0]
        rule = runner.parse_rule(REPO_ROOT / ".claude" / "rules" / "universal.md")
        cell = runner.eval_one_scenario(
            "key", rule, "capability-first", scenario, "m", dry_run=False, judge_repeats=1
        )
        assert cell["decision_declared"] is True
        assert "decision" not in cell["mechanisms"]["baseline"]
        summary = dg.summarize_decisions([cell], runner.MECHANISMS)
        assert summary["per_mechanism"]["baseline"]["positive"]["pass_rate"] == dg.UNMEASURED

    @pytest.mark.parametrize("termination", ["refusal", "token_limit", "incomplete"])
    def test_non_scoreable_termination_leaves_the_cell_ungraded(
        self, monkeypatch: pytest.MonkeyPatch, termination: str
    ) -> None:
        def cut_off(_key: str, _messages: list[dict[str, str]], **kwargs: Any) -> str:
            kwargs["metadata"]["termination"] = termination
            return "DECISION: REUSE"

        monkeypatch.setattr(runner, "RATE_LIMIT_SLEEP_SEC", 0)
        monkeypatch.setattr(runner, "_call_api", cut_off)
        monkeypatch.setattr(runner, "score_response", _judge_ok)
        scenario = SCENARIOS[1]
        rule = runner.parse_rule(REPO_ROOT / ".claude" / "rules" / "universal.md")
        cell = runner.eval_one_scenario(
            "key", rule, "capability-first", scenario, "m", dry_run=False, judge_repeats=1
        )
        baseline = cell["mechanisms"]["baseline"]
        assert "decision" not in baseline
        assert baseline["decision_ungraded"] == termination
        summary = dg.summarize_decisions([cell], runner.MECHANISMS)
        positive = summary["per_mechanism"]["baseline"]["positive"]
        assert (positive["declared"], positive["graded"]) == (1, 0)
        assert positive["pass_rate"] == dg.UNMEASURED
        assert positive["failure_reasons"] == []

    def test_scoreable_termination_is_still_graded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def clean_stop(_key: str, _messages: list[dict[str, str]], **kwargs: Any) -> str:
            kwargs["metadata"]["termination"] = "end_turn"
            return "DECISION: REUSE\nEVIDENCE: python scripts/validation/check_rule_scope_keys.py"

        monkeypatch.setattr(runner, "RATE_LIMIT_SLEEP_SEC", 0)
        monkeypatch.setattr(runner, "_call_api", clean_stop)
        monkeypatch.setattr(runner, "score_response", _judge_ok)
        rule = runner.parse_rule(REPO_ROOT / ".claude" / "rules" / "universal.md")
        cell = runner.eval_one_scenario(
            "key", rule, "capability-first", SCENARIOS[1], "m", dry_run=False, judge_repeats=1
        )
        assert cell["mechanisms"]["baseline"]["decision"]["passed"] is True
        assert "decision_ungraded" not in cell["mechanisms"]["baseline"]


class TestRunVerdictFollowsTheDecision:
    """A judge PASS over vocabulary must not survive wrong or unmeasured calls.

    The judge scores how much a response sounds like the rule. These runs force
    the judge verdict to PASS, the keyword-pass path, and check what the run
    reports and exits with. `python.md` carries a `description:`, so the
    `description` mechanism is measurable.
    """

    def _run(
        self, monkeypatch: pytest.MonkeyPatch, styles: dict[str, str], **kwargs: Any
    ) -> dict[str, Any]:
        return _stub_run(monkeypatch, styles, rule_name="python.md", judge_verdict="PASS", **kwargs)

    def test_every_call_wrong_turns_a_judge_pass_into_fail_decision(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        styles = {"baseline": "bad", "description": "bad", "full": "bad"}
        summary = self._run(monkeypatch, styles)["summary"]
        assert summary["verdict"] == "FAIL_DECISION"
        gate = summary["decision_check"]["gate"]
        assert gate["failed"] == [
            "positive description",
            "negative description",
            "negative full",
        ]
        assert gate["incomplete"] == []
        assert runner._classify_verdict(summary["verdict"]) == 1
        out = capsys.readouterr().out
        assert "FAIL_DECISION" in out
        assert "Decision gate" in out

    def test_one_wrong_positive_call_on_description_is_enough(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        styles = {"baseline": "good", "description": "bad", "full": "good"}
        summary = self._run(monkeypatch, styles)["summary"]
        assert summary["verdict"] == "FAIL_DECISION"

    def test_right_calls_keep_the_judge_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        styles = {"baseline": "bad", "description": "good", "full": "good"}
        summary = self._run(monkeypatch, styles)["summary"]
        assert summary["verdict"] == "PASS"
        assert summary["decision_check"]["gate"] == {"failed": [], "incomplete": []}
        assert runner._classify_verdict(summary["verdict"]) == 0

    def test_a_failing_baseline_and_full_positive_do_not_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        styles = {"baseline": "bad", "description": "good", "full": "good"}
        assert self._run(monkeypatch, styles)["summary"]["verdict"] == "PASS"

    @pytest.mark.parametrize("termination", ["refusal", "token_limit", "incomplete"])
    def test_an_ungraded_gated_cell_withholds_the_pass(
        self, monkeypatch: pytest.MonkeyPatch, termination: str
    ) -> None:
        styles = {"baseline": "good", "description": "good", "full": "good"}
        summary = self._run(monkeypatch, styles, termination={"description": termination})[
            "summary"
        ]
        assert summary["verdict"] == "FAIL_DECISION"
        gate = summary["decision_check"]["gate"]
        assert gate["failed"] == []
        assert "positive description" in gate["incomplete"]

    def test_a_failing_judge_verdict_is_not_overwritten(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        styles = {"baseline": "bad", "description": "bad", "full": "bad"}
        result = _stub_run(
            monkeypatch,
            styles,
            rule_name="python.md",
            judge_verdict="FAIL_OVER_ACTIVATION",
        )
        assert result["summary"]["verdict"] == "FAIL_OVER_ACTIVATION"
        assert result["summary"]["decision_check"]["gate"]["failed"]

    def test_a_rule_without_description_cannot_pass_on_decisions_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        styles = {"baseline": "good", "description": "good", "full": "good"}
        summary = _stub_run(monkeypatch, styles, judge_verdict="PASS")["summary"]
        assert summary["verdict"] == "FAIL_DECISION"
        assert "positive description" in summary["decision_check"]["gate"]["incomplete"]

    def test_fail_decision_does_not_advance_the_rollback_streak(self) -> None:
        state = gate._update_reference(
            {"consecutive_activation_failures": 1}, "FAIL_DECISION", "run-1", "2026-10-18"
        )
        assert state["consecutive_activation_failures"] == 1
        assert state["last_result_counted_for_rollback"] is False
        assert state["last_verdict"] == "FAIL_DECISION"

    def test_a_rollback_verdict_still_advances_the_streak(self) -> None:
        state = gate._update_reference(
            {"consecutive_activation_failures": 1}, "FAIL_THRESHOLD", "run-1", "2026-10-18"
        )
        assert state["consecutive_activation_failures"] == 2
        assert state["last_result_counted_for_rollback"] is True
