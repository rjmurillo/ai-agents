"""Offline checks for tests/evals/rule-scenarios/capability-first.json (issue #6658).

Asserts the frozen scenario set against the acceptance criteria without a model
call: every decision class has a known-good response that passes and a
known-bad response that fails, keyword-only output never passes, and the file
loads and runs through the existing rule-activation runner.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
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

    _spec = importlib.util.spec_from_file_location(
        "eval_rule_activation_cf", EVAL_DIR / "eval-rule-activation.py"
    )
    assert _spec and _spec.loader
    runner = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(runner)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))

DATA: dict[str, Any] = json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))
SCENARIOS: list[dict[str, Any]] = DATA["scenarios"]
IDS = [s["id"] for s in SCENARIOS]

# Required decision classes from the issue, keyed by the gate each one expects.
POSITIVE_GATES = {
    "measure-before-estimating",
    "reuse-before-building",
    "keep-tradeoff-explicit",
    "verify-postcondition",
    "mark-unverified-without-comparison",
}
KEYWORDS = "capability map GPS measure verify reuse instrument competence judgment"


class TestScenarioSet:
    def test_five_positive_classes_and_one_negative(self) -> None:
        positives = {
            s["expected_gate"]
            for s in SCENARIOS
            if s["expected_gate"] != "skip-rule-not-applicable"
        }
        negatives = [s for s in SCENARIOS if s["expected_gate"] == "skip-rule-not-applicable"]
        assert positives == POSITIVE_GATES
        assert len(negatives) >= 1

    def test_every_scenario_declares_a_sound_decision_spec(self) -> None:
        for scenario in SCENARIOS:
            assert dg.validate_decision_spec(scenario["decision"]) is None, scenario["id"]

    def test_ids_are_unique(self) -> None:
        assert len(IDS) == len(set(IDS))

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_prompt_inlines_the_fixture_and_the_output_contract(
        self, scenario: dict[str, Any]
    ) -> None:
        text = scenario["input"]
        assert "DECISION:" in text
        assert "EVIDENCE:" in text
        for option in scenario["decision"]["options"]:
            assert option in text, f"{scenario['id']} prompt omits option {option}"

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_expected_signals_hold_no_doctrine_keywords(self, scenario: dict[str, Any]) -> None:
        signals = " ".join(scenario.get("expected_signals", [])).lower()
        for banned in ("map", "gps", "capability", "competence"):
            assert banned not in signals.split(), f"{scenario['id']} hands the judge '{banned}'"

    def test_file_loads_through_the_existing_runner(self) -> None:
        loaded = runner._load_scenarios_file(str(SCENARIO_FILE))
        assert not isinstance(loaded, int), f"runner refused the file with exit {loaded}"
        data, (rule_path, reference_path) = loaded
        assert rule_path == REPO_ROOT / ".claude" / "rules" / "universal.md"
        assert reference_path is None
        assert data["rule_id"] == "capability-first"


class TestKnownResponses:
    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_known_good_passes(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        assert spec["known_good"]
        for response in spec["known_good"]:
            result = dg.grade_decision(spec, response)
            assert result.passed, (scenario["id"], result)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_known_good_variants_pass(self, scenario: dict[str, Any]) -> None:
        """False-negative control: other prompt-compliant answers must also pass.

        Each variant is a frozen phrasing the prompt allows. Tightening an
        evidence pattern without admitting these would grade phrasing, not the
        decision (round 3 review of S3, S4, S5).
        """
        spec = scenario["decision"]
        variants = spec["known_good_variants"]
        assert len(variants) >= 3, scenario["id"]
        assert len(set(variants)) == len(variants), scenario["id"]
        for response in variants:
            result = dg.grade_decision(spec, response)
            assert result.passed, (scenario["id"], response, result)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_known_bad_fails_on_the_decision(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        assert spec["known_bad"]
        for response in spec["known_bad"]:
            result = dg.grade_decision(spec, response)
            assert not result.passed, scenario["id"]
            assert result.reason == dg.REASON_WRONG_DECISION, (scenario["id"], result)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_keyword_stuffed_never_passes(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        assert len(spec["keyword_stuffed"]) >= 2
        for response in spec["keyword_stuffed"]:
            assert not dg.grade_decision(spec, response).passed, scenario["id"]

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_bare_keywords_never_pass(self, scenario: dict[str, Any]) -> None:
        assert not dg.grade_decision(scenario["decision"], KEYWORDS).passed

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_every_wrong_token_fails_even_with_good_evidence(
        self, scenario: dict[str, Any]
    ) -> None:
        spec = scenario["decision"]
        evidence = dg.grade_decision(spec, spec["known_good"][0]).evidence
        wrong = [o for o in spec["options"] if o not in spec["expected"]]
        assert wrong
        for token in wrong:
            result = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: {evidence}")
            assert result.reason == dg.REASON_WRONG_DECISION

    def test_contradicting_evidence_cases_cover_the_four_reviewed_scenarios(self) -> None:
        covered = {s["id"] for s in SCENARIOS if s["decision"].get("right_token_bad_evidence")}
        assert covered >= {"S1", "S3", "S4", "S5"}

    @pytest.mark.parametrize(
        ("scenario_id", "evidence"),
        [
            ("S4", "out/report.json isn't empty and was written"),
            ("S4", "nothing missing, exit 0"),
            ("S5", "no comparison needed, the paragraph clearly improved outcomes"),
            ("S3", "legal is fine with it, set 30 days now"),
            ("S1", "cat tests/evals/rule-scenarios/universal.json"),
            ("S1", "find tests/evals/rule-scenarios -name *.json"),
            ("S1", "ls tests/evals/rule-scenarios"),
            ("S3", "Legal owns it, so set 30 days now"),
            ("S4", "total 0 is fine, report.json was written"),
            ("S4", "report.json is not missing and not empty"),
            ("S5", "no data exists, but it improves outcomes"),
            ("S1", "rg says about 3 files in rule-scenarios"),
            ("S1", "I would grep for it; about 3 universal.md files"),
            ("S1", "python3 -c 'print(len(open(\"universal.md\").read()))' rule-scenarios"),
        ],
    )
    def test_reviewed_contradicting_evidence_probes_fail(
        self, scenario_id: str, evidence: str
    ) -> None:
        spec = next(s["decision"] for s in SCENARIOS if s["id"] == scenario_id)
        token = spec["expected"][0]
        result = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: {evidence}")
        assert result.reason == dg.REASON_EVIDENCE_MISMATCH, (scenario_id, evidence, result)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_hedged_decision_line_never_passes(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        evidence = dg.grade_decision(spec, spec["known_good"][0]).evidence
        first, second = spec["options"][0], spec["options"][1]
        result = dg.grade_decision(spec, f"DECISION: {first} or {second}\nEVIDENCE: {evidence}")
        assert (result.passed, result.reason) == (False, dg.REASON_AMBIGUOUS), scenario["id"]

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_right_token_with_contradicting_evidence_fails(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        for response in spec.get("right_token_bad_evidence", []):
            result = dg.grade_decision(spec, response)
            assert result.decision in {t.upper() for t in spec["expected"]}, scenario["id"]
            assert result.reason == dg.REASON_EVIDENCE_MISMATCH, (scenario["id"], result)

    @pytest.mark.parametrize(
        ("scenario_id", "evidence"),
        [
            ("S4", "total 0 in out/, so no report was written"),
            ("S4", "out/report.json does not exist"),
            ("S4", "the listing shows total 0 and report.json was not created"),
            ("S5", "unmeasured, no comparison run exists"),
            ("S5", "not yet measured against a baseline"),
            ("S3", "the account team has not named affected customers"),
            ("S3", "Legal has not said whether any contract requires 90 days"),
            ("S5", "none exists: no outcome data, effect unmeasured"),
            (
                "S1",
                "python3 -c \"import glob,json;print(sum(json.load(open(p)).get('rule_path')"
                "=='.claude/rules/universal.md' for p in glob.glob("
                "'tests/evals/rule-scenarios/*.json')))\"",
            ),
            ("S1", "`$ grep -l universal.md tests/evals/rule-scenarios/*.json | wc -l`"),
            ("S1", "cd tests/evals/rule-scenarios && rg -l universal.md | wc -l"),
            ("S1", "ls tests/evals/rule-scenarios | xargs grep -l universal.md | wc -l"),
            ("S3", "Legal owns this call."),
            ("S3", "Does any customer contract require 90 days?"),
            ("S4", "out/ is empty, report.json is missing"),
            ("S4", "out/report.json is absent"),
            ("S5", "None exists."),
            ("S5", "No with/without comparison was run."),
            ("S5", "there is no A/B run yet"),
        ],
    )
    def test_honest_variants_of_the_evidence_still_pass(
        self, scenario_id: str, evidence: str
    ) -> None:
        spec = next(s["decision"] for s in SCENARIOS if s["id"] == scenario_id)
        token = spec["expected"][0]
        result = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: {evidence}")
        assert result.passed, (scenario_id, evidence, result)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_right_token_without_fixture_evidence_fails(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        token = spec["expected"][0]
        bare = dg.grade_decision(spec, f"DECISION: {token}")
        assert bare.reason == dg.REASON_NO_EVIDENCE

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_right_token_with_empty_claim_fails_the_evidence_check(
        self, scenario: dict[str, Any]
    ) -> None:
        spec = scenario["decision"]
        token = spec["expected"][0]
        result = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: zzz qqq")
        assert result.reason == dg.REASON_EVIDENCE_MISMATCH


def _judge_ok(*_a: object, **_kw: object) -> dict[str, object]:
    return {"activation_score": 3, "citation_score": 3, "behavior_score": 3, "judge_failed": False}


def _stub_run(monkeypatch: pytest.MonkeyPatch, per_mechanism: dict[str, str]) -> dict[str, Any]:
    """Run every scenario through `_process_one_rule` with stubbed model calls.

    `per_mechanism` maps a system-prompt marker to the response style the stub
    returns: "good" for each scenario's first known_good, "bad" for known_bad.
    """
    by_input = {s["input"]: s for s in SCENARIOS}

    def fake_call_api(_key: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        scenario = by_input[messages[0]["content"]]
        system = kwargs.get("system") or ""
        style = per_mechanism["full" if system else "baseline"]
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
    rule_path = REPO_ROOT / ".claude" / "rules" / "universal.md"
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


class TestRunnerRefusals:
    def _write(self, tmp_path: Path, mutate: Any) -> Path:
        data = json.loads(json.dumps(DATA))
        mutate(data)
        target = tmp_path / "scenarios.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        return target

    def test_malformed_decision_spec_is_refused_with_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = self._write(tmp_path, lambda d: d["scenarios"][0]["decision"].pop("expected"))
        assert runner._load_scenarios_file(str(target)) == 2
        assert "decision.expected" in capsys.readouterr().err

    def test_spec_that_cannot_fail_is_refused(self, tmp_path: Path) -> None:
        def mutate(d: dict[str, Any]) -> None:
            d["scenarios"][0]["decision"]["expected"] = list(
                d["scenarios"][0]["decision"]["options"]
            )

        assert runner._load_scenarios_file(str(self._write(tmp_path, mutate))) == 2


class TestDryRunCli:
    def test_dry_run_exits_zero_and_reports_decision_graded_count(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(EVAL_DIR / "eval-rule-activation.py"),
                "--scenarios",
                str(SCENARIO_FILE),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert f"decision-graded scenarios: {len(SCENARIOS)}" in proc.stdout
        assert "UNMEASURED" in proc.stdout
