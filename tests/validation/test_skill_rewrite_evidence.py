"""Tests for the ADR-127 results recompute in ``skill_rewrite_evidence``.

The module is pure, so these tests build results dicts in memory. The git side
is tested in ``test_check_skill_rewrite_evidence.py``.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import skill_rewrite_evidence as sre

RUNNER = sre.load_runner()
SURFACE = "a" * 64
SCEN_SHA = "b" * 64
BASE = "c" * 40
MODEL = "m-1"


def scenarios(n: int = 8) -> tuple[dict[str, Any], ...]:
    return tuple(
        {"id": f"S{i}", "desc": "d", "input": "i", "expected_verdict": "GO"}
        for i in range(1, n + 1)
    )


def expected(n: int = 8) -> sre.Expected:
    return sre.Expected(
        prompt_path="src/claude/skills/demo/SKILL.md",
        prompt_surface_sha256=SURFACE,
        scenarios_path="tests/evals/demo-scenarios.json",
        scenarios_sha256=SCEN_SHA,
        scenarios=scenarios(n),
    )


def runs(pattern: str) -> list[dict[str, Any]]:
    """`P` pass, `F` fail, `N` not scored."""
    out = []
    for ch in pattern:
        if ch == "N":
            out.append({"verdict": "NOT_SCORED", "not_scored": True, "model_used": MODEL})
        else:
            out.append({"verdict": "GO" if ch == "P" else "STOP", "model_used": MODEL})
    return out


def results(
    table: dict[str, tuple[str, str]] | None = None,
    n: int = 8,
    verdict: str = "PASS",
    runs_per: int = 3,
    security: bool = False,
) -> dict[str, Any]:
    table = table or {}
    ids = [f"S{i}" for i in range(1, n + 1)]
    pat = "P" * runs_per
    before = [{"scenario_id": i, "per_run": runs(table.get(i, (pat, pat))[0])} for i in ids]
    after = [{"scenario_id": i, "per_run": runs(table.get(i, (pat, pat))[1])} for i in ids]
    return {
        "model": MODEL,
        "identity": {
            "prompt_path": "src/claude/skills/demo/SKILL.md",
            "prompt_surface_sha256": SURFACE,
            "scenarios_path": "tests/evals/demo-scenarios.json",
            "scenarios_sha256": SCEN_SHA,
            "base_ref": "origin/main",
            "base_commit": BASE,
            "model": MODEL,
        },
        "runs_per_scenario": runs_per,
        "security_critical": security,
        "gate": {"verdict": verdict},
        "detail": {"before": before, "after": after},
    }


def verify(res: Any, n: int = 8) -> list[str]:
    return sre.verify_results(RUNNER, res, expected(n))


def test_load_runner_keeps_an_existing_path_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    rest = [p for p in sys.path if p != str(sre._EVAL_DIR)]
    monkeypatch.setattr(sys, "path", [str(sre._EVAL_DIR), *rest])
    assert sre.load_runner().DEFAULT_RUNS == 3
    assert sys.path.count(str(sre._EVAL_DIR)) == 1


class TestPositive:
    def test_clean_pass_has_no_findings(self) -> None:
        assert verify(results()) == []

    def test_improvement_on_a_base_failure_passes(self) -> None:
        assert verify(results({"S1": ("FFF", "PPP")})) == []

    def test_unscored_base_run_is_unstable_and_after_must_pass_all(self) -> None:
        # Base scored twice: unstable. After passes all three: allowed.
        assert verify(results({"S1": ("PPN", "PPP")})) == []

    def test_security_tier_uses_five_runs(self) -> None:
        assert verify(results(runs_per=5, security=True)) == []

    def test_resample_on_suspected_regression_that_holds_is_a_regression(self) -> None:
        res = results({"S1": ("PPPPPP", "PFF")}, verdict="FAIL")
        found = verify(res)
        assert any("recomputed gate is FAIL" in f for f in found)


class TestNegativeControl:
    def test_hand_edited_pass_verdict_fails(self) -> None:
        """gate.verdict says PASS, the runs say a carried scenario regressed."""
        res = results({"S1": ("PPP", "FFF")}, verdict="PASS")
        found = verify(res)
        assert any("gate.verdict says 'PASS'" in f and "'FAIL'" in f for f in found)
        assert any("recomputed gate is FAIL" in f for f in found)

    def test_recorded_fail_still_blocks(self) -> None:
        res = results({"S1": ("PPP", "FFF")}, verdict="FAIL")
        found = verify(res)
        assert not any("gate.verdict says" in f for f in found)
        assert any("recomputed gate is FAIL" in f for f in found)

    def test_recorded_pass_on_relabelled_runs_is_ignored(self) -> None:
        """A per-run `passed` flag is not read; only the verdict label is."""
        res = results({"S1": ("PPP", "FFF")})
        for run in res["detail"]["after"][0]["per_run"]:
            run["passed"] = True
        assert any("recompute to 'FAIL'" in f for f in verify(res))

    def test_missing_gate_block_disagrees(self) -> None:
        res = results()
        del res["gate"]
        assert any("gate.verdict says None" in f for f in verify(res))


class TestMissingSignal:
    def test_not_a_dict(self) -> None:
        assert verify([]) == ["results file is not a JSON object"]

    def test_no_identity_block(self) -> None:
        res = results()
        del res["identity"]
        assert "identity block is missing" in verify(res)[0]

    @pytest.mark.parametrize("key", sre.IDENTITY_KEYS)
    def test_each_identity_key_is_required(self, key: str) -> None:
        res = results()
        res["identity"][key] = None
        assert any(f"identity.{key} is missing" in f for f in verify(res))

    def test_blank_identity_value(self) -> None:
        res = results()
        res["identity"]["model"] = "  "
        assert any("identity.model is missing" in f for f in verify(res))

    def test_bad_sha256(self) -> None:
        res = results()
        res["identity"]["scenarios_sha256"] = "xyz"
        assert any("not a 64-hex sha256" in f for f in verify(res))

    def test_bad_base_commit(self) -> None:
        res = results()
        res["identity"]["base_commit"] = "origin/main"
        assert any("not a 40-hex commit" in f for f in verify(res))

    def test_model_mismatch(self) -> None:
        res = results()
        res["model"] = "other"
        assert any("differs from the top-level model" in f for f in verify(res))


class TestIdentityMatch:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("prompt_surface_sha256", "d" * 64),
            ("scenarios_sha256", "e" * 64),
            ("prompt_path", "other/SKILL.md"),
            ("scenarios_path", "tests/evals/x.json"),
        ],
    )
    def test_identity_must_match_repository(self, key: str, value: str) -> None:
        res = results()
        res["identity"][key] = value
        assert any(f"identity.{key} is {value!r}" in f for f in verify(res))

    def test_run_model_must_match(self) -> None:
        res = results()
        res["detail"]["after"][0]["per_run"][0]["model_used"] = "other"
        assert any("names a model other" in f for f in verify(res))


class TestShape:
    def test_runs_below_floor(self) -> None:
        res = results(runs_per=2)
        assert any("below the required 3" in f for f in verify(res))

    def test_security_needs_five(self) -> None:
        res = results(security=True)
        assert any("below the required 5" in f for f in verify(res))

    def test_security_flag_not_bool(self) -> None:
        res = results()
        res["security_critical"] = "no"
        assert any("security_critical is 'no'; it must be true or false" in f for f in verify(res))

    def test_integer_scenario_ids_are_read(self) -> None:
        res = results()
        for side in ("before", "after"):
            for row in res["detail"][side]:
                row["scenario_id"] = int(row["scenario_id"][1:])
        exp = sre.Expected(
            prompt_path=expected().prompt_path,
            prompt_surface_sha256=SURFACE,
            scenarios_path=expected().scenarios_path,
            scenarios_sha256=SCEN_SHA,
            scenarios=tuple({**s, "id": int(s["id"][1:])} for s in scenarios()),
        )
        assert sre.verify_results(RUNNER, res, exp) == []

    def test_resampled_base_run_model_is_checked(self) -> None:
        res = results({"S1": ("PPPPPP", "FFF")}, verdict="FAIL")
        res["detail"]["before"][0]["per_run"][4]["model_used"] = "other"
        assert any("names a model other" in f for f in verify(res))

    def test_detail_missing(self) -> None:
        res = results()
        del res["detail"]
        assert any("detail.before or detail.after" in f for f in verify(res))

    def test_detail_not_dict(self) -> None:
        res = results()
        res["detail"] = []
        assert any("detail.before or detail.after" in f for f in verify(res))

    def test_row_without_per_run(self) -> None:
        res = results()
        res["detail"]["after"][0]["per_run"] = "x"
        assert any("detail.before or detail.after" in f for f in verify(res))

    def test_duplicate_scenario_row(self) -> None:
        res = results()
        res["detail"]["before"].append(copy.deepcopy(res["detail"]["before"][0]))
        assert any("detail.before or detail.after" in f for f in verify(res))

    def test_dropped_scenario(self) -> None:
        res = results()
        res["detail"]["after"].pop()
        assert any("detail.after drops scenarios ['S8']" in f for f in verify(res))

    def test_unknown_scenario(self) -> None:
        res = results(n=9)
        assert any("not in the file ['S9']" in f for f in verify(res, n=8))

    def test_run_without_verdict(self) -> None:
        res = results()
        res["detail"]["before"][0]["per_run"][0] = {"reason": "x"}
        assert any("S1: a run has no string verdict" in f for f in verify(res))

    def test_wrong_after_run_count(self) -> None:
        res = results({"S1": ("PPP", "PP")})
        assert any("S1: 3 base and 2 after runs" in f for f in verify(res))

    def test_extra_base_runs_without_suspected_regression(self) -> None:
        res = results({"S1": ("PPPPPP", "PPP")})
        assert any("extra base runs without a suspected regression" in f for f in verify(res))


class TestFloors:
    def test_scenario_floor(self) -> None:
        found = verify(results(n=7), n=7)
        assert any("scenario floor: 7 scenarios" in f for f in found)

    def test_carried_floor(self) -> None:
        table = {f"S{i}": ("FFF", "PPP") for i in (1, 2, 3)}
        found = verify(results(table))
        assert any("carried floor: 5 scenarios" in f for f in found)

    def test_base_failure_must_pass_every_after_run(self) -> None:
        found = verify(results({"S1": ("FFF", "PPF")}))
        assert any("S1: fails or is unstable on base" in f for f in found)

    def test_unstable_base_must_pass_every_after_run(self) -> None:
        found = verify(results({"S1": ("PPF", "PPF")}))
        assert any("S1: fails or is unstable on base" in f and "2 of 3" in f for f in found)

    def test_contradicted_resample_is_unstable(self) -> None:
        found = verify(results({"S1": ("PPPPPF", "PFF")}))
        assert any("S1: fails or is unstable on base" in f for f in found)


class TestRunnerConformance:
    """The rebuilt aggregate and pooling equal the runner's own."""

    KEYS = ("passes", "runs", "not_scored_runs", "pass_rate", "passed", "flaky")

    @staticmethod
    def _feed(monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]) -> None:
        queue = list(recorded)

        def judge(*_a: Any, **_k: Any) -> dict[str, Any]:
            return dict(queue.pop(0))

        monkeypatch.setattr(RUNNER, "judge_scenario", judge)
        monkeypatch.setattr(RUNNER.time, "sleep", lambda _s: None)

    @pytest.mark.parametrize("pattern", ["PPP", "PPF", "FFF", "PNN", "NNN", "PFN"])
    def test_aggregate_matches_run_scenario_multi(
        self, monkeypatch: pytest.MonkeyPatch, pattern: str
    ) -> None:
        recorded = runs(pattern)
        self._feed(monkeypatch, recorded)
        scenario = scenarios(1)[0]
        theirs = RUNNER.run_scenario_multi("k", "p", scenario, MODEL, len(pattern))
        ours = sre._aggregate(RUNNER, "S1", theirs["per_run"], "GO")
        assert {k: ours[k] for k in self.KEYS} == {k: theirs[k] for k in self.KEYS}

    @pytest.mark.parametrize("extra", ["PPP", "PPF", "PPN"])
    def test_pool_matches_resample_base(self, monkeypatch: pytest.MonkeyPatch, extra: str) -> None:
        scenario = scenarios(1)[0]
        self._feed(monkeypatch, runs("PPP"))
        first = RUNNER.run_scenario_multi("k", "p", scenario, MODEL, 3)
        self._feed(monkeypatch, runs(extra))
        theirs = RUNNER._resample_base("k", "p", scenario, MODEL, first, 3)
        mine_first = sre._aggregate(RUNNER, "S1", first["per_run"], "GO")
        mine_extra = sre._aggregate(RUNNER, "S1", runs(extra), "GO")
        ours = sre._pool(RUNNER, mine_first, mine_extra)
        keys = (*self.KEYS, "resample_contradicted")
        assert {k: ours[k] for k in keys} == {k: theirs[k] for k in keys}


class TestEndToEndConformance:
    """The runner's own comparison and gate, then the recompute, on one file."""

    @staticmethod
    def _runner_results(
        monkeypatch: pytest.MonkeyPatch, table: dict[str, tuple[str, str]]
    ) -> dict[str, Any]:
        queues = {
            (side, sid): list(runs(pattern))
            for sid, pair in table.items()
            for side, pattern in zip(("base", "head"), pair, strict=True)
        }

        def judge(_key: str, prompt: str, scenario: Any, *_a: Any, **_k: Any) -> dict[str, Any]:
            return dict(queues[(prompt, scenario["id"])].pop(0))

        monkeypatch.setattr(RUNNER, "judge_scenario", judge)
        monkeypatch.setattr(RUNNER.time, "sleep", lambda _s: None)
        comparison = RUNNER.run_comparison("k", "base", "head", list(scenarios()), MODEL, 3)
        gate = RUNNER.acceptance_gate(comparison)
        res = results()
        res["gate"] = gate
        res["detail"] = {
            "before": comparison["before_results"],
            "after": comparison["after_results"],
        }
        return res

    @pytest.mark.parametrize(
        ("overrides", "verdict"),
        [
            ({}, "PASS"),
            ({"S1": ("PPPPPP", "FFF")}, "FAIL"),
            ({"S1": ("PPF", "PPP"), "S2": ("FFF", "PPP")}, "PASS"),
            ({"S1": ("PPPPPP", "PFF")}, "FAIL"),
            ({"S1": ("PPPPPF", "PFF")}, "FAIL"),
            ({"S1": ("PPPPPF", "PPF")}, "PASS"),
            ({f"S{i}": ("PPF", "PPP") for i in range(1, 6)}, "FAIL"),
        ],
    )
    def test_recompute_agrees_with_the_runner(
        self, monkeypatch: pytest.MonkeyPatch, overrides: dict[str, tuple[str, str]], verdict: str
    ) -> None:
        table = {f"S{i}": ("PPP", "PPP") for i in range(1, 9)} | overrides
        res = self._runner_results(monkeypatch, table)
        assert res["gate"]["verdict"] == verdict
        found = verify(res)
        assert not any("gate.verdict says" in f for f in found), found
        assert any("recomputed gate is FAIL" in f for f in found) is (verdict == "FAIL")

    def test_base_run_model_must_match(self) -> None:
        res = results()
        res["detail"]["before"][0]["per_run"][0]["model_used"] = "other"
        assert any("names a model other" in f for f in verify(res))
