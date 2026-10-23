"""Offline checks for tests/evals/skill-scenarios/spec.json S5 and S6 (issue #6737).

No model call. Asserts that the positive case (repeated GUI steps with a direct
machine interface) and the negative case (a frozen narrow edit) each have
responses that pass and fail for the right reason, that keyword recitation never
passes, and that the file loads through the existing rule-activation runner
against the spec skill.
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
SCENARIO_FILE = REPO_ROOT / "tests" / "evals" / "skill-scenarios" / "spec.json"
SPEC_TEMPLATE = REPO_ROOT / "templates" / "skills" / "spec.SKILL.md.tmpl"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _decision_grade as dg

    _spec = importlib.util.spec_from_file_location(
        "eval_rule_activation_sr", EVAL_DIR / "eval-rule-activation.py"
    )
    assert _spec and _spec.loader
    runner = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(runner)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))

DATA: dict[str, Any] = json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))
SCENARIOS: list[dict[str, Any]] = [s for s in DATA["scenarios"] if "decision" in s]
IDS = [s["id"] for s in SCENARIOS]
NEGATIVE_GATE = "skip-rule-not-applicable"
KEYWORDS = "capability invention interface automation reframe architecture hypothesis"


class TestScenarioSet:
    def test_one_positive_and_one_negative(self) -> None:
        gates = {s["id"]: s["expected_gate"] for s in SCENARIOS}
        assert gates == {"S5": "prefer-purpose-built-interface", "S6": NEGATIVE_GATE}

    def test_every_decision_spec_is_sound(self) -> None:
        for scenario in SCENARIOS:
            assert dg.validate_decision_spec(scenario["decision"]) is None, scenario["id"]

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
        for banned in ("capability", "invention", "reframing", "architecture"):
            assert banned not in signals.split(), f"{scenario['id']} hands the judge '{banned}'"

    def test_frozen_edit_prompt_asks_for_the_changed_line_only(self) -> None:
        """A live run (2026-10-20) got a correct IMPLEMENT whose EVIDENCE line also
        argued against the daemon. The evidence floor rejects those words by
        design, so the prompt must say the line is code and nothing else."""
        s6 = next(s for s in SCENARIOS if s["id"] == "S6")
        text = " ".join(s6["input"].split())
        assert "EVIDENCE is the changed line of code and nothing else" in text
        assert "no commentary" in text

    def test_file_loads_through_the_runner_against_the_spec_skill(self) -> None:
        loaded = runner._load_scenarios_file(str(SCENARIO_FILE))
        assert not isinstance(loaded, int), f"runner refused the file with exit {loaded}"
        data, (primary, reference) = loaded
        assert primary.parent.name == "spec"
        assert primary.name == "SKILL.md"
        assert reference is None
        assert data["skill_id"] == "spec"

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
            result = dg.grade_decision(spec, response)
            assert result.reason == dg.REASON_WRONG_DECISION, (scenario["id"], result)

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
            assert result.reason == dg.REASON_EVIDENCE_MISMATCH, (scenario["id"], result)

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


class TestEvidenceProbes:
    @pytest.mark.parametrize(
        ("scenario_id", "evidence"),
        [
            ("S5", "/api/v1/failures, no clicks needed, compare one team to its export"),
            ("S5", "GET /api/v1/failures?team=7 and diff the rows against the CSV"),
            ("S5", "/api/v1/failures; row count must equal the dashboard export"),
            ("S6", "print(json.dumps(summary, sort_keys=True))"),
            ("S6", "json.dumps( summary, sort_keys=True ) when args.json is set"),
        ],
    )
    def test_honest_evidence_passes(self, scenario_id: str, evidence: str) -> None:
        spec = next(s["decision"] for s in SCENARIOS if s["id"] == scenario_id)
        token = spec["expected"][0]
        result = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: {evidence}")
        assert result.passed, (scenario_id, evidence, result)

    @pytest.mark.parametrize(
        ("scenario_id", "evidence"),
        [
            ("S5", "the endpoint is cleaner"),
            ("S5", "/api/v1/failures is a good idea"),
            ("S5", "I will click through the dashboard and compare it to /api/v1/failures"),
            ("S6", "a --json flag"),
            ("S6", "json.dumps(summary) behind a new architecture"),
            ("S6", "json.dumps(summary) served from a socket"),
        ],
    )
    def test_contradicting_or_empty_evidence_fails(self, scenario_id: str, evidence: str) -> None:
        spec = next(s["decision"] for s in SCENARIOS if s["id"] == scenario_id)
        token = spec["expected"][0]
        result = dg.grade_decision(spec, f"DECISION: {token}\nEVIDENCE: {evidence}")
        assert result.reason == dg.REASON_EVIDENCE_MISMATCH, (scenario_id, evidence, result)


class TestOptionFreeVariant:
    """S7 is S5 without option names, for measuring an unprompted call (issue #6737)."""

    @staticmethod
    def _by_id(scenario_id: str) -> dict[str, Any]:
        return next(s for s in DATA["scenarios"] if s["id"] == scenario_id)

    def test_variant_is_judge_scored_and_positive(self) -> None:
        s7 = self._by_id("S7")
        assert "decision" not in s7
        assert s7["expected_gate"] == self._by_id("S5")["expected_gate"]
        assert s7["expected_signals"] == ["api/v1/failures"]

    def test_prompt_names_no_option_and_no_output_contract(self) -> None:
        text = self._by_id("S7")["input"]
        for token in ("AUTOMATE_UI", "INTERFACE", "DECISION", "EVIDENCE", "Choose"):
            assert token not in text, f"S7 prompt cues the answer with {token!r}"

    def test_prompt_keeps_the_s5_fixture_so_only_the_framing_differs(self) -> None:
        s5 = " ".join(self._by_id("S5")["input"].split())
        s7 = " ".join(self._by_id("S7")["input"].split())
        shared = s5.split(" The goal is")[0]
        assert shared in s7
        assert "GET /api/v1/failures?team=<id>" in s7
        assert "architecture is still open" in s7

    def test_prompt_drops_the_s5_cue_that_the_dashboard_is_not_the_goal(self) -> None:
        text = " ".join(self._by_id("S7")["input"].split())
        assert "dashboard is not part of the goal" not in text

    def test_expected_signals_hold_no_doctrine_keywords(self) -> None:
        signals = " ".join(self._by_id("S7")["expected_signals"]).lower()
        for banned in ("capability", "invention", "reframing", "architecture"):
            assert banned not in signals.split()

    def test_rationale_does_not_depend_on_decision_tokens(self) -> None:
        rationale = self._by_id("S7")["rationale"]
        assert "AUTOMATE_UI" not in rationale
        assert "INTERFACE" not in rationale

    def test_scenario_ids_stay_unique(self) -> None:
        ids = [s["id"] for s in DATA["scenarios"]]
        assert len(ids) == len(set(ids))

    def test_loader_accepts_the_file_with_both_pools(self) -> None:
        loaded = runner._load_scenarios_file(str(SCENARIO_FILE))
        assert not isinstance(loaded, int), f"runner refused the file with exit {loaded}"
        gates = [runner._is_negative_gate(s["expected_gate"]) for s in loaded[0]["scenarios"]]
        assert any(gates)
        assert not all(gates)

    def test_loader_refuses_a_variant_with_a_near_miss_gate(self, tmp_path: Path) -> None:
        broken = json.loads(json.dumps(DATA))
        next(s for s in broken["scenarios"] if s["id"] == "S7")["expected_gate"] = ""
        target = tmp_path / "spec.json"
        target.write_text(json.dumps(broken), encoding="utf-8")
        assert runner._load_scenarios_file(str(target)) == 2


class TestSourceCarriesTheCheck:
    """The scenarios target the spec skill, so its source must carry the check."""

    def test_spec_template_holds_the_reframing_check_once(self) -> None:
        text = SPEC_TEMPLATE.read_text(encoding="utf-8")
        assert text.count("#### Reframing check") == 1
        for needle in (
            "Workflow automation",
            "Capability invention",
            "authority boundary",
            "falsifiable",
            "frozen",
        ):
            assert needle in text, needle
