"""Guard: the debate-log mutation harness stops its nested pytest at first failure.

Issue #5382. A mutant is DEAD as soon as one test fails, so a nested run that
keeps going after that failure spends its time on a verdict already decided. The
debate-log harness ran 943 lefthook and session-log tests per dead mutant. The
SURVIVED control still runs the whole suite because ``-x`` only acts on a
failure.

Two checks:

* the command the harness builds contains ``-x`` (a captured ``subprocess.run``,
  so no worktree is created and nothing nested runs);
* a real nested pytest with ``-x`` still gives the exit codes the harness grades
  on: a failing suite exits 1 (DEAD), a passing suite exits 0 (SURVIVED), and an
  empty suite exits 5 (never read as a kill, the harness asserts it is not 4 and
  that "no tests ran" is absent).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.mutation import test_mutate_debate_log_path as debate_log_path


def test_harness_nested_pytest_command_has_x(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], *_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    debate_log_path._run_tests_in(tmp_path)

    assert len(captured) == 1, f"expected one nested pytest launch, saw {len(captured)}"
    cmd = captured[0]
    assert "pytest" in cmd, f"not a pytest launch: {cmd}"
    assert "-x" in cmd, f"nested pytest must stop at first failure: {cmd}"
    for test_path in debate_log_path._TESTS:
        assert test_path in cmd, f"{test_path} dropped from the nested run: {cmd}"


def _nested_pytest(suite_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-x",
            "-q",
            "--tb=no",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            "--rootdir",
            str(suite_dir),
        ],
        cwd=suite_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_failing_suite_stops_at_first_failure_and_exits_1(tmp_path: Path) -> None:
    (tmp_path / "test_many_failures.py").write_text(
        "def test_a():\n    assert False\n"
        "def test_b():\n    assert False\n"
        "def test_c():\n    assert False\n",
        encoding="utf-8",
    )

    result = _nested_pytest(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 failed" in result.stdout, result.stdout
    assert "3 failed" not in result.stdout, "-x did not stop the run"


def test_passing_suite_still_runs_everything_and_exits_0(tmp_path: Path) -> None:
    (tmp_path / "test_all_pass.py").write_text(
        "def test_a():\n    assert True\n"
        "def test_b():\n    assert True\n"
        "def test_c():\n    assert True\n",
        encoding="utf-8",
    )

    result = _nested_pytest(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout, result.stdout


def test_empty_suite_exits_5_with_no_tests_ran(tmp_path: Path) -> None:
    result = _nested_pytest(tmp_path)

    assert result.returncode == 5, result.stdout + result.stderr
    assert "no tests ran" in result.stdout.lower()
