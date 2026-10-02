"""Scoring and base-side stability tests for eval-prompt-change.py (issue #5601).

Two defects, one negative control each:

1. A scenario passed only when the grader echoed a phrase. The verdict is the
   controlled label; the reason is free text. Wording must not gate.
2. A scenario flaky on the base side manufactured regressions, because the base
   prompt is fixed and its result swings between runs. That noise must not gate,
   and a genuine regression must still be caught.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    _spec = importlib.util.spec_from_file_location(
        "eval_prompt_change_stability", EVAL_DIR / "eval-prompt-change.py"
    )
    assert _spec and _spec.loader
    ev = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ev)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))

D12 = {
    "id": "D12",
    "desc": "prior art check",
    "input": "a PRD containing ## Prior Art / Constraints with a non-empty body",
    "expected_verdict": "PASS",
    "expected_reason_contains": "Prior Art / Constraints",
    "verdict_options": ["PASS", "FAIL"],
}
D6 = {
    "id": "D6",
    "desc": "degradation row",
    "input": "The optional memory backend is unavailable",
    "expected_verdict": "DEGRADED_PASS",
    "expected_reason_contains": "Serena-only",
    "verdict_options": ["DEGRADED_PASS", "HALT"],
}


def _result(sid: str, passes: int, runs: int = 3) -> dict[str, Any]:
    return {
        "scenario_id": sid,
        "passes": passes,
        "runs": runs,
        "pass_rate": passes / runs,
        "passed": passes >= -(-runs * 2 // 3),
        "flaky": 0 < passes < runs,
        "reason_mismatch_runs": 0,
        "per_run": [],
    }


def _comparison(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    security_critical: bool = False,
) -> dict[str, Any]:
    """Build a comparison the way run_comparison does, including the tier's base minimum."""
    required = ev.SECURITY_RUNS if security_critical else ev.DEFAULT_RUNS
    pairs = [
        (b, a) for b, a in zip(before, after, strict=True) if not ev.is_base_unstable(b, required)
    ]
    n = max(1, len(pairs))
    bs = sum(b["passed"] for b, _a in pairs) / n
    as_ = sum(a["passed"] for _b, a in pairs) / n
    return {
        "before_results": before,
        "after_results": after,
        "before_score": bs,
        "after_score": as_,
        "delta": as_ - bs,
        "scenario_count": len(before),
        "scored_scenario_count": len(pairs),
    }


# ---------------------------------------------------------------------------
# Defect 1: wording does not gate
# ---------------------------------------------------------------------------

REASONS = [
    "Check 9d verifies that the PriorArtBlock (## Prior Art / Constraints) is populated.",
    "Check 9d verifies that the PriorArtBlock is populated.",
    "The prior art block has content, so the gate passes.",
]


@pytest.mark.parametrize("reason", REASONS)
def test_same_verdict_scores_identically_across_reason_wordings(reason: str) -> None:
    assert ev.check_scenario_pass({"verdict": "PASS", "reason": reason}, D12) is True


def test_wrong_verdict_still_fails_whatever_the_reason() -> None:
    result = {"verdict": "FAIL", "reason": REASONS[0]}
    assert ev.check_scenario_pass(result, D12) is False


def test_not_scored_never_passes() -> None:
    assert ev.check_scenario_pass({"verdict": "PASS", "not_scored": True}, D12) is False


def test_reason_signal_reports_wording_without_gating() -> None:
    assert ev.reason_signal({"verdict": "PASS", "reason": REASONS[0]}, D12) is True
    assert ev.reason_signal({"verdict": "PASS", "reason": REASONS[1]}, D12) is False


def test_reason_signal_is_none_without_expectation_or_score() -> None:
    assert (
        ev.reason_signal({"verdict": "PASS", "reason": "x"}, {"expected_verdict": "PASS"}) is None
    )
    assert ev.reason_signal({"verdict": "PASS", "not_scored": True}, D12) is None


def _patch_judge(monkeypatch: pytest.MonkeyPatch, verdict: str, reasons: list[str]) -> None:
    calls = iter(reasons)

    def judge(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"verdict": verdict, "reason": next(calls), "raw": "", "not_scored": False}

    monkeypatch.setattr(ev, "judge_scenario", judge)
    monkeypatch.setattr(ev.time, "sleep", lambda _s: None)


def test_run_scenario_multi_counts_reason_mismatch_but_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_judge(monkeypatch, "PASS", REASONS)
    out = ev.run_scenario_multi("k", "prompt", D12, "m", 3)
    assert out["passed"] is True
    assert out["passes"] == 3
    assert out["reason_mismatch_runs"] == 2


@pytest.mark.parametrize(
    ("runs", "passes", "expected"),
    [
        (1, 1, True),
        (1, 0, False),
        (2, 1, False),
        (2, 2, True),
        (3, 1, False),
        (3, 2, True),
        (4, 2, False),
        (4, 3, True),
        (5, 3, False),
        (5, 4, True),
        (6, 4, True),
        (6, 3, False),
    ],
)
def test_pass_threshold_is_ceiling_of_two_thirds(
    monkeypatch: pytest.MonkeyPatch, runs: int, passes: int, expected: bool
) -> None:
    verdicts = iter(["PASS"] * passes + ["FAIL"] * (runs - passes))

    def judge(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"verdict": next(verdicts), "reason": "r", "raw": "", "not_scored": False}

    monkeypatch.setattr(ev, "judge_scenario", judge)
    monkeypatch.setattr(ev.time, "sleep", lambda _s: None)
    out = ev.run_scenario_multi("k", "prompt", D12, "m", runs)
    assert out["passed"] is expected


def test_run_and_report_serializes_scored_scenario_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        ev, "run_scenario_multi", _fake_multi({"D12": 2, "D6": 3}, {"D12": 0, "D6": 3})
    )
    out_file = tmp_path / "report.json"
    args = argparse.Namespace(model="m", runs=3, security_critical=False, output=str(out_file))
    with pytest.raises(SystemExit) as exc:
        ev._run_and_report("k", "base", "head", [D12, D6], args, "test")
    assert exc.value.code == 0
    comparison = json.loads(out_file.read_text(encoding="utf-8"))["comparison"]
    assert comparison["scenario_count"] == 2
    assert comparison["scored_scenario_count"] == 1


def test_behavior_preserving_edit_produces_no_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The #5600 row deletion: D6 keeps its verdict, loses the 'Serena-only' wording."""
    reasons = ["Degrade to the remaining backend."] * 3
    _patch_judge(monkeypatch, "DEGRADED_PASS", reasons)
    before = ev.run_scenario_multi("k", "base", D6, "m", 3)
    _patch_judge(monkeypatch, "DEGRADED_PASS", reasons)
    after = ev.run_scenario_multi("k", "head", D6, "m", 3)
    gate = ev.acceptance_gate(_comparison([before], [after]))
    assert gate["verdict"] == "PASS"
    assert gate["regressions"] == []
    assert gate["reason_mismatch_scenarios"] == ["D6"]


def test_genuine_verdict_regression_is_still_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: the head prompt changes the behavior D6 tests."""
    _patch_judge(monkeypatch, "DEGRADED_PASS", ["Serena-only."] * 3)
    before = ev.run_scenario_multi("k", "base", D6, "m", 3)
    _patch_judge(monkeypatch, "HALT", ["Cannot continue."] * 3)
    after = ev.run_scenario_multi("k", "head", D6, "m", 3)
    gate = ev.acceptance_gate(_comparison([before], [after]))
    assert gate["verdict"] == "FAIL"
    assert gate["regressions"] == ["D6"]


# ---------------------------------------------------------------------------
# Defect 2: base-side noise does not gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("passes", "expected"),
    [(0, False), (1, False), (2, True), (3, False)],
)
def test_is_base_unstable_truth_table(passes: int, expected: bool) -> None:
    assert ev.is_base_unstable(_result("S", passes)) is expected


def test_base_two_of_three_and_after_zero_is_not_a_regression() -> None:
    """The D12 shape from PR #5600: base 2/3, after 0/3."""
    stable = [_result(f"X{i}", 3) for i in range(6)]
    gate = ev.acceptance_gate(
        _comparison([_result("D12", 2), *stable], [_result("D12", 0), *stable])
    )
    assert gate["regressions"] == []
    assert gate["base_unstable_scenarios"] == ["D12"]
    assert gate["verdict"] == "PASS"


def test_base_stable_and_after_zero_is_a_regression() -> None:
    """Negative control: a stable base that the head breaks still blocks."""
    stable = [_result(f"X{i}", 3) for i in range(6)]
    gate = ev.acceptance_gate(
        _comparison([_result("D12", 3), *stable], [_result("D12", 0), *stable])
    )
    assert gate["regressions"] == ["D12"]
    assert gate["base_unstable_scenarios"] == []
    assert gate["verdict"] == "FAIL"


def test_base_stable_and_after_one_of_three_is_a_regression() -> None:
    gate = ev.acceptance_gate(_comparison([_result("D12", 3)], [_result("D12", 1)]))
    assert gate["regressions"] == ["D12"]
    assert gate["verdict"] == "FAIL"


def test_base_failing_and_after_passing_is_an_improvement() -> None:
    gate = ev.acceptance_gate(_comparison([_result("D12", 0)], [_result("D12", 3)]))
    assert gate["improvements"] == ["D12"]
    assert gate["base_unstable_scenarios"] == []


def _fake_multi(base: dict[str, int], head: dict[str, int]) -> Any:
    def fake(_key: str, prompt: str, scenario: dict[str, Any], _model: str, runs: int) -> Any:
        table = base if prompt == "base" else head
        return _result(scenario["id"], table[scenario["id"]], runs)

    return fake


def test_run_comparison_scores_only_stable_base_scenarios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenarios = [D12, D6]
    monkeypatch.setattr(
        ev, "run_scenario_multi", _fake_multi({"D12": 2, "D6": 3}, {"D12": 0, "D6": 3})
    )
    out = ev.run_comparison("k", "base", "head", scenarios, "m", 3)
    assert out["before_score"] == 1.0
    assert out["after_score"] == 1.0
    assert out["scenario_count"] == 2
    assert out["scored_scenario_count"] == 1
    assert ev.acceptance_gate(out)["verdict"] == "PASS"


def test_run_comparison_with_genuine_regression_fails_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ev, "run_scenario_multi", _fake_multi({"D12": 3, "D6": 3}, {"D12": 0, "D6": 3})
    )
    out = ev.run_comparison("k", "base", "head", [D12, D6], "m", 3)
    gate = ev.acceptance_gate(out)
    assert out["after_score"] < out["before_score"]
    assert gate["verdict"] == "FAIL"
    assert gate["regressions"] == ["D12"]


def test_run_comparison_with_every_base_unstable_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ev, "run_scenario_multi", _fake_multi({"D12": 2, "D6": 2}, {"D12": 0, "D6": 0})
    )
    out = ev.run_comparison("k", "base", "head", [D12, D6], "m", 3)
    assert out["scored_scenario_count"] == 0
    assert out["before_score"] == 0.0
    assert out["after_score"] == 0.0
    gate = ev.acceptance_gate(out)
    assert gate["criteria"]["has_stable_baseline"] is False
    assert gate["verdict"] == "FAIL"


def test_gate_without_scored_count_assumes_a_baseline() -> None:
    gate = ev.acceptance_gate(_comparison([_result("D12", 3)], [_result("D12", 3)]))
    assert gate["criteria"]["has_stable_baseline"] is True


def test_gate_summary_names_unstable_and_wording_signals(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gate = ev.acceptance_gate(_comparison([_result("D12", 2)], [_result("D12", 0)]))
    gate["reason_mismatch_scenarios"] = ["D6"]
    ev._print_gate_summary(gate)
    err = capsys.readouterr().err
    assert "Base unstable" in err and "['D12']" in err
    assert "Reason wording differs" in err and "['D6']" in err


# ---------------------------------------------------------------------------
# Stable-fraction floor and base minimum scored runs
# ---------------------------------------------------------------------------


def _floor_comparison(stable: int, total: int, runs: int = 3) -> dict[str, Any]:
    """`stable` scenarios with a 3/3 base, the rest 2/3 (base unstable); after is 3/3."""
    before = [_result(f"S{i}", 3 if i < stable else 2, runs) for i in range(total)]
    after = [_result(f"S{i}", runs, runs) for i in range(total)]
    return _comparison(before, after)


@pytest.mark.parametrize(
    ("stable", "total", "expected"),
    [
        (0, 4, "FAIL"),
        (1, 4, "FAIL"),
        (2, 4, "PASS"),
        (3, 5, "PASS"),
        (2, 5, "FAIL"),
        (1, 1, "PASS"),
    ],
)
def test_stable_fraction_floor(stable: int, total: int, expected: str) -> None:
    gate = ev.acceptance_gate(_floor_comparison(stable, total))
    assert gate["verdict"] == expected
    assert gate["criteria"]["has_stable_baseline"] is (expected == "PASS")


def test_below_floor_names_the_inconclusive_reason_and_excluded_count() -> None:
    gate = ev.acceptance_gate(_floor_comparison(1, 4))
    assert "inconclusive" in gate["inconclusive_reason"]
    assert "1 of 4" in gate["inconclusive_reason"]
    assert gate["excluded_count"] == 3
    assert gate["base_unstable_scenarios"] == ["S1", "S2", "S3"]


def test_floor_cleared_has_no_inconclusive_reason() -> None:
    gate = ev.acceptance_gate(_floor_comparison(2, 4))
    assert gate["inconclusive_reason"] is None


def test_base_with_one_scored_run_is_unstable() -> None:
    assert ev.is_base_unstable(_result("S", 1, 1), required_runs=3) is True
    assert ev.is_base_unstable(_result("S", 3, 3), required_runs=3) is False


def test_gate_excludes_a_base_scored_below_the_required_minimum() -> None:
    before = [_result("A", 3, 3), _result("B", 1, 1), _result("C", 3, 3)]
    after = [_result("A", 3, 3), _result("B", 0, 3), _result("C", 3, 3)]
    comparison = _comparison(before, after)
    gate = ev.acceptance_gate(comparison)
    assert "B" in gate["base_unstable_scenarios"]
    assert gate["regressions"] == []


def test_security_tier_requires_five_scored_base_runs_and_lists_separately() -> None:
    before = [_result("A", 5, 5), _result("B", 3, 3)]
    after = [_result("A", 5, 5), _result("B", 5, 5)]
    comparison = _comparison(before, after)
    gate = ev.acceptance_gate(comparison, security_critical=True)
    assert gate["base_unstable_scenarios"] == []
    assert gate["base_unstable_security_scenarios"] == ["B"]
    assert gate["excluded_count"] == 1


def test_run_comparison_excludes_a_base_scored_once(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_k: str, prompt: str, scenario: dict[str, Any], _m: str, runs: int) -> dict[str, Any]:
        if prompt == "base" and scenario["id"] == "D6":
            return _result("D6", 1, 1)
        return _result(scenario["id"], runs, runs)

    monkeypatch.setattr(ev, "run_scenario_multi", fake)
    out = ev.run_comparison("k", "base", "head", [D12, D6], "m", 3)
    assert out["scored_scenario_count"] == 1


def _without_counts(comparison: dict[str, Any]) -> dict[str, Any]:
    """A hand-built comparison that omits the counts run_comparison supplies."""
    return {
        k: v for k, v in comparison.items() if k not in ("scenario_count", "scored_scenario_count")
    }


def test_floor_derives_from_the_gate_exclusion_set_when_counts_are_omitted() -> None:
    gate = ev.acceptance_gate(_without_counts(_floor_comparison(1, 4)))
    assert gate["verdict"] == "FAIL"
    assert "1 of 4" in gate["inconclusive_reason"]


def test_hand_built_comparison_with_all_stable_and_no_counts_passes() -> None:
    gate = ev.acceptance_gate(_without_counts(_floor_comparison(4, 4)))
    assert gate["verdict"] == "PASS"


def test_a_larger_supplied_count_cannot_raise_the_stable_count() -> None:
    comparison = _floor_comparison(1, 4)
    comparison["scored_scenario_count"] = 4
    gate = ev.acceptance_gate(comparison)
    assert gate["verdict"] == "FAIL"


def test_a_smaller_supplied_count_lowers_the_stable_count() -> None:
    comparison = _floor_comparison(4, 4)
    comparison["scored_scenario_count"] = 1
    gate = ev.acceptance_gate(comparison)
    assert gate["verdict"] == "FAIL"


def test_security_tier_one_of_four_stable_is_inconclusive() -> None:
    before = [_result("S0", 5, 5)] + [_result(f"S{i}", 3, 3) for i in range(1, 4)]
    after = [_result(f"S{i}", 5, 5) for i in range(4)]
    gate = ev.acceptance_gate(_comparison(before, after, security_critical=True), True)
    assert gate["verdict"] == "FAIL"
    assert "1 of 4" in gate["inconclusive_reason"]
    assert gate["base_unstable_security_scenarios"] == ["S1", "S2", "S3"]
    assert gate["excluded_count"] == 3


def test_failing_base_scored_below_the_minimum_is_excluded() -> None:
    before = [_result("A", 3, 3), _result("B", 0, 1), _result("C", 3, 3)]
    after = [_result("A", 3, 3), _result("B", 3, 3), _result("C", 3, 3)]
    gate = ev.acceptance_gate(_comparison(before, after))
    assert gate["base_unstable_scenarios"] == ["B"]
    assert gate["improvements"] == []


def test_run_comparison_security_floor_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    scenarios = [{**D12, "id": f"S{i}"} for i in range(4)]

    def fake(_k: str, prompt: str, scenario: dict[str, Any], _m: str, runs: int) -> dict[str, Any]:
        if prompt == "base" and scenario["id"] != "S0":
            return _result(scenario["id"], 3, 3)
        return _result(scenario["id"], 5, 5)

    monkeypatch.setattr(ev, "run_scenario_multi", fake)
    out = ev.run_comparison("k", "base", "head", scenarios, "m", 5, security_critical=True)
    assert out["scored_scenario_count"] == 1
    assert ev.acceptance_gate(out, security_critical=True)["verdict"] == "FAIL"


def test_inconclusive_fail_exits_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ev, "run_scenario_multi", _fake_multi({"D12": 2, "D6": 2}, {"D12": 3, "D6": 3})
    )
    out_file = tmp_path / "report.json"
    args = argparse.Namespace(model="m", runs=3, security_critical=False, output=str(out_file))
    with pytest.raises(SystemExit) as exc:
        ev._run_and_report("k", "base", "head", [D12, D6], args, "test")
    assert exc.value.code == 1
    gate = json.loads(out_file.read_text(encoding="utf-8"))["gate"]
    assert gate["verdict"] == "FAIL"
    assert "inconclusive" in gate["inconclusive_reason"]
