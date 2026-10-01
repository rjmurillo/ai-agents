"""Ref-shape and failure-path cases for the pre-push infrastructure scan (issue #6076).

Tags, notes, multi-ref pushes, renames, fetch and diff failures, and the
short-circuit after a branch policy failure. Core acceptance cases live in
``test_push_infrastructure_scan.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy as policy
from tests.validation._push_scan_repo import (
    WORKFLOW,
    ZERO,
    Origin,
    commit,
    configure,
    git,
    install_scripts,
    new_branch_line,
    pre_push,
    work_clone,
)


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    return Origin(tmp_path)


def test_push_with_no_changed_files_skips_the_detector_and_reports_zero(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A branch at origin/main scores zero files, reported, without the detector."""
    work = work_clone(origin, tmp_path, detector=False)
    git(work, "checkout", "-q", "-b", "feature/empty", "origin/main")
    head = git(work, "rev-parse", "HEAD")

    result = pre_push(work, new_branch_line("feature/empty", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/empty scores 0 file(s)" in err


def test_failed_diff_fails_loud(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC5: a diff git cannot produce is a config error, not an empty file list."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")
    real_run_git = policy._run_git

    def failing_scan_diff(
        repo_root: Path, args: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["diff", "--name-only", "-z", "--no-renames"]:
            return subprocess.CompletedProcess(args, 128, "", "fatal: bad object\n")
        return real_run_git(repo_root, args, **kwargs)

    monkeypatch.setattr(policy, "_run_git", failing_scan_diff)

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "could not diff" in err
    assert "scores" not in err


def test_branch_policy_failure_returns_before_the_scan(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scan runs only after the per-update branch policies pass."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")
    scanned: list[object] = []

    def record_scan(*args: object) -> int:
        scanned.append(args)
        return 0

    monkeypatch.setattr(policy, "_check_push_updates", lambda *_args: 1)
    monkeypatch.setattr(policy, "check_pushed_infrastructure", record_scan)

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    assert result == 1
    assert scanned == []


def test_tag_push_with_workflow_change_and_no_marker_is_blocked(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A tag runs its commit's workflows, so a tag push is scored like a branch."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/release")
    head = commit(work, WORKFLOW, "on: push\n")
    git(work, "tag", "v9.9.9", head)
    line = f"refs/tags/v9.9.9 {head} refs/tags/v9.9.9 {ZERO}\n"

    result = pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "refs/tags/v9.9.9 scores 1 file(s)" in err


def test_tag_on_main_scores_nothing_and_notes_refs_are_skipped(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A release tag on main carries no branch change; a notes ref is not scanned."""
    work = work_clone(origin, tmp_path, detector=False)
    git(work, "checkout", "-q", "-b", "feature/other", "origin/main")
    main_tip = git(work, "rev-parse", "origin/main")
    git(work, "notes", "add", "-m", "note", main_tip)
    notes = git(work, "rev-parse", "refs/notes/commits")

    tag = pre_push(work, f"refs/tags/v1 {main_tip} refs/tags/v1 {ZERO}\n", monkeypatch)
    tag_err = capsys.readouterr().err
    note = pre_push(work, f"refs/notes/commits {notes} refs/notes/commits {ZERO}\n", monkeypatch)
    note_err = capsys.readouterr().err

    assert tag == 0, tag_err
    assert "refs/tags/v1 scores 0 file(s)" in tag_err
    assert note == 0, note_err
    assert "skipped, no branch or tag ref in this push carries commits" in note_err


def test_multi_ref_push_blocks_when_only_the_second_ref_is_unreviewed(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every ref is scored; one clean ref does not cover another."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    docs = commit(work, "docs/note.md", "note\n")
    git(work, "checkout", "-q", "-b", "feature/ci", "origin/main")
    ci = commit(work, WORKFLOW, "on: push\n")
    payload = new_branch_line("feature/docs", docs) + new_branch_line("feature/ci", ci)

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "refs/heads/feature/docs scores 1 file(s)" in err
    assert "refs/heads/feature/ci scores 1 file(s)" in err


def test_renaming_a_workflow_away_still_scores_the_workflow_path(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--no-renames reports both sides, so moving a workflow out is still CRITICAL."""
    origin.advance_main(WORKFLOW)
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/move")
    git(work, "mv", WORKFLOW, "ci-moved.yml")
    git(work, "commit", "-qm", "test: move workflow")
    head = git(work, "rev-parse", "HEAD")

    result = pre_push(work, new_branch_line("feature/move", head), monkeypatch)

    captured = capsys.readouterr()
    assert result == 1, captured.err
    assert "scores 2 file(s)" in captured.err
    assert WORKFLOW in captured.out


def test_failed_fetch_fails_closed_instead_of_scoring_a_stale_base(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC8: an unreachable origin fails the scan with exit 3, scoring nothing."""
    work = work_clone(origin, tmp_path)
    git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 3, err
    assert "will not score from a stale origin/main" in err
    assert "scores" not in err


def _branch_deleting_a_workflow_main_added_after_a_stale_ref(
    origin: Origin, tmp_path: Path
) -> tuple[Path, str]:
    """Main adds a workflow after the clone; the branch deletes it; origin/main stays stale."""
    work = work_clone(origin, tmp_path)
    stale = git(work, "rev-parse", "origin/main")
    origin.advance_main(WORKFLOW)
    # Fetch by path, not by remote name, so refs/remotes/origin/main is not updated.
    git(work, "fetch", "-q", str(origin.bare), "main:refs/heads/fresh-main")
    git(work, "checkout", "-q", "-b", "feature/drop-ci", "fresh-main")
    git(work, "rm", "-q", WORKFLOW)
    git(work, "commit", "-q", "-m", "drop ci")
    assert git(work, "rev-parse", "origin/main") == stale
    assert git(work, "rev-parse", "fresh-main") != stale
    git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    return work, git(work, "rev-parse", "HEAD")


def test_stale_base_hides_a_deleted_workflow_when_the_scan_trusts_it(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Control: scored from the stale base, the workflow deletion is invisible."""
    work, head = _branch_deleting_a_workflow_main_added_after_a_stale_ref(origin, tmp_path)
    monkeypatch.setattr(policy, "_fetch_origin_main", lambda _repo_root: True)

    result = pre_push(work, new_branch_line("feature/drop-ci", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/drop-ci scores 0 file(s)" in err


def test_failed_refresh_blocks_the_stale_base_that_would_hide_a_deleted_workflow(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With the real (failing) refresh, the same push fails closed with exit 3."""
    work, head = _branch_deleting_a_workflow_main_added_after_a_stale_ref(origin, tmp_path)

    result = pre_push(work, new_branch_line("feature/drop-ci", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 3, err
    assert "will not score from a stale origin/main" in err
    assert "scores" not in err


def test_shallow_clone_gets_the_unshallow_remedy_not_the_rebase_advice(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """merge-base exits 1 in a shallow clone too, where rebasing would not help.

    The history-integrity gate blocks a shallow repository before the scan, so
    the push gets the unshallow remedy and the scan never runs.
    """
    work = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", f"file://{origin.bare}", str(work)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    configure(work, origin.hooks)
    install_scripts(work)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")
    origin.advance_main("docs/one.md")
    origin.advance_main("docs/two.md")
    git(work, "fetch", "-q", "--depth", "1", "origin", "main")
    monkeypatch.setattr(policy, "_fetch_origin_main", lambda _repo_root: True)

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "git fetch --unshallow origin" in err
    assert "Rebase the branch" not in err
    assert "scores" not in err


def test_config_error_stops_the_scan_before_later_refs(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After an exit 2 the remaining refs are not scored."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs", "origin/main")
    docs = commit(work, "docs/note.md", "note\n")
    git(work, "checkout", "-q", "--orphan", "feature/orphan")
    git(work, "rm", "-rq", "--cached", ".")
    orphan = commit(work, "docs/orphan.md", "orphan\n")
    payload = new_branch_line("feature/orphan", orphan) + new_branch_line("feature/docs", docs)

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "refs/heads/feature/docs scores" not in err


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
