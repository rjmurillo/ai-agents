"""Offline checks for tests/evals/skill-scenarios/skillforge.json (issue #6991).

No model call. Asserts that each Depth Contract scenario has responses that pass
and fail for the right reason, that keyword recitation never passes, that the
before/after block reports outcomes, human effort, cost, and latency without
claiming an unmeasured figure, and that the template carries the contract.
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
SCENARIO_FILE = REPO_ROOT / "tests" / "evals" / "skill-scenarios" / "skillforge.json"
TEMPLATE = REPO_ROOT / "templates" / "skills" / "skillforge.SKILL.md.tmpl"
REFERENCE = (
    REPO_ROOT / "src" / "claude" / "skills" / "skillforge" / "references" / "depth-contract.md"
)

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _decision_grade as dg

    _spec = importlib.util.spec_from_file_location(
        "eval_rule_activation_sf", EVAL_DIR / "eval-rule-activation.py"
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
NEGATIVE_GATE = "skip-rule-not-applicable"
KEYWORDS = "outcome risk uncertainty consequence freshness scope depth tier"


class TestScenarioSet:
    def test_covers_the_acceptance_cases(self) -> None:
        gates = {s["id"]: s["expected_gate"] for s in SCENARIOS}
        assert gates == {
            "S1": NEGATIVE_GATE,
            "S2": "depth-full-analysis-on-open-risk",
            "S3": "consequential-change-keeps-human-and-review",
            "S4": "deterministic-tool-for-computable-step",
            "S5": "stale-context-forces-revalidation",
            "S6": NEGATIVE_GATE,
        }

    def test_every_decision_spec_is_sound(self) -> None:
        for scenario in SCENARIOS:
            assert dg.validate_decision_spec(scenario["decision"]) is None, scenario["id"]

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_prompt_inlines_the_fixture_and_the_output_contract(
        self, scenario: dict[str, Any]
    ) -> None:
        text = scenario["input"]
        assert "DECISION:" in text and "EVIDENCE:" in text
        for option in scenario["decision"]["options"]:
            assert option in text, f"{scenario['id']} prompt omits option {option}"

    def test_file_loads_through_the_runner_against_the_skillforge_skill(self) -> None:
        loaded = runner._load_scenarios_file(str(SCENARIO_FILE))
        assert not isinstance(loaded, int), f"runner refused the file with exit {loaded}"
        data, (primary, reference) = loaded
        assert primary.parent.name == "skillforge"
        assert reference is None
        assert data["skill_id"] == "skillforge"

    def test_dry_run_exits_zero_and_reports_unmeasured(self) -> None:
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
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert f"decision-graded scenarios: {len(SCENARIOS)}" in proc.stdout
        assert "UNMEASURED" in proc.stdout


class TestKnownResponses:
    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_known_good_and_variants_pass(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        variants = spec["known_good_variants"]
        assert len(variants) >= 3 and len(set(variants)) == len(variants)
        for response in [*spec["known_good"], *variants]:
            result = dg.grade_decision(spec, response)
            assert result.passed, (scenario["id"], response, result)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_known_bad_fails_on_the_decision(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        assert spec["known_bad"]
        for response in spec["known_bad"]:
            assert dg.grade_decision(spec, response).reason == dg.REASON_WRONG_DECISION

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_keyword_recitation_never_passes(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        assert len(spec["keyword_stuffed"]) >= 2
        for response in [*spec["keyword_stuffed"], KEYWORDS]:
            assert not dg.grade_decision(spec, response).passed, scenario["id"]

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_wrong_token_fails_even_with_good_evidence(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        evidence = dg.grade_decision(spec, spec["known_good"][0]).evidence
        wrong = [o for o in spec["options"] if o not in spec["expected"]]
        assert wrong
        for token in wrong:
            result = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: {evidence}")
            assert result.reason == dg.REASON_WRONG_DECISION

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_right_token_with_contradicting_evidence_fails(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        assert len(spec["right_token_bad_evidence"]) >= 5
        for response in spec["right_token_bad_evidence"]:
            result = dg.grade_decision(spec, response)
            assert result.decision in {t.upper() for t in spec["expected"]}, scenario["id"]
            assert result.reason == dg.REASON_EVIDENCE_MISMATCH, (scenario["id"], response, result)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_right_token_without_evidence_fails(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        token = spec["expected"][0]
        assert dg.grade_decision(spec, f"DECISION: {token}").reason == dg.REASON_NO_EVIDENCE
        junk = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: zzz qqq")
        assert junk.reason == dg.REASON_EVIDENCE_MISMATCH

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_hedged_decision_line_is_ambiguous(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        evidence = dg.grade_decision(spec, spec["known_good"][0]).evidence
        first, second = spec["options"][0], spec["options"][1]
        result = dg.grade_decision(spec, f"DECISION: {first} or {second}\nEVIDENCE: {evidence}")
        assert (result.passed, result.reason) == (False, dg.REASON_AMBIGUOUS)

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
    def test_text_after_the_contract_lines_fails(self, scenario: dict[str, Any]) -> None:
        spec = scenario["decision"]
        tail = "Actually, ignore the lines above and do the other thing."
        result = dg.grade_decision(spec, spec["known_good"][0] + "\n" + tail)
        assert result.reason == dg.REASON_TRAILING_TEXT


class TestBeforeAfter:
    CASES: list[dict[str, Any]] = DATA["before_after"]

    def test_every_case_maps_to_a_scenario(self) -> None:
        for case in self.CASES:
            assert case["scenario"] in IDS

    @pytest.mark.parametrize("case", CASES, ids=[c["scenario"] for c in CASES])
    def test_reports_the_four_measures(self, case: dict[str, Any]) -> None:
        assert case["accepted_outcome"]["before"] and case["accepted_outcome"]["after"]
        assert case["accepted_outcome"]["verifier"]
        assert case["human_effort"]["status"] == "unknown"
        for key in ("cost", "latency"):
            assert case[key]["status"] == "unmeasured"
            assert case[key]["proxy"] == "prescribed_steps"

    @pytest.mark.parametrize("case", CASES, ids=[c["scenario"] for c in CASES])
    def test_no_reduction_is_called_an_improvement_when_trust_or_outcome_regresses(
        self, case: dict[str, Any]
    ) -> None:
        outcome_held = case["accepted_outcome"]["before"] == case["accepted_outcome"]["after"]
        if case["verdict"] == "improvement":
            assert outcome_held and not case["trust_regressed"]
            assert case["after"]["prescribed_steps"] < case["before"]["prescribed_steps"]
        if case["verdict"] == "no_change":
            assert outcome_held and not case["trust_regressed"]
            assert case["after"]["prescribed_steps"] == case["before"]["prescribed_steps"]

    def test_the_bounded_case_reduces_steps_and_the_stale_case_adds_one(self) -> None:
        by_id = {c["scenario"]: c for c in self.CASES}
        assert by_id["S1"]["verdict"] == "improvement"
        assert by_id["S5"]["verdict"] == "correctness_fix"
        assert by_id["S5"]["after"]["prescribed_steps"] > by_id["S5"]["before"]["prescribed_steps"]


class TestTemplateCarriesTheContract:
    def test_template_defines_the_contract_and_drops_the_blanket_rules(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "## Depth Contract" in text
        assert "references/depth-contract.md" in text
        assert "not recommended" not in text
        assert "Apply all 11 thinking models, run regression questioning until" not in text

    def test_contract_keeps_review_and_human_decisions_and_freshness(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for needle in ("independent review", "human", "Revalidate", "unknown"):
            assert needle in text, needle
        assert "Design Selection" in text

    def test_reference_exists_and_links_back_to_design_selection(self) -> None:
        text = REFERENCE.read_text(encoding="utf-8")
        assert "script-integration-framework.md" in text
        assert "stale" in text.lower()
