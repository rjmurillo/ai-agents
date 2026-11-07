"""skillopt report: evidence, benchmark spread, signals, and its CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _skillopt_report as report_mod
import pytest
import skillopt
from skillopt import SkillOptError
from skillopt_helpers import write_json

EVAL = {"splits": {"sel": ["a", "b", "c", "d"], "train": ["e"]}}


def _report(inc: dict, cand: dict, **kw: Any) -> dict[str, Any]:
    return report_mod.run_report(EVAL, inc, cand, **kw)


def _task(report: dict, tid: str) -> dict[str, Any]:
    return next(t for t in report["tasks"] if t["id"] == tid)


def test_change_and_signals_per_task():
    inc = {"a": True, "b": False, "c": True, "d": False}
    cand = {"a": True, "b": True, "c": False, "d": False}

    report = _report(inc, cand)

    assert [_task(report, t)["change"] for t in "abcd"] == ["same", "gain", "regression", "same"]
    assert "always_passes" in _task(report, "a")["signals"]
    assert "never_passes" in _task(report, "d")["signals"]
    assert _task(report, "b")["signals"] == ["pass_without_evidence_candidate"]


def test_pass_rate_benchmark_matches_counts_and_delta():
    inc = {"a": True, "b": False, "c": True, "d": False}
    cand = {"a": True, "b": True, "c": True, "d": False}

    bench = _report(inc, cand)["benchmark"]

    assert bench["incumbent"]["pass_rate"] == {"n": 4, "mean": 0.5, "stdev": 0.5774}
    assert bench["candidate"]["pass_rate"]["mean"] == 0.75
    assert bench["delta"]["pass_rate"] == 0.25


def test_unverified_tasks_leave_pass_rate_and_get_a_signal():
    inc = {"a": True, "b": "UNVERIFIED", "c": True}
    cand = {"a": True, "b": True, "c": True, "d": False}

    report = _report(inc, cand)

    assert _task(report, "b")["signals"] == ["unverified"]
    assert _task(report, "b")["change"] == "unverified"
    assert _task(report, "d")["signals"] == ["unverified"]
    assert report["benchmark"]["incumbent"]["pass_rate"]["n"] == 2


def test_evidence_is_echoed_and_a_pass_without_it_is_flagged():
    inc = {"a": True, "b": False, "c": False, "d": False}
    cand = {"a": True, "b": False, "c": False, "d": False}
    evidence = {"incumbent": {"a": "exit 0, one finding"}, "candidate": {}}

    report = _report(inc, cand, evidence=evidence)

    task = _task(report, "a")
    assert task["evidence"]["incumbent"] == "exit 0, one finding"
    assert task["signals"] == ["always_passes", "pass_without_evidence_candidate"]
    assert "pass_without_evidence_incumbent" not in task["signals"]


@pytest.mark.parametrize("bad", ["", "  ", 3, ["x"]])
def test_bad_evidence_is_refused(bad):
    with pytest.raises(SkillOptError, match="evidence.incumbent.a"):
        _report({}, {}, evidence={"incumbent": {"a": bad}})


def test_measurements_pool_repeats_and_report_the_delta_with_the_declared_metric():
    inc = {t: True for t in "abcd"}
    eval_set = {**EVAL, "efficiency": {"metric": "total_tokens"}}
    measurements = {
        "incumbent": {"a": [100, 300], "b": [200]},
        "candidate": {"a": [50, 150], "b": [100]},
        "null": {"a": [999]},
    }

    bench = report_mod.run_report(eval_set, inc, inc, measurements=measurements)["benchmark"]

    measured = bench["measurements"]
    assert measured["metric"] == "total_tokens"
    assert measured["incumbent"] == {"n": 3, "mean": 200.0, "stdev": 100.0}
    assert measured["delta"] == -100.0


def test_measurements_without_a_declared_metric_have_a_null_name():
    measured = _report({}, {}, measurements={"incumbent": {"a": [1]}})["benchmark"]["measurements"]

    assert measured["metric"] is None
    assert measured["candidate"] == {"n": 0, "mean": None, "stdev": None}
    assert measured["delta"] is None


def test_no_measurements_file_means_no_measurements_block():
    assert "measurements" not in _report({"a": True}, {"a": True})["benchmark"]


@pytest.mark.parametrize("values", [[-1], [True], ["9"], [None], [float("nan")], 5, "x"])
def test_bad_measurements_are_refused(values):
    with pytest.raises(SkillOptError, match="must be a list of numbers"):
        _report({}, {}, measurements={"incumbent": {"a": values}})


def test_measurements_outside_the_split_are_ignored():
    bad = {"incumbent": {"zzz": ["junk"]}}

    assert _report({}, {}, measurements=bad)["benchmark"]["measurements"]["incumbent"]["n"] == 0


def test_a_flip_in_the_null_control_marks_the_task_unstable():
    inc = {"a": True, "b": True, "c": False, "d": False}
    null = {"a": True, "b": False, "c": False, "d": False}

    report = _report(inc, inc, null_results=null)

    assert "unstable" in _task(report, "b")["signals"]
    assert "unstable" not in _task(report, "a")["signals"]


def test_report_checks_the_same_preconditions_as_the_gate():
    exposed = {**EVAL, "exposed": ["a"]}
    with pytest.raises(SkillOptError, match="exposed or invalid"):
        report_mod.run_report(exposed, {}, {})
    assert report_mod.run_report(exposed, {}, {}, split="train")["split"] == "train"
    with pytest.raises(SkillOptError, match="no 'nope' split"):
        _report({}, {}, split="nope")


@pytest.mark.parametrize("field", ["evidence", "measurements"])
def test_non_object_inputs_are_refused(field):
    with pytest.raises(SkillOptError, match="must be an object"):
        _report({}, {}, **{field: []})


def test_cli_prints_the_report_and_never_gates(tmp_path: Path, capsys):
    eval_path = write_json(tmp_path / "e.json", EVAL)
    inc = write_json(tmp_path / "i.json", {"a": True, "b": False, "c": False, "d": False})
    cand = write_json(tmp_path / "c.json", {"a": False, "b": False, "c": False, "d": False})
    ev = write_json(tmp_path / "ev.json", {"incumbent": {"a": "ok"}})
    argv = ["report", "--eval", str(eval_path), "--incumbent-results", str(inc)]
    argv += ["--candidate-results", str(cand), "--evidence", str(ev)]

    code = skillopt.main(argv)

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert _task(out, "a")["change"] == "regression"


def test_cli_exits_2_on_a_bad_input(tmp_path: Path, capsys):
    eval_path = write_json(tmp_path / "e.json", EVAL)
    inc = write_json(tmp_path / "i.json", {})
    argv = ["report", "--eval", str(eval_path), "--incumbent-results", str(inc)]
    argv += ["--candidate-results", str(tmp_path / "missing.json")]

    assert skillopt.main(argv) == 2
    assert "skillopt:" in capsys.readouterr().err
