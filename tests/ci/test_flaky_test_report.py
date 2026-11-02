"""Tests for the ``report`` subcommand of scripts/ci/flaky_test_report.py."""

from __future__ import annotations

import json

from scripts.ci import _flaky_state as fs
from scripts.ci import flaky_test_report as ftr
from tests.ci.flaky_test_helpers import BROKEN, FLAKY, make_state, write_junit


def _report_argv(first, out, outcome="failure"):
    return ["report", "--first-junit", str(first), "--first-outcome", outcome] + [
        "--out-dir",
        str(out),
        "--partition",
        "split-1",
    ]


def _with_state(tmp_path, state, rerun_cases):
    out = tmp_path / "out"
    fs.write_json(out / fs.STATE_FILE, state)
    if rerun_cases is not None:
        write_junit(out / fs.RERUN_JUNIT_FILE, rerun_cases)
    return out


def test_flaky_and_consistent_exit_1_with_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    out = _with_state(tmp_path, make_state(), ["failure", None])
    first = write_junit(tmp_path / "first.xml", ["failure", "failure", None])

    assert ftr.main(_report_argv(first, out)) == fs.EXIT_FAILED
    assert f"::warning title=Flaky test::{FLAKY}" in capsys.readouterr().out
    assert "| flaky |" in summary.read_text(encoding="utf-8")
    report = json.loads((out / fs.REPORT_FILE).read_text(encoding="utf-8"))
    assert (report["flaky"], report["consistent"]) == ([FLAKY], [BROKEN])
    assert report["exit_code"] == fs.EXIT_FAILED


def test_first_run_passed_writes_no_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    first = write_junit(tmp_path / "first.xml", [None])
    assert ftr.main(_report_argv(first, tmp_path / "out", "success")) == fs.EXIT_OK
    assert not summary.exists()


def test_without_state_exits_3_and_writes_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    first = write_junit(tmp_path / "first.xml", ["failure"])
    assert ftr.main(_report_argv(first, tmp_path / "out")) == fs.EXIT_EXTERNAL
    assert "wrote no state" in summary.read_text(encoding="utf-8")


def test_missing_first_junit_exits_3(tmp_path):
    out = tmp_path / "out"
    assert ftr.main(_report_argv(tmp_path / "absent.xml", out)) == fs.EXIT_EXTERNAL
    assert json.loads((out / fs.REPORT_FILE).read_text())["verdict"] == "error"


def test_bad_state_exits_2(tmp_path):
    out = _with_state(tmp_path, {"version": 0}, None)
    first = write_junit(tmp_path / "first.xml", ["failure"])
    assert ftr.main(_report_argv(first, out)) == fs.EXIT_CONFIG


def test_malformed_rerun_junit_exits_3(tmp_path):
    out = _with_state(tmp_path, make_state(), None)
    (out / fs.RERUN_JUNIT_FILE).write_text("<broken", encoding="utf-8")
    first = write_junit(tmp_path / "first.xml", ["failure", "failure"])
    assert ftr.main(_report_argv(first, out)) == fs.EXIT_EXTERNAL
