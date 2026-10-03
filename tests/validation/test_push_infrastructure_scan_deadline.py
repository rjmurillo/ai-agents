"""Deadline and external-failure cases for the pre-push infrastructure scan (issue #6076).

The scan's git steps and detector runs share one deadline: 60s from the scan's
start, never later than 110s after push-ref-policy started, inside its 2m
lefthook cap. A git step that does not complete exits 3, and the scan stops at
the first exit 3. Core cases live in ``test_push_infrastructure_scan.py``; ref
shapes and config errors in ``test_push_infrastructure_scan_refs.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy as policy
from tests.validation._push_scan_repo import (
    Origin,
    commit,
    git,
    new_branch_line,
    pre_push,
    work_clone,
)


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    return Origin(tmp_path)


@pytest.mark.parametrize("step", ["merge-base", "diff"])
def test_git_step_that_did_not_complete_exits_3_without_a_fetch_remedy(
    step: str,
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A timed-out git step is an external failure, not a missing base."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")
    real_run_git = policy._run_git
    scan_args = {
        "merge-base": ["merge-base", "origin/main", head],
        "diff": ["diff", "--name-only", "-z", "--no-renames"],
    }[step]

    def timed_out_step(
        repo_root: Path, args: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[: len(scan_args)] == scan_args:
            return subprocess.CompletedProcess(args, 3, "", "timed out after 90s\n")
        return real_run_git(repo_root, args, **kwargs)

    monkeypatch.setattr(policy, "_run_git", timed_out_step)

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 3, err
    assert f"git {step} did not complete for refs/heads/feature/docs" in err
    assert "git fetch origin main" not in err


def _two_ref_push(origin: Origin, tmp_path: Path) -> tuple[Path, str]:
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/a")
    first = commit(work, "docs/a.md", "a\n")
    git(work, "checkout", "-q", "-b", "feature/b", "origin/main")
    second = commit(work, "docs/b.md", "b\n")
    return work, new_branch_line("feature/a", first) + new_branch_line("feature/b", second)


def test_refs_share_one_detector_budget(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second ref's detector gets only what the first ref left of the budget."""
    work, payload = _two_ref_push(origin, tmp_path)
    clock = [1000.0]
    timeouts: list[float] = []
    real_run_command = policy._run_command

    def slow_detector(
        args: list[str], repo_root: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if policy.DETECT_INFRASTRUCTURE_SCRIPT in args:
            timeouts.append(kwargs["timeout_seconds"])
            clock[0] += 50.0
            return subprocess.CompletedProcess(list(args), 0, "", "")
        return real_run_command(args, repo_root, **kwargs)

    monkeypatch.setattr(policy, "_run_command", slow_detector)
    monkeypatch.setattr(policy.time, "monotonic", lambda: clock[0])

    result = pre_push(work, payload, monkeypatch)

    assert result == 0
    assert timeouts == [60.0, 10.0]


def test_scan_stops_after_a_detector_timeout(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After an exit 3, the remaining refs are not scanned and the push fails 3."""
    work, payload = _two_ref_push(origin, tmp_path)
    calls: list[list[str]] = []
    real_run_command = policy._run_command

    def timing_out_detector(
        args: list[str], repo_root: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if policy.DETECT_INFRASTRUCTURE_SCRIPT in args:
            calls.append(list(args))
            return subprocess.CompletedProcess(list(args), 3, "", "timed out\n")
        return real_run_command(args, repo_root, **kwargs)

    monkeypatch.setattr(policy, "_run_command", timing_out_detector)

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 3, err
    assert len(calls) == 1
    assert "refs/heads/feature/b scores" not in err


def test_spent_budget_fails_3_without_running_the_detector(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A ref reached after the budget is gone fails typed, not with a 0s run."""
    work, payload = _two_ref_push(origin, tmp_path)
    clock = [1000.0]
    calls: list[float] = []
    real_run_command = policy._run_command

    def budget_eating_detector(
        args: list[str], repo_root: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if policy.DETECT_INFRASTRUCTURE_SCRIPT in args:
            calls.append(kwargs["timeout_seconds"])
            clock[0] += 61.0
            return subprocess.CompletedProcess(list(args), 0, "", "")
        return real_run_command(args, repo_root, **kwargs)

    monkeypatch.setattr(policy, "_run_command", budget_eating_detector)
    monkeypatch.setattr(policy.time, "monotonic", lambda: clock[0])

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 3, err
    assert calls == [60.0]
    assert "scan deadline passed before git merge-base for refs/heads/feature/b" in err


def test_slow_fetch_shrinks_the_scan_deadline_to_fit_the_job_cap(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Time spent before the scan comes out of the scan, not past the 2m cap."""
    work, payload = _two_ref_push(origin, tmp_path)
    clock = [1000.0]
    timeouts: list[float] = []
    real_run_command = policy._run_command

    def slow_fetch(
        args: list[str], repo_root: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if "fetch" in args:
            clock[0] += 100.0
            return subprocess.CompletedProcess(list(args), 0, "", "")
        if policy.DETECT_INFRASTRUCTURE_SCRIPT in args:
            timeouts.append(kwargs["timeout_seconds"])
            return subprocess.CompletedProcess(list(args), 0, "", "")
        if "--no-renames" in args:
            diff_timeouts.append(kwargs["timeout_seconds"])
        return real_run_command(args, repo_root, **kwargs)

    diff_timeouts: list[float] = []
    monkeypatch.setattr(policy, "_run_command", slow_fetch)
    monkeypatch.setattr(policy.time, "monotonic", lambda: clock[0])

    result = pre_push(work, payload, monkeypatch)

    assert result == 0
    assert timeouts == [10.0, 10.0]
    assert diff_timeouts == [10.0, 10.0]


def test_git_step_after_the_deadline_exits_3_without_running_git(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A scan that starts past the job deadline fails typed before any git step."""
    work, payload = _two_ref_push(origin, tmp_path)
    clock = [1000.0]
    scan_steps: list[list[str]] = []
    real_run_command = policy._run_command

    def stalled_fetch(
        args: list[str], repo_root: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if "fetch" in args:
            clock[0] += 115.0
            return subprocess.CompletedProcess(list(args), 0, "", "")
        if "--no-renames" in args or policy.DETECT_INFRASTRUCTURE_SCRIPT in args:
            scan_steps.append(list(args))
        return real_run_command(args, repo_root, **kwargs)

    monkeypatch.setattr(policy, "_run_command", stalled_fetch)
    monkeypatch.setattr(policy.time, "monotonic", lambda: clock[0])

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 3, err
    assert "scan deadline passed before git merge-base" in err
    assert scan_steps == []


def test_slow_diff_spends_the_deadline_before_the_detector_runs(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Time a ref's own diff takes is checked again before its detector starts."""
    work, payload = _two_ref_push(origin, tmp_path)
    clock = [1000.0]
    detector_calls: list[float] = []
    real_run_command = policy._run_command

    def slow_diff(
        args: list[str], repo_root: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if policy.DETECT_INFRASTRUCTURE_SCRIPT in args:
            detector_calls.append(kwargs["timeout_seconds"])
            return subprocess.CompletedProcess(list(args), 0, "", "")
        result = real_run_command(args, repo_root, **kwargs)
        if "--no-renames" in args:
            clock[0] += 61.0
        return result

    monkeypatch.setattr(policy, "_run_command", slow_diff)
    monkeypatch.setattr(policy.time, "monotonic", lambda: clock[0])

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 3, err
    assert detector_calls == []
    assert "deadline passed before scoring refs/heads/feature/a" in err
