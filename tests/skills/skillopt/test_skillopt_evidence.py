"""Tests for the skillopt evidence checks: weakness, manifesto, pins, proposer tier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import skillopt
from skillopt_helpers import Capture, write_json

EVAL: dict[str, Any] = {
    "splits": {"train": ["t1", "t2", "t3", "t4"], "sel": ["s1", "s2"]},
    "tasks": {},
}
INCUMBENT = {"t1": False, "t2": False, "t3": False, "t4": True}
CANDIDATE = {"t1": True, "t2": True, "t3": False, "t4": True}
PATCHES = [{"op": "append", "text": "rule"}]


def weakness(**over: Any) -> dict[str, Any]:
    pattern = {
        "id": "p1",
        "tasks": ["t1", "t2"],
        "verifier_cause": "missing artifact",
        "agent_behavior": "skipped the write step",
        "mechanism": "no rule names the output path",
        "addressable": True,
    }
    pattern.update(over)
    return {"schema": "skillopt-weakness/1", "patterns": [pattern]}


def manifesto(**over: Any) -> dict[str, Any]:
    entry = {
        "patch": 0,
        "pattern": "p1",
        "evidence": ["t1", "t2"],
        "root_cause": "output path unstated",
        "component": "skill",
        "fix": "name the output path",
        "predicted_fixes": ["t1", "t2"],
        "at_risk": ["t4"],
    }
    entry.update(over)
    return {
        "schema": "skillopt-manifesto/1",
        "proposer_model": "claude-opus-5-5",
        "entries": [entry],
    }


def run(tmp_path: Path, argv: list[str], **files: Any) -> int:
    paths = {
        name: str(write_json(tmp_path / f"{name}.json", value)) for name, value in files.items()
    }
    resolved = [paths.get(a[1:], a) if a.startswith("@") else a for a in argv]
    return skillopt.main(resolved)


class TestWeaknessCheck:
    ARGV = ["weakness-check", "--eval", "@eval", "--incumbent-results", "@inc", "--weakness", "@w"]

    def test_valid_reports_recurrent_and_unclustered(self, tmp_path: Path, capsys: Capture) -> None:
        assert run(tmp_path, self.ARGV, eval=EVAL, inc=INCUMBENT, w=weakness()) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["recurrent_addressable"] == ["p1"]
        assert report["unclustered_failures"] == ["t3"]

    @pytest.mark.parametrize(
        ("override", "message"),
        [
            ({"tasks": ["s1"]}, "sel task"),
            ({"tasks": ["t4"]}, "passed at baseline"),
            ({"tasks": ["zz"]}, "non-train"),
            ({"tasks": []}, "at least one"),
            ({"mechanism": ""}, "mechanism"),
            ({"mechanism": "same cause as s2"}, "names sel task"),
            ({"mechanism": "mirror the s1-style output"}, "names sel task"),
            ({"mechanism": "see s1."}, "names sel task"),
            ({"addressable": "yes"}, "addressable"),
        ],
    )
    def test_invalid_exits_2(
        self, tmp_path: Path, capsys: Capture, override: dict[str, Any], message: str
    ) -> None:
        assert run(tmp_path, self.ARGV, eval=EVAL, inc=INCUMBENT, w=weakness(**override)) == 2
        assert message in capsys.readouterr().err

    def test_sel_id_inside_a_longer_token_is_not_a_leak(self, tmp_path: Path) -> None:
        doc = weakness(mechanism="rule s10 and step s1x are unrelated ids")
        assert run(tmp_path, self.ARGV, eval=EVAL, inc=INCUMBENT, w=doc) == 0

    def test_sel_id_that_prefixes_a_train_id_is_not_a_leak(self, tmp_path: Path) -> None:
        eval_set = {"splits": {"train": ["s1-b", "t2"], "sel": ["s1"]}}
        inc = {"s1-b": False, "t2": True}
        doc = weakness(tasks=["s1-b"], mechanism="s1-b and ts1 skip the write step")
        assert run(tmp_path, self.ARGV, eval=eval_set, inc=inc, w=doc) == 0
        leak = weakness(tasks=["s1-b"], mechanism="s1-b fails like s1 does")
        assert run(tmp_path, self.ARGV, eval=eval_set, inc=inc, w=leak) == 2

    def test_unverified_baseline_task_is_not_a_failure(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        inc = {**INCUMBENT, "t2": "UNVERIFIED"}
        assert run(tmp_path, self.ARGV, eval=EVAL, inc=inc, w=weakness()) == 2
        assert "no verified result" in capsys.readouterr().err
        assert run(tmp_path, self.ARGV, eval=EVAL, inc=inc, w=weakness(tasks=["t1"])) == 0
        assert json.loads(capsys.readouterr().out)["unclustered_failures"] == ["t3"]

    def test_task_in_both_splits_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        eval_set = {"splits": {"train": ["x", "t2"], "sel": ["x"]}}
        doc = weakness(tasks=["x"], mechanism="same as x")
        assert run(tmp_path, self.ARGV, eval=eval_set, inc={"x": False, "t2": True}, w=doc) == 2
        assert "both train and sel" in capsys.readouterr().err

    def test_malformed_sel_split_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        bad = {"splits": {"train": ["t1", "t2", "t3", "t4"], "sel": "s1"}}
        assert run(tmp_path, self.ARGV, eval=bad, inc=INCUMBENT, w=weakness()) == 2
        assert "'sel' split" in capsys.readouterr().err

    def test_task_in_two_patterns_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        doc = weakness()
        doc["patterns"].append({**doc["patterns"][0], "id": "p2", "tasks": ["t1"]})
        assert run(tmp_path, self.ARGV, eval=EVAL, inc=INCUMBENT, w=doc) == 2
        assert "is in patterns" in capsys.readouterr().err

    def test_wrong_schema_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        assert run(tmp_path, self.ARGV, eval=EVAL, inc=INCUMBENT, w={"patterns": []}) == 2
        assert "schema" in capsys.readouterr().err


class TestManifestoCheck:
    ARGV = [
        "manifesto-check",
        "--eval",
        "@eval",
        "--incumbent-results",
        "@inc",
        "--weakness",
        "@w",
        "--manifesto",
        "@m",
        "--patches",
        "@p",
    ]

    def call(
        self,
        tmp_path: Path,
        m: dict[str, Any],
        w: dict[str, Any] | None = None,
        patches: list[Any] | None = None,
    ) -> int:
        return run(
            tmp_path,
            self.ARGV,
            eval=EVAL,
            inc=INCUMBENT,
            w=w or weakness(),
            m=m,
            p=PATCHES if patches is None else patches,
        )

    def test_valid_exits_0(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto()) == 0
        out = capsys.readouterr()
        assert json.loads(out.out)["proposer_tier"] == "capable"
        assert "WARN" not in out.err

    def test_lightweight_proposer_warns_but_passes(self, tmp_path: Path, capsys: Capture) -> None:
        doc = manifesto()
        doc["proposer_model"] = "claude-haiku-5-5"
        assert self.call(tmp_path, doc) == 0
        assert "STOP" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("override", "message"),
        [
            ({"patch": 1}, "patch index"),
            ({"patch": True}, "patch index"),
            ({"pattern": "nope"}, "unknown pattern"),
            ({"component": "vibes"}, "component"),
            ({"evidence": ["t3"]}, "not in pattern"),
            ({"predicted_fixes": []}, "at least one"),
            ({"at_risk": ["s2"]}, "sel task"),
            ({"root_cause": " "}, "root_cause"),
            ({"fix": "copy what s1 expects"}, "names sel task"),
            ({"predicted_fixes": ["t4"]}, "already pass at baseline"),
            ({"at_risk": ["t3"]}, "do not pass at baseline"),
        ],
    )
    def test_invalid_exits_2(
        self, tmp_path: Path, capsys: Capture, override: dict[str, Any], message: str
    ) -> None:
        assert self.call(tmp_path, manifesto(**override)) == 2
        assert message in capsys.readouterr().err

    def test_unverified_predicted_fix_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        argv = [x if x != "@inc" else "@inc2" for x in self.ARGV]
        inc = {**INCUMBENT, "t3": "UNVERIFIED"}
        m = manifesto(predicted_fixes=["t1", "t3"])
        assert run(tmp_path, argv, eval=EVAL, inc2=inc, w=weakness(), m=m, p=PATCHES) == 2
        assert "no verified failing result" in capsys.readouterr().err

    def test_unverified_at_risk_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        argv = [x if x != "@inc" else "@inc2" for x in self.ARGV]
        inc = {**INCUMBENT, "t4": "UNVERIFIED"}
        m = manifesto(at_risk=["t4"])
        assert run(tmp_path, argv, eval=EVAL, inc2=inc, w=weakness(), m=m, p=PATCHES) == 2
        assert "do not pass at baseline" in capsys.readouterr().err

    def test_unaddressable_pattern_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto(), w=weakness(addressable=False)) == 2
        assert "not addressable" in capsys.readouterr().err

    def test_patch_without_entry_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto(), patches=PATCHES * 2) == 2
        assert "no manifesto entry" in capsys.readouterr().err

    def test_duplicate_entry_for_patch_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        doc = manifesto()
        doc["entries"].append(dict(doc["entries"][0]))
        assert self.call(tmp_path, doc) == 2
        assert "has manifesto entries" in capsys.readouterr().err

    def test_prefers_recurrent_pattern_warning(self, tmp_path: Path, capsys: Capture) -> None:
        w = weakness()
        w["patterns"].append({**w["patterns"][0], "id": "p2", "tasks": ["t3"]})
        m = manifesto(pattern="p2", evidence=["t3"], predicted_fixes=["t3"])
        assert self.call(tmp_path, m, w=w) == 0
        assert "prefer recurrent" in capsys.readouterr().err


class TestManifestoVerify:
    ARGV = [
        "manifesto-verify",
        "--eval",
        "@eval",
        "--manifesto",
        "@m",
        "--incumbent-results",
        "@inc",
        "--candidate-results",
        "@cand",
    ]

    def call(self, tmp_path: Path, m: dict[str, Any], cand: dict[str, Any]) -> int:
        return run(tmp_path, self.ARGV, eval=EVAL, m=m, inc=INCUMBENT, cand=cand)

    def test_held_exits_0(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto(), CANDIDATE) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["verdict"] == "PREDICTIONS_HELD"
        assert report["entries"][0]["confirmed_fixes"] == ["t1", "t2"]

    def test_missed_fix_exits_1(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto(), {**CANDIDATE, "t2": False}) == 1
        report = json.loads(capsys.readouterr().out)
        assert report["verdict"] == "PREDICTION_FALSIFIED"
        assert report["entries"][0]["missed_fixes"] == ["t2"]

    def test_unpredicted_regression_exits_1(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto(at_risk=[]), {**CANDIDATE, "t4": False}) == 1
        assert json.loads(capsys.readouterr().out)["unpredicted_regressions"] == ["t4"]

    def test_listed_at_risk_regression_is_reported_not_falsified(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        assert self.call(tmp_path, manifesto(), {**CANDIDATE, "t4": False}) == 0
        assert json.loads(capsys.readouterr().out)["entries"][0]["at_risk_regressed"] == ["t4"]

    def test_unverified_exits_1(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto(), {**CANDIDATE, "t3": "UNVERIFIED"}) == 1
        assert json.loads(capsys.readouterr().out)["verdict"] == "PREDICTION_UNVERIFIED"

    def test_fix_already_passing_at_baseline_is_missed(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        assert self.call(tmp_path, manifesto(predicted_fixes=["t1", "t4"]), CANDIDATE) == 1
        entry = json.loads(capsys.readouterr().out)["entries"][0]
        assert entry["confirmed_fixes"] == ["t1"]
        assert entry["missed_fixes"] == ["t4"]

    def test_unverified_baseline_is_neither_confirmed_nor_missed(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        inc = {**INCUMBENT, "t1": "UNVERIFIED"}
        assert run(tmp_path, self.ARGV, eval=EVAL, m=manifesto(), inc=inc, cand=CANDIDATE) == 1
        report = json.loads(capsys.readouterr().out)
        assert report["verdict"] == "PREDICTION_UNVERIFIED"
        assert report["entries"][0]["confirmed_fixes"] == ["t2"]
        assert report["entries"][0]["missed_fixes"] == []
        assert report["unverified"] == ["t1"]

    def test_sel_prediction_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        assert self.call(tmp_path, manifesto(predicted_fixes=["s1"]), CANDIDATE) == 2
        assert "sel task" in capsys.readouterr().err
