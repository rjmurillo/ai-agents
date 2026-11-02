"""Tests for the ``rerun`` subcommand and argument handling of flaky_test_report.py."""

from __future__ import annotations

import subprocess
import sys

import pytest

from scripts.ci import _flaky_state as fs
from scripts.ci import flaky_test_report as ftr
from tests.ci.flaky_test_helpers import FLAKY, write_lastfailed


def _rerun_argv(tmp_path, lastfailed, *extra):
    return ["rerun", "--out-dir", str(tmp_path / "o"), "--lastfailed", str(lastfailed), *extra]


def test_rerun_defaults_to_the_real_pytest_runner(tmp_path, monkeypatch):
    calls: list = []
    monkeypatch.setattr(ftr.run_pytest_non_tmp, "main", lambda args: calls.append(args) or 0)
    lastfailed = write_lastfailed(tmp_path / "lf", [FLAKY])
    assert ftr.main(_rerun_argv(tmp_path, lastfailed, "--max-tests", "1")) == fs.EXIT_OK
    assert calls and calls[0][-1] == FLAKY


def test_rerun_malformed_cache_exits_3(tmp_path):
    lastfailed = tmp_path / "lf"
    lastfailed.write_text("{bad", encoding="utf-8")
    assert ftr.main(_rerun_argv(tmp_path, lastfailed), lambda args: 0) == fs.EXIT_EXTERNAL


def test_rerun_unwritable_out_dir_exits_3(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    argv = ["rerun", "--out-dir", str(blocker / "o"), "--lastfailed", str(tmp_path / "x")]
    assert ftr.main(argv, lambda args: 0) == fs.EXIT_EXTERNAL


@pytest.mark.parametrize(
    "argv",
    [[], ["rerun"], ["rerun", "--out-dir", "o", "--max-tests", "0"], ["report", "--out-dir", "o"]],
)
def test_bad_arguments_exit_2(argv):
    assert ftr.main(argv) == fs.EXIT_CONFIG


def test_help_exits_0():
    assert ftr.main(["--help"]) == fs.EXIT_OK


def test_script_subprocess_exits_nonzero_on_missing_junit(tmp_path):
    argv = ["report", "--first-junit", str(tmp_path / "absent.xml"), "--first-outcome"]
    argv += ["failure", "--out-dir", str(tmp_path / "o"), "--partition", "split-1"]
    result = subprocess.run(
        [sys.executable, ftr.__file__, *argv],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == fs.EXIT_EXTERNAL
    assert "JUnit report not found" in result.stdout
