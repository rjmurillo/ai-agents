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
        "passed": passes >= max(1, (runs * 2) // 3),
        "flaky": 0 < passes < runs,
        "reason_mismatch_runs": 0,
        "per_run": [],
    }


def _comparison(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a comparison the way run_comparison does: scores cover stable base scenarios."""
    pairs = [(b, a) for b, a in zip(before, after, strict=True) if not ev.is_base_unstable(b)]
    n = max(1, len(pairs))
    bs = sum(b["passed"] for b, _a in pairs) / n
    as_ = sum(a["passed"] for _b, a in pairs) / n
    return {
        "before_results": before,
        "after_results": after,
        "before_score": bs,
        "after_score": as_,
        "delta": as_ - bs,
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
