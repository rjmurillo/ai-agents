"""Base resample on a suspected regression for eval-prompt-change.py (issue #5601).

A base that drew 3/3 on its single sample can still be a noisy base. These tests
cover the resample that runs only when base passed and after failed, with a
negative control that keeps a genuine regression.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import pytest

from tests.eval.test_eval_prompt_change_stability import D6, D12, _result, ev


def _resampling_multi(
    first_base: int, resample_base: int, head: int, calls: list[tuple[str, int]]
) -> Any:
    """Fake judge: the first base sample draws `first_base`, later base calls `resample_base`.

    `calls` records (prompt, runs) so a test can assert when no resample happens.
    """

    def fake(_k: str, prompt: str, scenario: dict[str, Any], _m: str, runs: int) -> Any:
        calls.append((prompt, runs))
        if prompt != "base":
            return _result(scenario["id"], head, runs)
        base_calls = sum(1 for p, _r in calls if p == "base")
        return _result(scenario["id"], first_base if base_calls == 1 else resample_base, runs)

    return fake


def test_base_three_of_three_then_one_of_three_on_resample_is_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(ev, "run_scenario_multi", _resampling_multi(3, 1, 0, calls))
    out = ev.run_comparison("k", "base", "head", [D12], "m", 3, base_resamples=3)
    gate = ev.acceptance_gate(out)
    assert gate["regressions"] == []
    assert gate["verdict"] == "FAIL"
    assert gate["criteria"]["has_stable_baseline"] is False
    assert gate["base_unstable_scenarios"] == ["D12"]
    assert out["before_results"][0]["resample_contradicted"] is True
    assert out["scored_scenario_count"] == 0
    assert out["api_calls"] == 3 + 3 + 3


def test_base_three_of_three_staying_stable_is_still_a_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(ev, "run_scenario_multi", _resampling_multi(3, 3, 0, calls))
    out = ev.run_comparison("k", "base", "head", [D12, D6], "m", 3, base_resamples=3)
    gate = ev.acceptance_gate(out)
    assert gate["regressions"] == ["D12", "D6"]
    assert gate["base_unstable_scenarios"] == []
    assert gate["verdict"] == "FAIL"
    assert out["before_results"][0]["runs"] == 6
    assert out["before_results"][0]["resampled_runs"] == 3


def test_no_resample_without_a_suspected_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(ev, "run_scenario_multi", _resampling_multi(3, 0, 3, calls))
    out = ev.run_comparison("k", "base", "head", [D12], "m", 3, base_resamples=3)
    assert calls == [("base", 3), ("head", 3)]
    assert out["api_calls"] == 6
    assert "resampled_runs" not in out["before_results"][0]


def test_no_resample_when_the_base_already_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(ev, "run_scenario_multi", _resampling_multi(0, 3, 0, calls))
    ev.run_comparison("k", "base", "head", [D12], "m", 3, base_resamples=3)
    assert calls == [("base", 3), ("head", 3)]


def test_zero_resamples_disables_the_resample(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(ev, "run_scenario_multi", _resampling_multi(3, 0, 0, calls))
    out = ev.run_comparison("k", "base", "head", [D12], "m", 3, base_resamples=0)
    assert len(calls) == 2
    assert ev.acceptance_gate(out)["regressions"] == ["D12"]


def test_resample_contradiction_marks_the_base_tag() -> None:
    before = _result("D12", 4, 6)
    before["resample_contradicted"] = True
    assert "resample contradicted" in ev._base_tag(before, 3)
    assert ev.is_base_unstable(before, 3) is True


def test_base_resamples_flag_rejects_a_negative_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = ["x", "--prompt", "p", "--scenarios", "s", "--base-resamples", "-1"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        ev._parse_args()
    assert exc.value.code == 2


def test_base_resamples_flag_defaults_to_three(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["x", "--prompt", "p", "--scenarios", "s"])
    assert ev._parse_args().base_resamples == ev.DEFAULT_BASE_RESAMPLES == 3


def test_all_unscored_resample_marks_the_base_unstable(monkeypatch: pytest.MonkeyPatch) -> None:
    unscored = {"passes": 0, "runs": 0, "not_scored_runs": 3, "per_run": []}
    monkeypatch.setattr(ev, "run_scenario_multi", lambda *_a, **_k: unscored)
    pooled = ev._resample_base("k", "base", D12, "m", _result("D12", 3, 3), 3)
    assert pooled["resample_contradicted"] is True
    assert ev.is_base_unstable(pooled, 3) is True


def test_security_tier_pools_five_plus_resample_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(ev, "run_scenario_multi", _resampling_multi(5, 5, 0, calls))
    out = ev.run_comparison("k", "base", "head", [D12], "m", 5, True, base_resamples=3)
    assert out["before_results"][0]["runs"] == 8
    assert ev.acceptance_gate(out, security_critical=True)["regressions"] == ["D12"]


def test_run_and_report_forwards_base_resamples(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    seen: dict[str, Any] = {}

    def fake(*_a: Any, **kw: Any) -> Any:
        seen.update(kw)
        raise SystemExit(0)

    monkeypatch.setattr(ev, "run_comparison", fake)
    args = argparse.Namespace(
        model="m", runs=3, security_critical=False, base_resamples=7, output=None
    )
    with pytest.raises(SystemExit):
        ev._run_and_report("k", "b", "h", [D12], args, "t")
    assert seen["base_resamples"] == 7
