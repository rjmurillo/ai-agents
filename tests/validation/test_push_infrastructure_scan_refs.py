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


def test_failed_refresh_is_reported_when_a_branch_policy_fails_first(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The scan never runs, so the policy failure carries the stale-base warning once."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")
    git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    monkeypatch.setattr(policy, "_check_push_updates", lambda *_args: 1)

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert err.count("could not refresh origin/main") == 1
    assert "will not score from a stale origin/main" not in err


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


def test_failed_refresh_with_nothing_to_scan_still_warns(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A notes-only push gets no scan, so the failed refresh is reported as a warning."""
    work = work_clone(origin, tmp_path, detector=False)
    git(work, "checkout", "-q", "-b", "feature/other", "origin/main")
    main_tip = git(work, "rev-parse", "origin/main")
    git(work, "notes", "add", "-m", "note", main_tip)
    notes = git(work, "rev-parse", "refs/notes/commits")
    git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))

    result = pre_push(work, f"refs/notes/commits {notes} refs/notes/commits {ZERO}\n", monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert err.count("WARNING: could not refresh origin/main; using local ref") == 1
    assert "will not score from a stale origin/main" not in err


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


def test_multi_ref_push_scores_every_unreviewed_ref_and_exits_one(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An exit 1 on the first ref does not stop the scan before the second ref."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/ci-one", "origin/main")
    first = commit(work, WORKFLOW, "on: push\n")
    git(work, "checkout", "-q", "-b", "feature/ci-two", "origin/main")
    second = commit(work, ".github/workflows/other.yml", "on: push\n")
    payload = new_branch_line("feature/ci-one", first) + new_branch_line("feature/ci-two", second)

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "refs/heads/feature/ci-one scores 1 file(s)" in err
    assert "refs/heads/feature/ci-two scores 1 file(s)" in err


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
    assert "WARNING: could not refresh origin/main" not in err


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
        ["git", "clone", "-q", "--depth", "1", origin.bare.resolve().as_uri(), str(work)],
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


@pytest.mark.parametrize("later_exit", [2, 3])
def test_later_typed_failure_overrides_an_earlier_unreviewed_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, later_exit: int
) -> None:
    """Ref A returns 1, ref B returns 2 or 3: the typed failure is the overall exit."""
    codes = {"refs/heads/a": 1, "refs/heads/b": later_exit}
    scored: list[str] = []

    def fake(push_ref: policy.PushRef, _root: Path, _deadline: float) -> int:
        scored.append(push_ref.remote_ref)
        return codes[push_ref.remote_ref]

    monkeypatch.setattr(policy, "_check_ref_infrastructure", fake)
    refs = [
        policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/a", ZERO),
        policy.PushRef("refs/heads/b", "2" * 40, "refs/heads/b", ZERO),
    ]

    result = policy.check_pushed_infrastructure(refs, tmp_path)

    assert result == later_exit
    assert scored == ["refs/heads/a", "refs/heads/b"]


def test_mixed_push_reports_each_skipped_ref(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A notes ref beside a scanned branch is skipped, and the skip is named."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs", "origin/main")
    docs = commit(work, "docs/note.md", "note\n")
    main_tip = git(work, "rev-parse", "origin/main")
    git(work, "notes", "add", "-m", "note", main_tip)
    notes = git(work, "rev-parse", "refs/notes/commits")
    payload = new_branch_line("feature/docs", docs)
    payload += f"refs/notes/commits {notes} refs/notes/commits {ZERO}\n"

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/docs scores 1 file(s)" in err
    assert "skipped refs/notes/commits" in err
