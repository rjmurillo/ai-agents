"""Guard: the debate-log mutation harness stops its nested pytest at first failure.

Issue #5382. A mutant is DEAD as soon as one test fails, so a nested run that
keeps going after that failure spends its time on a verdict already decided. The
debate-log harness ran 943 lefthook and session-log tests per dead mutant. The
SURVIVED control still runs the whole suite because ``-x`` only acts on a
failure.

Two checks, both against the harness and neither launching a nested pytest:

* the command the harness builds contains ``-x`` (a captured ``subprocess.run``,
  so no worktree is created and nothing nested runs);
* the harness still grades the exit codes ``-x`` leaves it: a fake nested run
  that fails (exit 1) is DEAD, one that passes (exit 0) is SURVIVED and
  refused, and an empty suite (exit 5, "no tests ran") or a missing path
  (exit 4) is refused rather than read as a kill.
"""

from __future__ import annotations

import subprocess
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


def _fake_result(returncode: int, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pytest"], returncode=returncode, stdout=stdout, stderr=""
    )


def _grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str]
) -> str:
    """Run _apply_positive_mutant against a canned nested-pytest result."""
    original = b"before\n"
    target = tmp_path / debate_log_path._TARGET_REL
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    monkeypatch.setattr(debate_log_path, "_run_tests_in", lambda _wt_path: result)

    outcome = debate_log_path._apply_positive_mutant(tmp_path, original, b"before", b"after", "x")

    assert target.read_bytes() == original
    return outcome


def test_failing_nested_run_is_graded_dead(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outcome = _grade(tmp_path, monkeypatch, _fake_result(1, "1 failed in 0.1s"))

    assert outcome == debate_log_path._OUTCOME_DEAD


def test_passing_nested_run_is_refused_as_survived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AssertionError, match="MUTANT SURVIVED"):
        _grade(tmp_path, monkeypatch, _fake_result(0, "3 passed in 0.1s"))


def test_empty_nested_run_is_refused_not_graded_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AssertionError, match="no tests were collected"):
        _grade(tmp_path, monkeypatch, _fake_result(5, "no tests ran in 0.01s"))


def test_missing_path_nested_run_is_refused_not_graded_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AssertionError, match="exited 4"):
        _grade(tmp_path, monkeypatch, _fake_result(4, "ERROR: file or directory not found"))
