"""Tests for scripts/ci/_flaky_rerun.py: the one serial rerun of failed tests."""

from __future__ import annotations

import json

from scripts.ci import _flaky_rerun as fr
from scripts.ci import _flaky_state as fs
from tests.ci.flaky_test_helpers import BROKEN, FLAKY, rerun_cache, write_lastfailed


def _runner(out_dir, still_failing, exit_code, calls):
    def runner(args):
        calls.append(args)
        if still_failing:
            write_lastfailed(rerun_cache(out_dir), still_failing)
        return exit_code

    return runner


def _status(out_dir):
    return json.loads((out_dir / fs.STATE_FILE).read_text(encoding="utf-8"))["status"]


def test_rerun_runs_only_failed_tests_serially(tmp_path):
    out = tmp_path / "out"
    calls: list = []
    lastfailed = write_lastfailed(tmp_path / "lf", [FLAKY, BROKEN])

    rc = fr.run_rerun(lastfailed, out, 25, _runner(out, [BROKEN], 1, calls))

    assert rc == fs.EXIT_OK
    (args,) = calls
    assert args[:2] == ["-n", "0"]
    assert args[-2:] == [BROKEN, FLAKY]
    assert f"cache_dir={(out / fs.RERUN_CACHE_DIR).resolve()}" in args
    assert f"--junitxml={(out / fs.RERUN_JUNIT_FILE).resolve()}" in args
    state = json.loads((out / fs.STATE_FILE).read_text(encoding="utf-8"))
    assert state["status"] == fs.STATUS_RAN
    assert state["rerun_exit"] == 1
    assert state["rerun_failures"] == [BROKEN]


def test_rerun_skipped_without_nodeids(tmp_path, capsys):
    out = tmp_path / "out"
    calls: list = []
    assert fr.run_rerun(tmp_path / "absent", out, 25, _runner(out, [], 0, calls)) == fs.EXIT_OK
    assert calls == []
    assert _status(out) == fs.STATUS_NO_NODEIDS
    assert "lists no failed test" in capsys.readouterr().out


def test_rerun_skipped_above_cap(tmp_path, capsys):
    out = tmp_path / "out"
    calls: list = []
    lastfailed = write_lastfailed(tmp_path / "lf", [f"t::{i}" for i in range(3)])
    assert fr.run_rerun(lastfailed, out, 2, _runner(out, [], 0, calls)) == fs.EXIT_OK
    assert calls == []
    assert _status(out) == fs.STATUS_OVER_CAP
    assert "3 failed tests exceed the cap of 2" in capsys.readouterr().out


def test_rerun_at_cap_still_runs(tmp_path):
    out = tmp_path / "out"
    calls: list = []
    lastfailed = write_lastfailed(tmp_path / "lf", ["t::0", "t::1"])
    fr.run_rerun(lastfailed, out, 2, _runner(out, [], 0, calls))
    assert len(calls) == 1
    assert _status(out) == fs.STATUS_RAN


def test_rerun_state_says_started_while_pytest_runs(tmp_path):
    out = tmp_path / "out"
    seen: list = []

    def runner(args):
        seen.append(_status(out))
        return 0

    fr.run_rerun(write_lastfailed(tmp_path / "lf", [FLAKY]), out, 25, runner)
    assert seen == [fs.STATUS_STARTED]
