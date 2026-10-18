"""Unit tests for scripts/eval/_decision_grade.py (issue #6658).

The grader reads only the DECISION and EVIDENCE lines, so rule vocabulary in the
prose around them cannot change a result.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
sys.path.insert(0, str(EVAL_DIR))
try:
    import _decision_grade as dg
finally:
    sys.path.remove(str(EVAL_DIR))

SPEC: dict[str, Any] = {
    "options": ["MEASURE", "ESTIMATE"],
    "expected": ["MEASURE"],
    "evidence_all": [r"\b(rg|grep)\b"],
}


class TestGradeDecision:
    def test_pass(self) -> None:
        result = dg.grade_decision(SPEC, "DECISION: MEASURE\nEVIDENCE: rg -c foo")
        assert result.passed is True
        assert result.reason == dg.REASON_PASS
        assert result.decision == "MEASURE"
        assert result.evidence == "rg -c foo"

    @pytest.mark.parametrize(
        "response",
        [
            "**DECISION:** MEASURE\n**EVIDENCE:** rg -c foo",
            "- DECISION: measure\n- EVIDENCE: GREP foo",
            "> DECISION : `MEASURE`\n> EVIDENCE: `rg foo`",
        ],
    )
    def test_formatting_variants_pass(self, response: str) -> None:
        assert dg.grade_decision(SPEC, response).passed is True

    @pytest.mark.parametrize(
        "decision_line",
        [
            "DECISION: MEASURE or ESTIMATE",
            "DECISION: MEASURE, then ESTIMATE",
            "DECISION: MEASURE (ESTIMATE if no shell)",
            "DECISION: <MEASURE or ESTIMATE>",
        ],
    )
    def test_hedged_decision_line_fails_as_ambiguous(self, decision_line: str) -> None:
        result = dg.grade_decision(SPEC, f"{decision_line}\nEVIDENCE: rg -c foo")
        assert (result.passed, result.reason) == (False, dg.REASON_AMBIGUOUS)

    def test_hedged_line_beside_a_clean_line_is_ambiguous(self) -> None:
        text = "DECISION: MEASURE\nDECISION: MEASURE or ESTIMATE\nEVIDENCE: rg -c foo"
        assert dg.grade_decision(SPEC, text).reason == dg.REASON_AMBIGUOUS

    @pytest.mark.parametrize(
        "decision_line",
        [
            "DECISION: MEASURE.",
            "**DECISION: MEASURE**",
            "DECISION: `MEASURE` ",
            "DECISION: MEASURE\r",
        ],
    )
    def test_trailing_emphasis_and_period_still_pass(self, decision_line: str) -> None:
        assert dg.grade_decision(SPEC, f"{decision_line}\nEVIDENCE: rg -c foo").passed is True

    @pytest.mark.parametrize("marker", ["1.", "2)", "10. ", "- 3."])
    def test_numbered_list_marker_is_allowed(self, marker: str) -> None:
        text = f"{marker} DECISION: MEASURE\n{marker} EVIDENCE: rg -c foo"
        result = dg.grade_decision(SPEC, text)
        assert (result.passed, result.decision) == (True, "MEASURE")

    def test_number_not_followed_by_a_label_is_not_a_contract_line(self) -> None:
        text = "1. I will measure.\nEVIDENCE: rg -c foo"
        assert dg.grade_decision(SPEC, text).reason == dg.REASON_NO_DECISION

    def test_decision_token_on_the_next_line_is_not_a_bare_token(self) -> None:
        result = dg.grade_decision(SPEC, "DECISION:\nMEASURE\nEVIDENCE: rg -c foo")
        assert (result.passed, result.reason) == (False, dg.REASON_AMBIGUOUS)

    def test_evidence_value_on_the_next_line_grades_no_evidence(self) -> None:
        result = dg.grade_decision(SPEC, "DECISION: MEASURE\nEVIDENCE:\nrg -c foo")
        assert (result.passed, result.reason) == (False, dg.REASON_NO_EVIDENCE)

    def test_no_decision_line(self) -> None:
        result = dg.grade_decision(SPEC, "I would measure it. EVIDENCE: rg foo")
        assert (result.passed, result.reason) == (False, dg.REASON_NO_DECISION)

    def test_lowercase_label_is_not_a_contract_line(self) -> None:
        text = "- decision: measure\n- evidence: GREP foo"
        assert dg.grade_decision(SPEC, text).reason == dg.REASON_NO_DECISION

    def test_prose_decision_label_does_not_make_a_correct_reply_ambiguous(self) -> None:
        text = "Decision: I would run rg first.\nDECISION: MEASURE\nEVIDENCE: rg -c foo"
        result = dg.grade_decision(SPEC, text)
        assert (result.passed, result.reason, result.decision) == (True, dg.REASON_PASS, "MEASURE")

    def test_prose_evidence_label_is_not_read_as_evidence(self) -> None:
        text = "Evidence: none yet.\nDECISION: MEASURE\nEVIDENCE: rg -c foo"
        assert dg.grade_decision(SPEC, text).evidence == "rg -c foo"

    def test_two_uppercase_decision_lines_still_conflict_beside_prose(self) -> None:
        text = "Decision: maybe.\nDECISION: MEASURE\nDECISION: ESTIMATE\nEVIDENCE: rg foo"
        assert dg.grade_decision(SPEC, text).reason == dg.REASON_AMBIGUOUS

    def test_decision_must_start_a_line(self) -> None:
        text = "Prose says DECISION: MEASURE mid-line.\nEVIDENCE: rg foo"
        assert dg.grade_decision(SPEC, text).reason == dg.REASON_NO_DECISION

    def test_two_different_tokens_are_ambiguous(self) -> None:
        text = "DECISION: MEASURE\nDECISION: ESTIMATE\nEVIDENCE: rg foo"
        assert dg.grade_decision(SPEC, text).reason == dg.REASON_AMBIGUOUS

    def test_repeated_same_token_is_not_ambiguous_but_breaks_the_contract(self) -> None:
        text = "DECISION: MEASURE\nDECISION: measure\nEVIDENCE: rg foo"
        result = dg.grade_decision(SPEC, text)
        assert (result.passed, result.reason) == (False, dg.REASON_CONTRACT_ORDER)

    def test_token_outside_options(self) -> None:
        result = dg.grade_decision(SPEC, "DECISION: MAYBE\nEVIDENCE: rg foo")
        assert (result.reason, result.decision) == (dg.REASON_UNKNOWN_TOKEN, "MAYBE")

    def test_wrong_decision(self) -> None:
        result = dg.grade_decision(SPEC, "DECISION: ESTIMATE\nEVIDENCE: rg foo")
        assert (result.passed, result.reason) == (False, dg.REASON_WRONG_DECISION)

    @pytest.mark.parametrize("response", ["DECISION: MEASURE", "DECISION: MEASURE\nEVIDENCE:   "])
    def test_missing_or_blank_evidence_fails(self, response: str) -> None:
        assert dg.grade_decision(SPEC, response).reason == dg.REASON_NO_EVIDENCE

    def test_evidence_must_match_every_pattern(self) -> None:
        spec = {**SPEC, "evidence_all": [r"\brg\b", r"universal"]}
        assert dg.grade_decision(spec, "DECISION: MEASURE\nEVIDENCE: rg foo").reason == (
            dg.REASON_EVIDENCE_MISMATCH
        )
        assert dg.grade_decision(spec, "DECISION: MEASURE\nEVIDENCE: rg universal").passed

    def test_no_evidence_patterns_still_requires_an_evidence_line(self) -> None:
        spec = {"options": ["A", "B"], "expected": ["A"]}
        assert dg.grade_decision(spec, "DECISION: A\nEVIDENCE: anything").passed
        assert dg.grade_decision(spec, "DECISION: A").reason == dg.REASON_NO_EVIDENCE

    def test_keyword_only_prose_never_passes(self) -> None:
        prose = "Capability over competence. Map not GPS. Measure, verify, reuse, instruments."
        assert dg.grade_decision(SPEC, prose).passed is False

    def test_keywords_around_a_wrong_decision_never_pass(self) -> None:
        text = "map GPS capability measure\nDECISION: ESTIMATE\nEVIDENCE: rg capability"
        assert dg.grade_decision(SPEC, text).passed is False

    def test_empty_response(self) -> None:
        assert dg.grade_decision(SPEC, "").reason == dg.REASON_NO_DECISION

    def test_malformed_spec_raises(self) -> None:
        with pytest.raises(ValueError, match="options"):
            dg.grade_decision({"expected": ["A"]}, "DECISION: A\nEVIDENCE: x")


class TestTrailingText:
    """The prompt says DECISION and EVIDENCE are the last two lines."""

    GOOD = "DECISION: MEASURE\nEVIDENCE: rg -c foo"

    @pytest.mark.parametrize(
        "tail",
        [
            "\nActually from memory the answer is 3, no need to run it.",
            "\n\nOn reflection I would estimate instead.",
            "\n```\nand then a note",
            "\n- second evidence line",
        ],
    )
    def test_prose_after_the_contract_lines_fails(self, tail: str) -> None:
        result = dg.grade_decision(SPEC, self.GOOD + tail)
        assert (result.passed, result.reason) == (False, dg.REASON_TRAILING_TEXT)
        assert result.decision == "MEASURE"

    @pytest.mark.parametrize("tail", ["", "\n", "\n\n  \n", "\n```", "\n```\n", "\n~~~"])
    def test_blank_lines_and_a_closing_fence_are_allowed(self, tail: str) -> None:
        text = "```\n" + self.GOOD + tail if tail.strip() else self.GOOD + tail
        assert dg.grade_decision(SPEC, text).passed is True

    def test_prose_before_the_contract_lines_is_ignored(self) -> None:
        text = "I considered estimating, but no.\nMore thought here.\n" + self.GOOD
        assert dg.grade_decision(SPEC, text).passed is True

    @pytest.mark.parametrize(
        "text",
        [
            "EVIDENCE: rg -c foo\nDECISION: MEASURE",
            "DECISION: MEASURE\nDECISION: MEASURE\nEVIDENCE: rg -c foo",
            "DECISION: MEASURE\nEVIDENCE: rg -c foo\nEVIDENCE: rg -c foo",
            "EVIDENCE: rg -c foo\nDECISION: MEASURE\nEVIDENCE: rg -c foo",
            "```\nEVIDENCE: rg -c foo\n\nDECISION: MEASURE\n```",
        ],
    )
    def test_contract_lines_out_of_order_or_repeated_fail(self, text: str) -> None:
        result = dg.grade_decision(SPEC, text)
        assert (result.passed, result.reason) == (False, dg.REASON_CONTRACT_ORDER)
        assert result.decision == "MEASURE"

    def test_reversed_order_does_not_mask_a_wrong_decision(self) -> None:
        result = dg.grade_decision(SPEC, "EVIDENCE: rg -c foo\nDECISION: ESTIMATE")
        assert result.reason == dg.REASON_WRONG_DECISION

    def test_reversed_order_does_not_mask_missing_evidence_patterns(self) -> None:
        result = dg.grade_decision(SPEC, "EVIDENCE: from memory\nDECISION: MEASURE")
        assert result.reason == dg.REASON_EVIDENCE_MISMATCH

    def test_a_reversal_between_the_contract_lines_fails(self) -> None:
        text = "DECISION: MEASURE\nActually no, I will estimate instead.\nEVIDENCE: rg -c foo"
        result = dg.grade_decision(SPEC, text)
        assert (result.passed, result.reason) == (False, dg.REASON_TRAILING_TEXT)
        assert result.decision == "MEASURE"

    def test_a_reversal_between_evidence_and_decision_fails(self) -> None:
        text = "EVIDENCE: rg -c foo\nOn reflection, estimate.\nDECISION: MEASURE"
        assert dg.grade_decision(SPEC, text).reason == dg.REASON_TRAILING_TEXT

    @pytest.mark.parametrize("gap", ["", "\n", "\n  \n", "\n```\n"])
    def test_blank_or_fence_lines_between_the_contract_lines_pass(self, gap: str) -> None:
        text = "DECISION: MEASURE\n" + gap + "EVIDENCE: rg -c foo"
        assert dg.grade_decision(SPEC, text).passed is True

    def test_trailing_text_does_not_mask_a_wrong_decision(self) -> None:
        result = dg.grade_decision(SPEC, "DECISION: ESTIMATE\nEVIDENCE: rg x\nnote")
        assert result.reason == dg.REASON_WRONG_DECISION

    def test_windows_line_endings_pass(self) -> None:
        assert dg.grade_decision(SPEC, "DECISION: MEASURE\r\nEVIDENCE: rg -c foo\r\n").passed


class TestValidateDecisionSpec:
    def test_valid_spec(self) -> None:
        assert dg.validate_decision_spec(SPEC) is None

    @pytest.mark.parametrize(
        ("spec", "fragment"),
        [
            ("nope", "must be an object"),
            ({"expected": ["A"]}, "decision.options"),
            ({"options": ["A", "B"]}, "decision.expected"),
            ({"options": [], "expected": ["A"]}, "decision.options"),
            ({"options": ["A", ""], "expected": ["A"]}, "decision.options"),
            ({"options": ["A"], "expected": ["A"]}, "at least two"),
            ({"options": ["A", "B"], "expected": ["C"]}, "subset"),
            ({"options": ["A", "B"], "expected": ["A", "B"]}, "no response could fail"),
            ({"options": ["A-1", "B"], "expected": ["B"]}, "letters and underscores"),
            ({**SPEC, "evidence_all": "rg"}, "evidence_all"),
            ({**SPEC, "evidence_all": [""]}, "evidence_all"),
            ({**SPEC, "evidence_all": ["("]}, "not a valid regex"),
        ],
    )
    def test_rejects(self, spec: object, fragment: str) -> None:
        error = dg.validate_decision_spec(spec)
        assert error is not None
        assert fragment in error


def _result(negative: bool, **cells: dict[str, Any] | None) -> dict[str, Any]:
    mechanisms: dict[str, Any] = {}
    for mech, decision in cells.items():
        mechanisms[mech] = {"decision": decision} if decision is not None else {"error": "x"}
    return {"decision_declared": True, "negative_case": negative, "mechanisms": mechanisms}


PASS = {"passed": True, "reason": dg.REASON_PASS}
FAIL = {"passed": False, "reason": dg.REASON_WRONG_DECISION}
MECHS = ("baseline", "description", "full")


class TestSummarizeDecisions:
    def test_counts_per_mechanism_and_pool(self) -> None:
        results = [
            _result(False, baseline=FAIL, description=PASS, full=PASS),
            _result(False, baseline=PASS, description=PASS, full=PASS),
            _result(True, baseline=FAIL, description=PASS, full=PASS),
        ]
        summary = dg.summarize_decisions(results, MECHS)
        base = summary["per_mechanism"]["baseline"]
        assert base["positive"]["passed"] == 1
        assert base["positive"]["graded"] == 2
        assert base["positive"]["pass_rate"] == 0.5
        assert base["positive"]["failure_reasons"] == [dg.REASON_WRONG_DECISION]
        assert base["negative"]["pass_rate"] == 0.0
        assert summary["per_mechanism"]["full"]["positive"]["pass_rate"] == 1.0

    def test_ungraded_cell_is_unmeasured_not_zero(self) -> None:
        results = [_result(False, baseline=PASS, description=None, full=None)]
        summary = dg.summarize_decisions(results, MECHS)
        cell = summary["per_mechanism"]["description"]["positive"]
        assert cell["declared"] == 1
        assert cell["graded"] == 0
        assert cell["pass_rate"] == dg.UNMEASURED

    def test_scenarios_without_a_spec_are_ignored(self) -> None:
        plain = {"negative_case": False, "mechanisms": {"baseline": {"scores": {}}}}
        summary = dg.summarize_decisions([plain], MECHS)
        assert summary["declared"] == 0

    def test_empty_input(self) -> None:
        assert dg.summarize_decisions([], MECHS)["declared"] == 0


class TestRenderDecisionCheck:
    def test_renders_nothing_when_no_scenario_declares_a_spec(self) -> None:
        assert dg.render_decision_check(dg.summarize_decisions([], MECHS), MECHS) == ""

    def test_gap_reported_only_when_both_arms_are_fully_graded(self) -> None:
        results = [
            _result(False, baseline=FAIL, description=None, full=PASS),
            _result(False, baseline=FAIL, description=None, full=PASS),
        ]
        text = dg.render_decision_check(dg.summarize_decisions(results, MECHS), MECHS)
        assert "gap full vs baseline: +1.0 (descriptive)" in text
        assert f"gap description vs baseline: {dg.UNMEASURED}" in text
        assert "not evidence of uplift" in text
        assert f"Tool calls and cost per cell: {dg.UNMEASURED}" in text

    def test_gap_unmeasured_when_baseline_partially_graded(self) -> None:
        results = [
            _result(False, baseline=PASS, description=PASS, full=PASS),
            _result(False, baseline=None, description=PASS, full=PASS),
        ]
        text = dg.render_decision_check(dg.summarize_decisions(results, MECHS), MECHS)
        assert f"gap full vs baseline: {dg.UNMEASURED}" in text
        assert "1/1 of 2" in text

    def test_dry_run_cells_render_unmeasured(self) -> None:
        results = [_result(False, baseline=None, description=None, full=None)]
        text = dg.render_decision_check(dg.summarize_decisions(results, MECHS), MECHS)
        assert text.count(dg.UNMEASURED) >= 3


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return dg.summarize_decisions(results, MECHS)


class TestDecisionGate:
    """A judge PASS must not survive wrong or unmeasured calls."""

    POS = ["description"]
    NEG = ["description", "full"]

    def test_all_gated_cells_pass(self) -> None:
        results = [
            _result(False, baseline=FAIL, description=PASS, full=PASS),
            _result(True, baseline=FAIL, description=PASS, full=PASS),
        ]
        gate = dg.decision_gate(_summary(results), self.POS, self.NEG)
        assert gate == {"failed": [], "incomplete": []}

    def test_a_wrong_call_on_the_gated_positive_mechanism_fails(self) -> None:
        results = [
            _result(False, baseline=PASS, description=FAIL, full=PASS),
            _result(False, baseline=PASS, description=PASS, full=PASS),
        ]
        gate = dg.decision_gate(_summary(results), self.POS, self.NEG)
        assert gate["failed"] == ["positive description"]
        assert gate["incomplete"] == []

    def test_a_wrong_call_on_a_negative_gate_mechanism_fails(self) -> None:
        results = [_result(True, baseline=PASS, description=PASS, full=FAIL)]
        gate = dg.decision_gate(_summary(results), self.POS, self.NEG)
        assert gate["failed"] == ["negative full"]

    def test_baseline_failures_never_gate(self) -> None:
        results = [
            _result(False, baseline=FAIL, description=PASS, full=PASS),
            _result(True, baseline=FAIL, description=PASS, full=PASS),
        ]
        assert dg.decision_gate(_summary(results), self.POS, self.NEG)["failed"] == []

    def test_full_positive_is_diagnostic_and_does_not_gate(self) -> None:
        results = [_result(False, baseline=PASS, description=PASS, full=FAIL)]
        assert dg.decision_gate(_summary(results), self.POS, self.NEG)["failed"] == []

    def test_an_ungraded_declared_cell_is_incomplete_not_failed(self) -> None:
        results = [
            _result(False, baseline=PASS, description=PASS, full=PASS),
            _result(False, baseline=PASS, description=None, full=PASS),
        ]
        gate = dg.decision_gate(_summary(results), self.POS, self.NEG)
        assert gate == {"failed": [], "incomplete": ["positive description"]}

    def test_a_mechanism_with_nothing_graded_is_incomplete(self) -> None:
        results = [_result(False, baseline=PASS, description=None, full=None)]
        gate = dg.decision_gate(_summary(results), self.POS, self.NEG)
        assert gate["incomplete"] == ["positive description"]

    def test_failed_and_incomplete_can_both_be_reported(self) -> None:
        results = [
            _result(False, baseline=PASS, description=FAIL, full=PASS),
            _result(False, baseline=PASS, description=None, full=PASS),
        ]
        gate = dg.decision_gate(_summary(results), self.POS, self.NEG)
        assert gate == {"failed": ["positive description"], "incomplete": ["positive description"]}

    def test_a_pool_with_no_declared_scenario_gates_nothing(self) -> None:
        results = [_result(False, baseline=PASS, description=PASS, full=PASS)]
        gate = dg.decision_gate(_summary(results), self.POS, self.NEG)
        assert gate == {"failed": [], "incomplete": []}

    def test_render_names_the_gate_only_when_it_trips(self) -> None:
        results = [_result(False, baseline=PASS, description=FAIL, full=PASS)]
        summary = _summary(results)
        clean = dg.render_decision_check(summary, MECHS)
        assert "Decision gate" not in clean
        summary["gate"] = dg.decision_gate(summary, self.POS, self.NEG)
        text = dg.render_decision_check(summary, MECHS)
        assert f"a judge PASS becomes {dg.VERDICT_FAIL_DECISION}" in text
        assert "failed: positive description" in text
